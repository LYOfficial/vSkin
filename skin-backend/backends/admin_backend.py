from typing import Any, List, Dict
import time
import secrets
import os
import re
import uuid
from fastapi import HTTPException

from utils.typing import InviteCode
from utils.user_groups import (
    SUPER_ADMIN_GROUP,
    ADMIN_GROUP,
    USER_GROUP,
    resolve_user_group,
    is_admin_group,
    can_grant_admin,
    get_user_group_meta,
    normalize_user_group,
)
from database_module import Database
from config_loader import Config

class AdminBackend:
    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    def _avatar_url_from_hash(self, avatar_hash: str | None) -> str:
        if avatar_hash:
            return f"/static/textures/{avatar_hash}.png"
        return "/public/default-avatar"

    # ========== Settings Management (Granular) ==========

    async def get_site_settings(self):
        s = await self.db.setting.get_all()
        raw_suffixes = s.get("register_email_suffixes", "")
        if isinstance(raw_suffixes, list):
            register_email_suffixes = [str(item).strip() for item in raw_suffixes if str(item).strip()]
        else:
            register_email_suffixes = [
                item.strip()
                for item in str(raw_suffixes or "").replace("\n", ",").split(",")
                if item.strip()
            ]
        return {
            "site_name": s.get("site_name", "皮肤站"),
            "site_title": s.get("site_title", s.get("site_name", "皮肤站")),
            "site_logo": s.get("site_logo", ""),
            "site_subtitle": s.get("site_subtitle", "简洁、高效、现代的 Minecraft 皮肤管理站"),
            "home_image_urls": s.get("home_image_urls", ""),
            "require_invite": s.get("require_invite", "false") == "true",
            "allow_register": s.get("allow_register", "true") == "true",
            "register_email_suffixes": register_email_suffixes,
            "enable_skin_library": s.get("enable_skin_library", "true") == "true",
            "max_texture_size": int(s.get("max_texture_size", "1024")),
            "footer_text": s.get("footer_text", ""),
            "filing_icp": s.get("filing_icp", ""),
            "filing_icp_link": s.get("filing_icp_link", ""),
            "filing_mps": s.get("filing_mps", ""),
            "filing_mps_link": s.get("filing_mps_link", ""),
        }

    async def get_security_settings(self):
        s = await self.db.setting.get_all()
        return {
            "rate_limit_enabled": s.get("rate_limit_enabled", "true") == "true",
            "rate_limit_auth_attempts": int(s.get("rate_limit_auth_attempts", "5")),
            "rate_limit_auth_window": int(s.get("rate_limit_auth_window", "15")),
            "enable_strong_password_check": s.get("enable_strong_password_check", "false") == "true",
        }

    async def get_auth_settings(self):
        s = await self.db.setting.get_all()
        return {
            "jwt_expire_days": int(s.get("jwt_expire_days", "7")),
        }

    async def get_microsoft_settings(self):
        s = await self.db.setting.get_all()
        return {
            "microsoft_client_id": s.get("microsoft_client_id", ""),
            "microsoft_client_secret": s.get("microsoft_client_secret", ""),
            "microsoft_redirect_uri": s.get("microsoft_redirect_uri", ""),
        }

    async def get_email_settings(self):
        s = await self.db.setting.get_all()
        return {
            "email_verify_enabled": s.get("email_verify_enabled", "false") == "true",
            "email_verify_ttl": int(s.get("email_verify_ttl", "300")),
            "smtp_host": s.get("smtp_host", ""),
            "smtp_port": int(s.get("smtp_port", "465")),
            "smtp_user": s.get("smtp_user", ""),
            "smtp_ssl": s.get("smtp_ssl", "true") == "true",
            "smtp_sender": s.get("smtp_sender", ""),
            "email_template_html": s.get("email_template_html", ""),
        }

    async def get_janus_settings(self):
        s = await self.db.setting.get_all()
        base_path = str(s.get("janus_base_path", "/api/janus") or "/api/janus").strip()
        if not base_path.startswith("/"):
            base_path = "/" + base_path
        if len(base_path) > 1:
            base_path = base_path.rstrip("/")

        union_mode = str(s.get("janus_union_mode", "all") or "all").strip().lower()
        if union_mode not in {"all", "only", "excludes"}:
            union_mode = "all"

        return {
            "janus_enabled": s.get("janus_enabled", "true") == "true",
            "janus_base_path": base_path,
            "janus_issuer": s.get("janus_issuer", ""),
            "janus_union_api_base": s.get("janus_union_api_base", "https://skin.mualliance.ltd/api/union"),
            "janus_union_mode": union_mode,
            "janus_union_code": s.get("janus_union_code", ""),
            "janus_union_auto_sync": s.get("janus_union_auto_sync", "false") == "true",
        }

    async def get_fallback_settings(self):
        s = await self.db.setting.get_all()
        return {
            "fallback_strategy": s.get("fallback_strategy", "serial"),
            "fallbacks": await self.db.fallback.list_endpoints(),
        }

    async def save_settings_group(self, group: str, body: dict):
        allowed_keys = {
            "site": [
                "site_name",
                "site_title",
                "site_logo",
                "site_subtitle",
                "home_image_urls",
                "require_invite",
                "allow_register",
                "register_email_suffixes",
                "enable_skin_library",
                "max_texture_size",
                "footer_text",
                "filing_icp",
                "filing_icp_link",
                "filing_mps",
                "filing_mps_link",
            ],
            "security": ["rate_limit_enabled", "rate_limit_auth_attempts", "rate_limit_auth_window", "enable_strong_password_check"],
            "auth": ["jwt_expire_days"],
            "microsoft": ["microsoft_client_id", "microsoft_client_secret", "microsoft_redirect_uri"],
            "email": ["email_verify_enabled", "email_verify_ttl", "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_ssl", "smtp_sender", "email_template_html"],
            "fallback": ["fallback_strategy"],
            "janus": [
                "janus_enabled",
                "janus_base_path",
                "janus_issuer",
                "janus_union_api_base",
                "janus_union_mode",
                "janus_union_code",
                "janus_union_auto_sync",
            ],
        }
        
        if group not in allowed_keys and group != "fallback_endpoints":
            raise HTTPException(status_code=400, detail="Invalid settings group")

        if group == "fallback_endpoints":
            if "fallbacks" in body:
                fallbacks = self._validate_fallback_services(body.get("fallbacks"))
                await self.db.fallback.save_endpoints(fallbacks)
            return

        for key in allowed_keys[group]:
            if key in body:
                val = body[key]
                # Special handling for password
                if key == "smtp_password" and not val:
                    continue

                if key == "site_title":
                    val = str(val or "").strip() or str(body.get("site_name") or "").strip() or "皮肤站"

                if key == "home_image_urls":
                    if isinstance(val, list):
                        val = "\n".join(str(item).strip() for item in val if str(item).strip())
                    else:
                        val = "\n".join(
                            line.strip()
                            for line in str(val or "").splitlines()
                            if line.strip()
                        )

                if key == "register_email_suffixes":
                    if isinstance(val, list):
                        parts = [str(item).strip() for item in val if str(item).strip()]
                    else:
                        parts = [
                            item.strip()
                            for item in str(val or "").replace("\n", ",").split(",")
                            if item.strip()
                        ]
                    val = ",".join(parts)

                if key == "janus_base_path":
                    val = str(val or "/api/janus").strip() or "/api/janus"
                    if not val.startswith("/"):
                        val = "/" + val
                    if len(val) > 1:
                        val = val.rstrip("/")

                if key == "janus_union_mode":
                    mode = str(val or "all").strip().lower()
                    if mode not in {"all", "only", "excludes"}:
                        raise HTTPException(status_code=400, detail="janus_union_mode must be all/only/excludes")
                    val = mode

                if key in {"janus_issuer", "janus_union_api_base"}:
                    val = str(val or "").strip()
                
                value = "true" if isinstance(val, bool) and val else ("false" if isinstance(val, bool) else str(val))
                await self.db.setting.set(key, value)
        
        # If fallback strategy was saved, update endpoints if they were also passed (though we prefer separate)
        if group == "fallback" and "fallbacks" in body:
            fallbacks = self._validate_fallback_services(body.get("fallbacks"))
            await self.db.fallback.save_endpoints(fallbacks)

    # ========== Legacy compatibility (can be removed later) ==========

    async def get_admin_settings(self):
        site = await self.get_site_settings()
        sec = await self.get_security_settings()
        auth = await self.get_auth_settings()
        ms = await self.get_microsoft_settings()
        janus = await self.get_janus_settings()
        fallback = await self.get_fallback_settings()
        email = await self.get_email_settings()
        return {**site, **sec, **auth, **ms, **janus, **fallback, **email}

    async def save_admin_settings(self, body: dict):
        # Determine which groups are present and save them
        for group in ["site", "security", "auth", "microsoft", "janus", "email", "fallback"]:
            await self.save_settings_group(group, body)
        if "fallbacks" in body:
            await self.save_settings_group("fallback_endpoints", body)

    # ========== Other Methods ==========

    def _validate_fallback_services(self, services: Any) -> list[dict]:
        if not isinstance(services, list):
            raise HTTPException(status_code=400, detail="fallbacks must be a list")

        normalized: list[dict] = []
        for idx, entry in enumerate(services, start=1):
            if not isinstance(entry, dict):
                raise HTTPException(status_code=400, detail="invalid fallback entry")

            endpoint_id = entry.get("id")
            if endpoint_id is not None:
                try:
                    endpoint_id = int(endpoint_id)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"fallback[{idx}] id invalid")
            
            session_url = str(entry.get("session_url", "")).strip()
            account_url = str(entry.get("account_url", "")).strip()
            services_url = str(entry.get("services_url", "")).strip()
            cache_ttl = entry.get("cache_ttl", 60)
            raw_domains = entry.get("skin_domains", "")
            
            if not session_url or not account_url or not services_url:
                raise HTTPException(status_code=400, detail=f"fallback[{idx}] urls are required")

            if isinstance(raw_domains, list):
                skin_domains = [str(item).strip() for item in raw_domains if str(item).strip()]
            else:
                skin_domains = [item.strip() for item in str(raw_domains).split(",") if item.strip()]
            
            try:
                cache_ttl = int(cache_ttl)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"fallback[{idx}] cache_ttl invalid")
            
            if cache_ttl < 0:
                raise HTTPException(status_code=400, detail=f"fallback[{idx}] cache_ttl must be non-negative")

            normalized.append({
                "id": endpoint_id,
                "session_url": session_url,
                "account_url": account_url,
                "services_url": services_url,
                "cache_ttl": cache_ttl,
                "skin_domains": ",".join(skin_domains),
                "enable_profile": bool(entry.get("enable_profile", True)),
                "enable_hasjoined": bool(entry.get("enable_hasjoined", True)),
                "enable_whitelist": bool(entry.get("enable_whitelist", False)),
                "note": str(entry.get("note", "")).strip(),
            })
        return normalized

    async def get_admin_users(self):
        users = await self.db.user.list_users(limit=1000, offset=0)
        result = []
        for row in users:
            profile_count = await self.db.user.count_profiles_by_user(row.id)
            user_group = resolve_user_group(getattr(row, "user_group", None), row.is_admin)
            result.append({
                "id": row.id,
                "email": row.email,
                "display_name": row.display_name or "",
                "avatar_url": self._avatar_url_from_hash(row.avatar_hash),
                "is_admin": bool(is_admin_group(user_group)),
                "user_group": user_group,
                "user_group_meta": get_user_group_meta(user_group),
                "banned_until": row.banned_until,
                "profile_count": profile_count,
            })
        return result

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        user_row = await self.db.user.get_by_id(user_id)
        if not user_row:
            raise HTTPException(status_code=404, detail="user not found")

        profiles = await self.db.user.get_profiles_by_user(user_id)
        profiles_list = [
            {
                "id": p.id,
                "name": p.name,
                "model": p.texture_model,
                "skin_hash": p.skin_hash,
                "cape_hash": p.cape_hash,
            }
            for p in profiles
        ]

        user_group = resolve_user_group(getattr(user_row, "user_group", None), user_row.is_admin)
        return {
            "id": user_row.id,
            "email": user_row.email,
            "lang": user_row.preferredLanguage,
            "display_name": user_row.display_name,
            "avatar_url": self._avatar_url_from_hash(user_row.avatar_hash),
            "is_admin": bool(is_admin_group(user_group)),
            "user_group": user_group,
            "user_group_meta": get_user_group_meta(user_group),
            "banned_until": user_row.banned_until,
            "profiles": profiles_list,
        }

    async def toggle_user_admin(self, user_id: str, actor_id: str):
        if actor_id == user_id:
            raise HTTPException(status_code=403, detail="cannot change own admin status")

        actor = await self.db.user.get_by_id(actor_id)
        if not actor:
            raise HTTPException(status_code=401, detail="actor not found")
        actor_group = resolve_user_group(getattr(actor, "user_group", None), actor.is_admin)
        if not can_grant_admin(actor_group):
            raise HTTPException(status_code=403, detail="only super admin can change admin group")

        target = await self.db.user.get_by_id(user_id)
        if not target:
            raise HTTPException(status_code=404, detail="user not found")
        target_group = resolve_user_group(getattr(target, "user_group", None), target.is_admin)

        if target_group == SUPER_ADMIN_GROUP:
            raise HTTPException(status_code=403, detail="cannot change super admin group")

        next_group = USER_GROUP if is_admin_group(target_group) else ADMIN_GROUP
        ok = await self.db.user.set_user_group(user_id, next_group)
        if not ok:
            raise HTTPException(status_code=404, detail="user not found")

    async def set_user_group(self, user_id: str, actor_id: str, user_group: str):
        actor = await self.db.user.get_by_id(actor_id)
        if not actor:
            raise HTTPException(status_code=401, detail="actor not found")
        actor_group = resolve_user_group(getattr(actor, "user_group", None), actor.is_admin)

        target = await self.db.user.get_by_id(user_id)
        if not target:
            raise HTTPException(status_code=404, detail="user not found")
        target_group = resolve_user_group(getattr(target, "user_group", None), target.is_admin)

        desired_group = normalize_user_group(user_group)

        # 特例：允许超级管理员将自己再次设置为超级管理员，用于权限刷新
        if actor_id == user_id:
            if actor_group == SUPER_ADMIN_GROUP and desired_group == SUPER_ADMIN_GROUP:
                ok = await self.db.user.set_user_group(user_id, SUPER_ADMIN_GROUP)
                if not ok:
                    raise HTTPException(status_code=404, detail="user not found")
                return
            raise HTTPException(status_code=403, detail="cannot change own user group")

        if target_group == SUPER_ADMIN_GROUP:
            raise HTTPException(status_code=403, detail="cannot change super admin group")

        if desired_group == SUPER_ADMIN_GROUP:
            raise HTTPException(status_code=403, detail="cannot assign super admin group")

        if desired_group == ADMIN_GROUP and not can_grant_admin(actor_group):
            raise HTTPException(status_code=403, detail="only super admin can assign admin group")

        ok = await self.db.user.set_user_group(user_id, desired_group)
        if not ok:
            raise HTTPException(status_code=404, detail="user not found")

    async def delete_user(self, user_id: str, is_admin_action=False):
        user_row = await self.db.user.get_by_id(user_id)
        if not user_row:
            raise HTTPException(status_code=404, detail="user not found")
        user_group = resolve_user_group(getattr(user_row, "user_group", None), user_row.is_admin)
        if user_group == SUPER_ADMIN_GROUP and is_admin_action:
            raise HTTPException(status_code=403, detail="cannot delete super admin user")
        await self.db.user.delete(user_id)
        return True

    async def ban_user(self, user_id, banned_until, actor_id):
        user_row = await self.db.user.get_by_id(user_id)
        if not user_row:
            raise HTTPException(status_code=404, detail="user not found")
        user_group = resolve_user_group(getattr(user_row, "user_group", None), user_row.is_admin)
        if user_group == SUPER_ADMIN_GROUP:
            raise HTTPException(status_code=403, detail="cannot ban super admin user")
        await self.db.user.ban(user_id, banned_until)
        return banned_until

    async def reset_user_password(self, user_id: str, new_password: str):
        from utils.password_utils import hash_password
        user_row = await self.db.user.get_by_id(user_id)
        if not user_row:
            raise HTTPException(status_code=404, detail="user not found")
        
        password_hash = hash_password(new_password)
        await self.db.user.update_password(user_id, password_hash)
        return {"ok": True}

    async def create_invite(self, code, total_uses, note: str = ""):
        if code:
            if not (6 <= len(code) <= 32) or not re.match(r"^[a-zA-Z0-9_-]+$", code):
                raise HTTPException(status_code=400, detail="Invalid code format")
        else:
            code = secrets.token_urlsafe(16)

        if await self.db.user.get_invite(code):
            raise HTTPException(status_code=400, detail="invite code already exists")

        await self.db.user.create_invite(InviteCode(code, int(time.time() * 1000), total_uses=total_uses, note=note))
        return code

    async def upload_carousel_image(self, filename: str, content: bytes):
        directory = self.config.get("carousel.directory", "carousel")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, filename), "wb") as f:
            f.write(content)
        return {"filename": filename}

    async def upload_site_logo(self, original_filename: str, content: bytes):
        extension = os.path.splitext(original_filename)[1].lower()
        if extension not in [".png", ".jpg", ".jpeg", ".webp", ".ico", ".svg"]:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        directory = self.config.get("textures.directory", "textures")
        os.makedirs(directory, exist_ok=True)

        previous_logo = await self.db.setting.get("site_logo", "")
        filename = f"site-logo-{uuid.uuid4().hex}{extension}"
        with open(os.path.join(directory, filename), "wb") as f:
            f.write(content)

        await self.db.setting.set("site_logo", f"/static/textures/{filename}")

        if previous_logo.startswith("/static/textures/site-logo-"):
            previous_name = os.path.basename(previous_logo)
            previous_path = os.path.join(directory, previous_name)
            if os.path.dirname(os.path.abspath(previous_path)) == os.path.abspath(directory) and os.path.exists(previous_path):
                try:
                    os.remove(previous_path)
                except OSError:
                    pass

        return {"path": f"/static/textures/{filename}"}

    async def delete_carousel_image(self, filename: str):
        directory = self.config.get("carousel.directory", "carousel")
        file_path = os.path.join(directory, filename)
        if os.path.dirname(os.path.abspath(file_path)) != os.path.abspath(directory):
            raise HTTPException(status_code=400, detail="Invalid filename")
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"ok": True}
        raise HTTPException(status_code=404, detail="File not found")

    async def get_official_whitelist(self, endpoint_id: int):
        return await self.db.fallback.list_whitelist_users(endpoint_id)

    async def add_official_whitelist_user(self, username: str, endpoint_id: int):
        if not username:
            raise HTTPException(status_code=400, detail="username required")
        await self.db.fallback.add_whitelist_user(username, endpoint_id)
        return {"ok": True}

    async def remove_official_whitelist_user(self, username: str, endpoint_id: int):
        if not username:
            raise HTTPException(status_code=400, detail="username required")
        await self.db.fallback.remove_whitelist_user(username, endpoint_id)
        return {"ok": True}
