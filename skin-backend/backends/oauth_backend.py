import hashlib
import secrets
import time
from urllib.parse import urlencode

from fastapi import HTTPException

from config_loader import Config
from database_module import Database


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
    }

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def _site_url(self) -> str:
        return str(self.config.get("server.site_url", "")).rstrip("/")

    def _api_url(self) -> str:
        api_url = str(self.config.get("server.api_url", "")).rstrip("/")
        if api_url:
            return api_url
        site = self._site_url()
        root_path = str(self.config.get("server.root_path", "")).rstrip("/")
        if site and root_path:
            return site + root_path
        return site

    def _avatar_url_from_hash(self, avatar_hash: str | None) -> str:
        site = self._site_url()
        if avatar_hash:
            path = f"/static/textures/{avatar_hash}.png"
            return f"{site}{path}" if site else path
        path = "/public/default-avatar"
        api_url = self._api_url()
        return f"{api_url}{path}" if api_url else path

    def _parse_scope(self, scope: str) -> tuple[str, list[str]]:
        raw = (scope or "userinfo").replace(",", " ")
        chunks = [x.strip() for x in raw.split(" ") if x.strip()]
        if not chunks:
            chunks = ["userinfo"]

        result: list[str] = []
        for item in chunks:
            if item == "basic":
                item = "userinfo"
            if item not in self.SUPPORTED_SCOPES:
                raise HTTPException(status_code=400, detail=f"unsupported scope: {item}")
            if item not in result:
                result.append(item)
        return " ".join(result), result

    def _scope_items(self, scopes: list[str]) -> list[dict]:
        items = []
        for key in scopes:
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

    def _mask_secret(self, secret: str) -> str:
        if len(secret) <= 8:
            return "*" * len(secret)
        return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]

    async def list_apps(self) -> list[dict]:
        rows = await self.db.oauth.list_clients()
        return rows

    async def create_app(self, client_name: str, redirect_uri: str) -> dict:
        final_name = (client_name or "").strip()
        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        secret = self._make_secret()
        app_id = await self.db.oauth.create_client(final_name, self._hash_secret(secret), final_redirect_uri)
        return {
            "app_id": app_id,
            "client_name": final_name,
            "redirect_uri": final_redirect_uri,
            "client_secret": secret,
            "client_secret_masked": self._mask_secret(secret),
        }

    async def update_app(self, app_id: int, client_name: str, redirect_uri: str):
        final_name = (client_name or "").strip()
        final_redirect_uri = self._normalize_redirect_uri(redirect_uri)
        updated = await self.db.oauth.update_client(app_id, final_name, final_redirect_uri)
        if not updated:
            raise HTTPException(status_code=404, detail="oauth app not found")
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
        await self.db.oauth.delete_client(app_id)
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
        return {
            "authorize_endpoint": f"{site_url}/oauth/authorize" if site_url else "/oauth/authorize",
            "token_endpoint": f"{api_url}/oauth/token" if api_url else "/oauth/token",
            "userinfo_endpoint": f"{api_url}/oauth/userinfo" if api_url else "/oauth/userinfo",
            "sample_redirect_uri": sample_redirect,
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

        return {
            "app_id": app["app_id"],
            "client_name": app["client_name"],
            "requester_name": app["client_name"] or "第三方应用",
            "site_name": site_name or "vSkin",
            "redirect_uri": app["redirect_uri"],
            "state": state or "",
            "scope": normalized_scope,
            "scope_items": self._scope_items(parsed_scopes),
        }

    def _build_redirect(self, redirect_uri: str, params: dict) -> str:
        query = urlencode(params)
        sep = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{sep}{query}"

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
        grant_type: str,
        code: str,
        client_id: int,
        client_secret: str,
        redirect_uri: str,
    ) -> dict:
        if grant_type != "authorization_code":
            raise HTTPException(status_code=400, detail="unsupported grant_type")

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

        access_token = self._make_access_token()
        refresh_token = self._make_refresh_token()
        expires_in = 7200
        expires_at = now + expires_in * 1000
        await self.db.oauth.create_access_token(
            access_token=access_token,
            refresh_token=refresh_token,
            app_id=client_id,
            user_id=auth_code["user_id"],
            scope=auth_code.get("scope") or "userinfo",
            expires_at=expires_at,
        )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token,
            "scope": auth_code.get("scope") or "userinfo",
        }

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

        return payload

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
