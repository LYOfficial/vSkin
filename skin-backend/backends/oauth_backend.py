import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode

import jwt
from fastapi import HTTPException

from config_loader import Config
from database_module import Database
from utils.user_groups import resolve_user_group, get_user_group_meta, is_admin_group


class OAuthProtocolError(Exception):
    def __init__(self, error: str, description: str | None = None, status_code: int = 400):
        self.error = error
        self.description = description
        self.status_code = status_code
        super().__init__(description or error)


class OAuthBackend:
    SUPPORTED_SCOPES = {
        "userinfo": {
            "label": "用户基础信息",
            "description": "读取用户ID、用户名和头像",
        },
        "profile": {
            "label": "用户名",
            "description": "读取用户名（显示名称）",
        },
        "avatar": {
            "label": "头像",
            "description": "读取头像地址",
        },
        "email": {
            "label": "邮箱",
            "description": "读取邮箱地址",
        },
        "skin": {
            "label": "当前皮肤",
            "description": "读取当前正在使用的皮肤 PNG 源图",
        },
        "permission": {
            "label": "权限组",
            "description": "读取用户权限组信息",
        },
        "openid": {
            "label": "OpenID 登录",
            "description": "签发 id_token 供启动器完成登录",
        },
        "offline_access": {
            "label": "离线刷新",
            "description": "允许客户端获取 refresh_token 并续期登录",
        },
        "Yggdrasil.PlayerProfiles.Select": {
            "label": "角色选择",
            "description": "允许启动器读取当前选中角色信息",
        },
        "Yggdrasil.Server.Join": {
            "label": "服务器会话",
            "description": "允许启动器完成联机服登录所需的认证流程",
        },
    }
    DEVICE_DEFAULT_SCOPE = "openid offline_access Yggdrasil.PlayerProfiles.Select Yggdrasil.Server.Join"
    DEVICE_SCOPE_KEYS = {
        "openid",
        "offline_access",
        "Yggdrasil.PlayerProfiles.Select",
        "Yggdrasil.Server.Join",
    }

    def __init__(self, db: Database, config: Config, crypto):
        self.db = db
        self.config = config
        self.crypto = crypto

    def _site_url(self) -> str:
        return str(self.config.get("server.site_url", "")).rstrip("/")

    def _normalize_path_prefix(self, value: str, default: str = "") -> str:
        raw = str(value or default or "").strip()
        if not raw:
            return ""
        normalized = "/" + raw.strip("/")
        return "" if normalized == "/" else normalized

    def _api_url(self) -> str:
        api_url = str(self.config.get("server.api_url", "")).rstrip("/")
        if api_url:
            return api_url
        site = self._site_url()
        root_path = str(self.config.get("server.root_path", "")).rstrip("/")
        if site and root_path:
            return site + root_path
        return site

    def _issuer(self) -> str:
        return self._api_url() or self._site_url()

    async def _janus_enabled(self) -> bool:
        value = await self.db.setting.get("janus_enabled", None)
        if value is None:
            return bool(self.config.get("janus.enabled", True))
        return str(value).lower() == "true"

    async def _janus_base_path(self) -> str:
        value = await self.db.setting.get("janus_base_path", None)
        fallback = str(self.config.get("janus.base_path", "/api/janus") or "/api/janus")
        return self._normalize_path_prefix(value, fallback) or "/api/janus"

    async def _janus_issuer(self) -> str:
        custom_issuer = (await self._get_setting_text("janus_issuer", "")).rstrip("/")
        if custom_issuer:
            return custom_issuer
        api_url = self._api_url().rstrip("/")
        base_path = await self._janus_base_path()
        if api_url:
            return f"{api_url}{base_path}"
        return base_path

    async def _janus_union_payload(self) -> dict:
        mode = (await self._get_setting_text("janus_union_mode", "all")).strip().lower() or "all"
        if mode not in {"all", "only", "excludes"}:
            mode = "all"
        return {
            "api_base": await self._get_setting_text("janus_union_api_base", str(self.config.get("janus.union_api_base", "https://skin.mualliance.ltd/api/union") or "https://skin.mualliance.ltd/api/union")),
            "mode": mode,
            "code": await self._get_setting_text("janus_union_code", ""),
            "auto_sync": (await self._get_setting_text("janus_union_auto_sync", "false")).lower() == "true",
        }

    def _verification_uri(self) -> str:
        site_url = self._site_url()
        if site_url:
            return f"{site_url}/device"
        return "/device"

    async def _get_setting_text(self, key: str, default: str = "") -> str:
        value = await self.db.setting.get(key, None)
        if value is None or value == "":
            return default
        return str(value)

    async def _get_setting_int(self, key: str, default: int, minimum: int) -> int:
        raw = await self.db.setting.get(key, None)
        if raw in (None, ""):
            return default
        try:
            final = int(raw)
        except (TypeError, ValueError):
            return default
        return max(minimum, final)

    def _jwks_kid(self) -> str:
        return str(self.config.get("oauth.jwks_kid", "main") or "main")

    def _access_token_expires_in(self) -> int:
        return max(300, int(self.config.get("oauth.access_token_expires_in", 7200) or 7200))

    def _refresh_token_expires_in(self) -> int:
        return max(3600, int(self.config.get("oauth.refresh_token_expires_in", 2592000) or 2592000))

    async def _device_expires_in(self) -> int:
        return await self._get_setting_int(
            "oauth_device_expires_in",
            max(300, int(self.config.get("oauth.device.expires_in", 900) or 900)),
            300,
        )

    async def _device_interval(self) -> int:
        return await self._get_setting_int(
            "oauth_device_interval",
            max(5, int(self.config.get("oauth.device.interval", 5) or 5)),
            5,
        )

    async def _shared_client_id(self) -> int | None:
        value = await self.db.setting.get("oauth_device_shared_client_id", None)
        if value in (None, ""):
            value = self.config.get("oauth.device.shared_client_id", "")
        if value in (None, ""):
            return None
        try:
            final = int(value)
        except (TypeError, ValueError):
            return None
        return final if final > 0 else None

    async def _device_default_redirect_uri(self) -> str:
        return await self._get_setting_text("oauth_device_default_redirect_uri", "https://oauth.ustb.world/")

    async def _device_settings_payload(self) -> dict:
        return {
            "shared_client_id": await self._shared_client_id(),
            "expires_in": await self._device_expires_in(),
            "interval": await self._device_interval(),
            "default_redirect_uri": await self._device_default_redirect_uri(),
        }

    async def _set_shared_client_id(self, app_id: int | None):
        await self.db.setting.set("oauth_device_shared_client_id", "" if app_id is None else str(int(app_id)))

    def _avatar_url_from_hash(self, avatar_hash: str | None) -> str:
        site = self._site_url()
        if avatar_hash:
            path = f"/static/textures/{avatar_hash}.png"
            return f"{site}{path}" if site else path
        path = "/public/default-avatar"
        api_url = self._api_url()
        return f"{api_url}{path}" if api_url else path

    def _skin_url_from_hash(self, skin_hash: str) -> str:
        path = f"/static/textures/{skin_hash}.png"
        site = self._site_url()
        return f"{site}{path}" if site else path

    def _texture_file_path(self, texture_hash: str) -> str | None:
        candidate_dirs = []

        textures_dir = getattr(self.db.texture, "textures_dir", None)
        if textures_dir:
            candidate_dirs.append(str(textures_dir))

        config_dir = str(self.config.get("textures.directory", "textures"))
        if config_dir not in candidate_dirs:
            candidate_dirs.append(config_dir)

        if "textures" not in candidate_dirs:
            candidate_dirs.append("textures")

        for directory in candidate_dirs:
            file_path = os.path.join(directory, f"{texture_hash}.png")
            if os.path.isfile(file_path):
                return file_path

        return None

    def _parse_scope(
        self,
        scope: str,
        default_scope: str = "userinfo",
        allowed_scopes: set[str] | None = None,
    ) -> tuple[str, list[str]]:
        raw = (scope or default_scope).replace(",", " ")
        chunks = [x.strip() for x in raw.split(" ") if x.strip()]
        if not chunks:
            chunks = [x.strip() for x in default_scope.split(" ") if x.strip()]

        result: list[str] = []
        for item in chunks:
            if item == "basic":
                item = "userinfo"
            if item not in self.SUPPORTED_SCOPES:
                raise HTTPException(status_code=400, detail=f"unsupported scope: {item}")
            if allowed_scopes is not None and item not in allowed_scopes:
                raise HTTPException(status_code=400, detail=f"unsupported scope: {item}")
            if item not in result:
                result.append(item)
        return " ".join(result), result

    def _scope_items(self, scopes: list[str]) -> list[dict]:
        # userinfo 已包含用户名与头像读取能力，授权页不重复展示 profile/avatar。
        display_scopes = list(scopes)
        if "userinfo" in display_scopes:
            display_scopes = [x for x in display_scopes if x not in {"profile", "avatar"}]

        items = []
        for key in display_scopes:
            meta = self.SUPPORTED_SCOPES.get(key, {})
            items.append(
                {
                    "key": key,
                    "label": meta.get("label", key),
                    "description": meta.get("description", ""),
                }
            )
        return items

    def _has_scope(self, scope_text: str, item: str) -> bool:
        _, scopes = self._parse_scope(scope_text)
        return item in scopes

    def _normalize_redirect_uri(self, redirect_uri: str) -> str:
        if not redirect_uri:
            raise HTTPException(status_code=400, detail="redirect_uri required")
        value = str(redirect_uri).strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            raise HTTPException(status_code=400, detail="redirect_uri must start with http:// or https://")
        return value

    def _hash_secret(self, secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def _make_secret(self) -> str:
        return secrets.token_urlsafe(36)

    def _make_code(self) -> str:
        return secrets.token_urlsafe(32)

    def _make_access_token(self) -> str:
        return secrets.token_urlsafe(40)

    def _make_refresh_token(self) -> str:
        return secrets.token_urlsafe(40)

    def _make_device_code(self) -> str:
        return secrets.token_urlsafe(48)

    def _make_user_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        return f"{raw[:4]}-{raw[4:]}"

    def _normalize_user_code(self, user_code: str) -> str:
        compact = "".join(ch for ch in str(user_code or "").upper() if ch.isalnum())
        if len(compact) != 8:
            raise HTTPException(status_code=400, detail="invalid user_code")
        return f"{compact[:4]}-{compact[4:]}"

    def _mask_secret(self, secret: str) -> str:
        if len(secret) <= 8:
            return "*" * len(secret)
        return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]

    async def list_apps(self) -> list[dict]:
        rows = await self.db.oauth.list_clients()
        shared_client_id = await self._shared_client_id()
        default_redirect_uri = await self._device_default_redirect_uri()
        for row in rows:
            row["is_device_shared_client"] = bool(shared_client_id and int(row["app_id"]) == int(shared_client_id))
            row["can_use_for_device_flow"] = True
            row["recommended_device_redirect_uri"] = default_redirect_uri
        return rows

    async def create_app(self, client_name: str, redirect_uri: str, set_as_device_shared_client: bool = False) -> dict:
        final_name = (client_name or "").strip()
        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        secret = self._make_secret()
        app_id = await self.db.oauth.create_client(final_name, self._hash_secret(secret), final_redirect_uri)
        if set_as_device_shared_client:
            await self._set_shared_client_id(app_id)
        return {
            "app_id": app_id,
            "client_name": final_name,
            "redirect_uri": final_redirect_uri,
            "client_secret": secret,
            "client_secret_masked": self._mask_secret(secret),
            "is_device_shared_client": bool(set_as_device_shared_client),
        }

    async def update_app(self, app_id: int, client_name: str, redirect_uri: str, set_as_device_shared_client: bool | None = None):
        final_name = (client_name or "").strip()
        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        updated = await self.db.oauth.update_client(app_id, final_name, final_redirect_uri)
        if not updated:
            raise HTTPException(status_code=404, detail="oauth app not found")
        if set_as_device_shared_client is True:
            await self._set_shared_client_id(app_id)
        elif set_as_device_shared_client is False:
            current_shared_client_id = await self._shared_client_id()
            if current_shared_client_id is not None and int(current_shared_client_id) == int(app_id):
                await self._set_shared_client_id(None)
        return {"ok": True}

    async def reset_app_secret(self, app_id: int) -> dict:
        app = await self.db.oauth.get_client(app_id)
        if not app:
            raise HTTPException(status_code=404, detail="oauth app not found")
        secret = self._make_secret()
        await self.db.oauth.update_client_secret(app_id, self._hash_secret(secret))
        return {
            "app_id": app_id,
            "client_secret": secret,
            "client_secret_masked": self._mask_secret(secret),
        }

    async def delete_app(self, app_id: int):
        app = await self.db.oauth.get_client(app_id)
        if not app:
            raise HTTPException(status_code=404, detail="oauth app not found")
        shared_client_id = await self._shared_client_id()
        await self.db.oauth.delete_client(app_id)
        if shared_client_id is not None and int(shared_client_id) == int(app_id):
            await self._set_shared_client_id(None)
        return {"ok": True}

    async def admin_meta(self) -> dict:
        site_url = str(self.config.get("server.site_url", "")).rstrip("/")
        api_url = str(self.config.get("server.api_url", "")).rstrip("/")
        if not api_url:
            root_path = str(self.config.get("server.root_path", "")).rstrip("/")
            if site_url and root_path:
                api_url = site_url + root_path
            elif site_url:
                api_url = site_url
        sample_redirect = "https://your-app.example.com/oauth/callback"
        device_settings = await self._device_settings_payload()
        janus_base_path = await self._janus_base_path()
        janus_issuer = await self._janus_issuer()
        return {
            "authorize_endpoint": f"{site_url}/oauth/authorize" if site_url else "/oauth/authorize",
            "token_endpoint": f"{api_url}/oauth/token" if api_url else "/oauth/token",
            "device_authorization_endpoint": f"{api_url}/oauth/device/code" if api_url else "/oauth/device/code",
            "jwks_uri": f"{api_url}/oauth/jwks" if api_url else "/oauth/jwks",
            "openid_configuration_url": f"{api_url}/.well-known/openid-configuration" if api_url else "/.well-known/openid-configuration",
            "verification_uri": f"{site_url}/device" if site_url else "/device",
            "userinfo_endpoint": f"{api_url}/oauth/userinfo" if api_url else "/oauth/userinfo",
            "permissions_endpoint": f"{api_url}/oauth/permissions" if api_url else "/oauth/permissions",
            "skin_endpoint": f"{api_url}/oauth/skin" if api_url else "/oauth/skin",
            "sample_redirect_uri": sample_redirect,
            "device_settings": device_settings,
            "janus": {
                "enabled": await self._janus_enabled(),
                "base_path": janus_base_path,
                "issuer": janus_issuer,
                "openid_configuration_url": f"{janus_issuer}/.well-known/openid-configuration" if janus_issuer else f"{janus_base_path}/.well-known/openid-configuration",
                "token_endpoint": f"{janus_issuer}/oauth/token" if janus_issuer else f"{janus_base_path}/oauth/token",
                "device_authorization_endpoint": f"{janus_issuer}/oauth/device/code" if janus_issuer else f"{janus_base_path}/oauth/device/code",
                "jwks_uri": f"{janus_issuer}/oauth/jwks" if janus_issuer else f"{janus_base_path}/oauth/jwks",
                "verification_uri": self._verification_uri(),
            },
        }

    async def openid_configuration(self) -> dict:
        issuer = self._issuer()
        if not issuer:
            raise HTTPException(status_code=500, detail="issuer not configured")

        payload = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize/check",
            "device_authorization_endpoint": f"{issuer}/oauth/device/code",
            "token_endpoint": f"{issuer}/oauth/token",
            "jwks_uri": f"{issuer}/oauth/jwks",
            "userinfo_endpoint": f"{issuer}/oauth/userinfo",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:device_code",
            ],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            "claims_supported": ["sub", "preferred_username", "selectedProfile"],
            "scopes_supported": list(self.SUPPORTED_SCOPES.keys()),
        }
        shared_client_id = await self._shared_client_id()
        if shared_client_id is not None:
            payload["shared_client_id"] = str(shared_client_id)
        return payload

    async def janus_openid_configuration(self) -> dict:
        if not await self._janus_enabled():
            raise HTTPException(status_code=404, detail="janus is disabled")

        issuer = await self._janus_issuer()
        payload = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize/check",
            "device_authorization_endpoint": f"{issuer}/oauth/device/code",
            "token_endpoint": f"{issuer}/oauth/token",
            "jwks_uri": f"{issuer}/oauth/jwks",
            "userinfo_endpoint": f"{issuer}/oauth/userinfo",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:device_code",
            ],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            "claims_supported": ["sub", "preferred_username", "selectedProfile"],
            "scopes_supported": list(self.SUPPORTED_SCOPES.keys()),
            "verification_uri": self._verification_uri(),
            "janus_base_path": await self._janus_base_path(),
            "union": await self._janus_union_payload(),
        }
        shared_client_id = await self._shared_client_id()
        if shared_client_id is not None:
            payload["shared_client_id"] = str(shared_client_id)
        return payload

    async def get_admin_device_settings(self) -> dict:
        return await self._device_settings_payload()

    async def save_admin_device_settings(self, body: dict) -> dict:
        shared_client_id = body.get("shared_client_id")
        if shared_client_id in (None, ""):
            await self._set_shared_client_id(None)
        else:
            try:
                final_shared_client_id = int(shared_client_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="shared_client_id invalid")
            app = await self.db.oauth.get_client(final_shared_client_id)
            if not app:
                raise HTTPException(status_code=404, detail="oauth app not found")
            await self._set_shared_client_id(final_shared_client_id)

        expires_in = body.get("expires_in")
        if expires_in is not None:
            try:
                expires_final = max(300, int(expires_in))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="expires_in invalid")
            await self.db.setting.set("oauth_device_expires_in", str(expires_final))

        interval = body.get("interval")
        if interval is not None:
            try:
                interval_final = max(5, int(interval))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="interval invalid")
            await self.db.setting.set("oauth_device_interval", str(interval_final))

        default_redirect_uri = body.get("default_redirect_uri")
        if default_redirect_uri is not None:
            await self.db.setting.set(
                "oauth_device_default_redirect_uri",
                self._normalize_redirect_uri(default_redirect_uri),
            )

        return await self._device_settings_payload()

    def jwks(self) -> dict:
        public_numbers = self.crypto.private_key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self._jwks_kid(),
                    "alg": "RS256",
                    "use": "sig",
                    "n": self._base64url_uint(public_numbers.n),
                    "e": self._base64url_uint(public_numbers.e),
                }
            ]
        }

    async def build_authorize_preview(
        self,
        client_id: int,
        redirect_uri: str,
        state: str = "",
        scope: str = "userinfo",
    ) -> dict:
        app = await self.db.oauth.get_client(client_id)
        if not app:
            raise HTTPException(status_code=400, detail="invalid client_id")

        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        if final_redirect_uri != app["redirect_uri"]:
            raise HTTPException(status_code=400, detail="redirect_uri mismatch")

        normalized_scope, parsed_scopes = self._parse_scope(scope)
        site_name = await self.db.setting.get("site_name", "vSkin")
        site_title = await self.db.setting.get("site_title", site_name or "vSkin")

        return {
            "app_id": app["app_id"],
            "client_name": app["client_name"],
            "requester_name": app["client_name"] or "第三方应用",
            "site_name": site_name or "vSkin",
            "site_title": site_title or site_name or "vSkin",
            "redirect_uri": app["redirect_uri"],
            "state": state or "",
            "scope": normalized_scope,
            "scope_items": self._scope_items(parsed_scopes),
        }

    def _build_redirect(self, redirect_uri: str, params: dict) -> str:
        query = urlencode(params)
        sep = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{sep}{query}"

    def _base64url_uint(self, value: int) -> str:
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    async def _get_client_or_error(self, client_id: int) -> dict:
        app = await self.db.oauth.get_client(client_id)
        if not app:
            raise OAuthProtocolError("invalid_client", "invalid client", status_code=401)
        return app

    async def _require_shared_client(self, client_id: int) -> dict:
        shared_client_id = await self._shared_client_id()
        if shared_client_id is None:
            raise OAuthProtocolError("invalid_client", "shared_client_id is not configured", status_code=503)
        if int(client_id) != int(shared_client_id):
            raise OAuthProtocolError("invalid_client", "client_id does not match shared_client_id", status_code=401)
        return await self._get_client_or_error(client_id)

    def _validate_client_secret(self, app: dict, client_secret: str | None):
        if self._hash_secret(client_secret or "") != app["client_secret_hash"]:
            raise OAuthProtocolError("invalid_client", "invalid client", status_code=401)

    def _build_selected_profile_payload(self, profile) -> dict:
        textures_payload = {
            "timestamp": int(time.time() * 1000),
            "profileId": profile.id,
            "profileName": profile.name,
            "textures": {},
        }

        site_url = self._site_url().rstrip("/")
        base_texture_url = f"{site_url}/static/textures/" if site_url else "/static/textures/"

        if profile.skin_hash:
            textures_payload["textures"]["SKIN"] = {
                "url": base_texture_url + profile.skin_hash + ".png"
            }
            if profile.texture_model == "slim":
                textures_payload["textures"]["SKIN"]["metadata"] = {"model": "slim"}

        if profile.cape_hash:
            textures_payload["textures"]["CAPE"] = {
                "url": base_texture_url + profile.cape_hash + ".png"
            }

        textures_json = json.dumps(textures_payload, separators=(",", ":"))
        textures_base64 = base64.b64encode(textures_json.encode("utf-8")).decode("utf-8")

        properties = [
            {
                "name": "textures",
                "value": textures_base64,
                "signature": self.crypto.sign_data(textures_base64),
            }
        ]
        return {
            "id": profile.id,
            "name": profile.name,
            "properties": properties,
        }

    async def _get_selected_profile_for_user(self, user_id: str):
        profile = await self.db.user.get_active_profile_for_oauth(user_id)
        if not profile:
            raise HTTPException(status_code=400, detail="当前账号没有可用于启动器登录的角色")
        return profile

    async def _issue_tokens(self, app_id: int, user_id: str, scope_text: str) -> dict:
        now = int(time.time())
        access_expires_in = self._access_token_expires_in()
        refresh_expires_in = self._refresh_token_expires_in()
        expires_at_ms = (now + access_expires_in) * 1000
        refresh_expires_at_ms = (now + refresh_expires_in) * 1000

        access_token = self._make_access_token()
        refresh_token = self._make_refresh_token()
        id_token = None

        if self._has_scope(scope_text, "openid"):
            user = await self.db.user.get_by_id(user_id)
            if not user:
                raise HTTPException(status_code=401, detail="user not found")
            profile = await self._get_selected_profile_for_user(user_id)
            id_token = jwt.encode(
                {
                    "iss": self._issuer(),
                    "aud": str(app_id),
                    "sub": user.id,
                    "iat": now,
                    "exp": now + access_expires_in,
                    "preferred_username": user.display_name,
                    "selectedProfile": self._build_selected_profile_payload(profile),
                },
                self.crypto.private_key,
                algorithm="RS256",
                headers={"kid": self._jwks_kid()},
            )

        await self.db.oauth.create_access_token(
            access_token=access_token,
            refresh_token=refresh_token,
            app_id=app_id,
            user_id=user_id,
            scope=scope_text,
            expires_at=expires_at_ms,
            refresh_expires_at=refresh_expires_at_ms,
        )

        payload = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": access_expires_in,
            "refresh_token": refresh_token,
            "scope": scope_text,
        }
        if id_token:
            payload["id_token"] = id_token
        return payload

    async def authorize_decision(
        self,
        user_id: str,
        client_id: int,
        redirect_uri: str,
        state: str,
        approved: bool,
        scope: str = "userinfo",
    ) -> dict:
        app = await self.db.oauth.get_client(client_id)
        if not app:
            raise HTTPException(status_code=400, detail="invalid client_id")

        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        if final_redirect_uri != app["redirect_uri"]:
            raise HTTPException(status_code=400, detail="redirect_uri mismatch")

        if not approved:
            params = {"error": "access_denied"}
            if state:
                params["state"] = state
            return {"redirect_url": self._build_redirect(final_redirect_uri, params)}

        user = await self.db.user.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="user not found")

        normalized_scope, _ = self._parse_scope(scope)

        code = self._make_code()
        now = int(time.time() * 1000)
        expires_at = now + 5 * 60 * 1000
        await self.db.oauth.create_authorization_code(
            code=code,
            app_id=client_id,
            user_id=user_id,
            redirect_uri=final_redirect_uri,
            scope=normalized_scope,
            expires_at=expires_at,
        )

        params = {"code": code}
        if state:
            params["state"] = state
        return {"redirect_url": self._build_redirect(final_redirect_uri, params)}

    async def exchange_code(
        self,
        code: str,
        client_id: int,
        client_secret: str,
        redirect_uri: str,
    ) -> dict:
        app = await self.db.oauth.get_client(client_id)
        if not app:
            raise HTTPException(status_code=400, detail="invalid client")

        if self._hash_secret(client_secret or "") != app["client_secret_hash"]:
            raise HTTPException(status_code=401, detail="invalid client")

        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        auth_code = await self.db.oauth.get_authorization_code(code)
        if not auth_code:
            raise HTTPException(status_code=400, detail="invalid code")
        if auth_code["used"]:
            raise HTTPException(status_code=400, detail="code already used")

        now = int(time.time() * 1000)
        if now > int(auth_code["expires_at"]):
            raise HTTPException(status_code=400, detail="code expired")
        if int(auth_code["app_id"]) != int(client_id):
            raise HTTPException(status_code=400, detail="code client mismatch")
        if auth_code["redirect_uri"] != final_redirect_uri:
            raise HTTPException(status_code=400, detail="redirect_uri mismatch")

        await self.db.oauth.mark_code_used(code)

        return await self._issue_tokens(
            app_id=client_id,
            user_id=auth_code["user_id"],
            scope_text=auth_code.get("scope") or "userinfo",
        )

    async def create_device_authorization(self, client_id: int, scope: str) -> dict:
        app = await self._require_shared_client(client_id)
        normalized_scope, _ = self._parse_scope(
            scope,
            default_scope=self.DEVICE_DEFAULT_SCOPE,
            allowed_scopes=self.DEVICE_SCOPE_KEYS,
        )

        expires_in = await self._device_expires_in()
        interval = await self._device_interval()
        device_code = self._make_device_code()
        user_code = self._make_user_code()
        expires_at = int(time.time() * 1000) + expires_in * 1000
        await self.db.oauth.create_device_code(
            device_code=device_code,
            user_code=user_code,
            app_id=app["app_id"],
            scope=normalized_scope,
            expires_at=expires_at,
            interval_seconds=interval,
        )

        verification_uri = self._verification_uri()
        return {
            "device_code": device_code,
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": f"{verification_uri}?{urlencode({'user_code': user_code})}",
            "expires_in": expires_in,
            "interval": interval,
        }

    async def build_device_preview(self, user_code: str) -> dict:
        normalized_user_code = self._normalize_user_code(user_code)
        record = await self.db.oauth.get_device_code_by_user_code(normalized_user_code)
        if not record:
            raise HTTPException(status_code=404, detail="设备授权码不存在")

        now = int(time.time() * 1000)
        if now > int(record["expires_at"]):
            raise HTTPException(status_code=400, detail="设备授权码已过期")
        if record["status"] == "consumed":
            raise HTTPException(status_code=400, detail="设备授权码已使用")

        app = await self.db.oauth.get_client(int(record["app_id"]))
        if not app:
            raise HTTPException(status_code=404, detail="OAuth 应用不存在")

        site_name = await self.db.setting.get("site_name", "vSkin")
        site_title = await self.db.setting.get("site_title", site_name or "vSkin")
        _, parsed_scopes = self._parse_scope(
            record.get("scope") or self.DEVICE_DEFAULT_SCOPE,
            default_scope=self.DEVICE_DEFAULT_SCOPE,
            allowed_scopes=self.DEVICE_SCOPE_KEYS,
        )
        return {
            "user_code": normalized_user_code,
            "status": record["status"],
            "requester_name": app["client_name"] or "授权设备",
            "client_name": app["client_name"],
            "site_name": site_name or "vSkin",
            "site_title": site_title or site_name or "vSkin",
            "scope": record.get("scope") or self.DEVICE_DEFAULT_SCOPE,
            "scope_items": self._scope_items(parsed_scopes),
            "expires_at": record["expires_at"],
            "expires_in": max(0, int((int(record["expires_at"]) - now) / 1000)),
        }

    async def decide_device_authorization(self, user_id: str, user_code: str, approved: bool) -> dict:
        normalized_user_code = self._normalize_user_code(user_code)
        record = await self.db.oauth.get_device_code_by_user_code(normalized_user_code)
        if not record:
            raise HTTPException(status_code=404, detail="设备授权码不存在")

        now = int(time.time() * 1000)
        if now > int(record["expires_at"]):
            raise HTTPException(status_code=400, detail="设备授权码已过期")
        if record["status"] not in {"pending", "approved"}:
            raise HTTPException(status_code=400, detail="设备授权状态不可变更")

        if approved:
            user = await self.db.user.get_by_id(user_id)
            if not user:
                raise HTTPException(status_code=401, detail="user not found")
            await self._get_selected_profile_for_user(user_id)
            await self.db.oauth.approve_device_code(record["device_code"], user_id, now)
            return {"ok": True, "status": "approved"}

        await self.db.oauth.deny_device_code(record["device_code"], now)
        return {"ok": True, "status": "denied"}

    async def exchange_device_code(self, client_id: int, device_code: str) -> dict:
        await self._require_shared_client(client_id)
        record = await self.db.oauth.get_device_code(device_code)
        if not record or int(record["app_id"]) != int(client_id):
            raise OAuthProtocolError("expired_token", "device_code is invalid or expired")

        now = int(time.time() * 1000)
        if now > int(record["expires_at"]):
            raise OAuthProtocolError("expired_token", "device_code expired")

        status = record.get("status")
        if status == "pending":
            next_allowed = record.get("next_allowed_poll_at")
            if next_allowed and now < int(next_allowed):
                raise OAuthProtocolError("slow_down", "polling too fast")

            await self.db.oauth.update_device_poll(
                device_code=device_code,
                last_polled_at=now,
                next_allowed_poll_at=now + int(record["interval_seconds"]) * 1000,
            )

        if status == "pending":
            raise OAuthProtocolError("authorization_pending", "authorization pending")
        if status == "denied":
            raise OAuthProtocolError("access_denied", "authorization denied")
        if status == "consumed":
            raise OAuthProtocolError("expired_token", "device_code already consumed")
        if status != "approved" or not record.get("user_id"):
            raise OAuthProtocolError("authorization_pending", "authorization pending")

        payload = await self._issue_tokens(
            app_id=int(record["app_id"]),
            user_id=record["user_id"],
            scope_text=record.get("scope") or self.DEVICE_DEFAULT_SCOPE,
        )
        await self.db.oauth.consume_device_code(device_code, now)
        return payload

    async def refresh_token(self, client_id: int, refresh_token: str, client_secret: str | None = None) -> dict:
        app = await self.db.oauth.get_client(client_id)
        if not app:
            raise OAuthProtocolError("invalid_client", "invalid client", status_code=401)

        shared_client_id = await self._shared_client_id()
        if shared_client_id is None or int(client_id) != int(shared_client_id):
            self._validate_client_secret(app, client_secret)

        record = await self.db.oauth.get_refresh_token(refresh_token)
        if not record:
            raise OAuthProtocolError("invalid_grant", "refresh_token is invalid")
        if int(record["app_id"]) != int(client_id):
            raise OAuthProtocolError("invalid_grant", "refresh_token client mismatch")

        now = int(time.time() * 1000)
        if now > int(record.get("refresh_expires_at") or 0):
            await self.db.oauth.delete_refresh_token(refresh_token)
            raise OAuthProtocolError("invalid_grant", "refresh_token expired")

        await self.db.oauth.delete_refresh_token(refresh_token)
        return await self._issue_tokens(
            app_id=client_id,
            user_id=record["user_id"],
            scope_text=record.get("scope") or "userinfo",
        )

    async def token_endpoint(
        self,
        grant_type: str,
        code: str | None = None,
        client_id: int | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        device_code: str | None = None,
        refresh_token: str | None = None,
    ) -> dict:
        if grant_type == "authorization_code":
            if client_id is None or not code or not client_secret or not redirect_uri:
                raise HTTPException(status_code=400, detail="code, client_id, client_secret and redirect_uri required")
            return await self.exchange_code(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )

        if grant_type == "urn:ietf:params:oauth:grant-type:device_code":
            if client_id is None or not device_code:
                raise OAuthProtocolError("invalid_request", "client_id and device_code required")
            return await self.exchange_device_code(client_id=client_id, device_code=device_code)

        if grant_type == "refresh_token":
            if client_id is None or not refresh_token:
                raise OAuthProtocolError("invalid_request", "client_id and refresh_token required")
            return await self.refresh_token(
                client_id=client_id,
                refresh_token=refresh_token,
                client_secret=client_secret,
            )

        raise OAuthProtocolError("unsupported_grant_type", "unsupported grant_type")

    async def _resolve_token_and_user(self, access_token: str) -> tuple[dict, object]:
        record = await self.db.oauth.get_access_token(access_token)
        if not record:
            raise HTTPException(status_code=401, detail="invalid token")

        now = int(time.time() * 1000)
        if now > int(record["expires_at"]):
            raise HTTPException(status_code=401, detail="token expired")

        user = await self.db.user.get_by_id(record["user_id"])
        if not user:
            raise HTTPException(status_code=401, detail="invalid token")

        return record, user

    async def get_userinfo(self, access_token: str) -> dict:
        record, user = await self._resolve_token_and_user(access_token)
        scope_text = record.get("scope") or "userinfo"
        payload = {
            "sub": user.id,
            "app_id": record["app_id"],
            "scope": scope_text,
        }

        if self._has_scope(scope_text, "userinfo") or self._has_scope(scope_text, "profile"):
            payload["username"] = user.display_name
            payload["display_name"] = user.display_name

        if self._has_scope(scope_text, "userinfo") or self._has_scope(scope_text, "avatar"):
            payload["avatar_url"] = self._avatar_url_from_hash(user.avatar_hash)

        if self._has_scope(scope_text, "email"):
            payload["email"] = user.email

        if self._has_scope(scope_text, "permission"):
            user_group = resolve_user_group(getattr(user, "user_group", None), user.is_admin)
            payload["user_group"] = user_group
            payload["user_group_meta"] = get_user_group_meta(user_group)
            payload["is_admin"] = bool(is_admin_group(user_group))

        return payload

    async def get_permissions_info(self, access_token: str) -> dict:
        record, user = await self._resolve_token_and_user(access_token)
        scope_text = record.get("scope") or "userinfo"
        if not self._has_scope(scope_text, "permission"):
            raise HTTPException(status_code=403, detail="missing permission scope")

        user_group = resolve_user_group(getattr(user, "user_group", None), user.is_admin)
        return {
            "sub": user.id,
            "user_group": user_group,
            "user_group_meta": get_user_group_meta(user_group),
            "is_admin": bool(is_admin_group(user_group)),
            "scope": scope_text,
        }

    async def get_profile_info(self, access_token: str) -> dict:
        record, user = await self._resolve_token_and_user(access_token)
        scope_text = record.get("scope") or "userinfo"
        if not (self._has_scope(scope_text, "userinfo") or self._has_scope(scope_text, "profile")):
            raise HTTPException(status_code=403, detail="missing profile scope")
        return {
            "sub": user.id,
            "username": user.display_name,
            "display_name": user.display_name,
            "scope": scope_text,
        }

    async def get_avatar_info(self, access_token: str) -> dict:
        record, user = await self._resolve_token_and_user(access_token)
        scope_text = record.get("scope") or "userinfo"
        if not (self._has_scope(scope_text, "userinfo") or self._has_scope(scope_text, "avatar")):
            raise HTTPException(status_code=403, detail="missing avatar scope")
        return {
            "sub": user.id,
            "avatar_url": self._avatar_url_from_hash(user.avatar_hash),
            "scope": scope_text,
        }

    async def get_email_info(self, access_token: str) -> dict:
        record, user = await self._resolve_token_and_user(access_token)
        scope_text = record.get("scope") or "userinfo"
        if not self._has_scope(scope_text, "email"):
            raise HTTPException(status_code=403, detail="missing email scope")
        return {
            "sub": user.id,
            "email": user.email,
            "scope": scope_text,
        }

    async def get_skin_info(self, access_token: str) -> dict:
        record, user = await self._resolve_token_and_user(access_token)
        scope_text = record.get("scope") or "userinfo"
        if not self._has_scope(scope_text, "skin"):
            raise HTTPException(status_code=403, detail="missing skin scope")

        profile = await self.db.user.get_active_profile_for_oauth(user.id)
        if not profile:
            raise HTTPException(status_code=404, detail="profile not found")
        if not profile.skin_hash:
            raise HTTPException(status_code=404, detail="skin not found")

        file_path = self._texture_file_path(profile.skin_hash)
        if not file_path:
            raise HTTPException(status_code=404, detail="skin file not found")

        return {
            "path": file_path,
            "skin_hash": profile.skin_hash,
            "skin_url": self._skin_url_from_hash(profile.skin_hash),
            "profile_id": profile.id,
            "profile_name": profile.name,
            "model": profile.texture_model,
            "scope": scope_text,
        }
