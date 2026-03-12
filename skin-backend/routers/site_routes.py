"""皮肤站主模块路由（用户、公共设置、材质等）"""

from fastapi import (
    APIRouter,
    Request,
    HTTPException,
    Depends,
    Body,
    UploadFile,
    File,
    Form,
    Query,
)
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from utils.image_utils import default_steve_head_avatar

from utils.jwt_utils import decode_jwt_token
from database_module import Database
from config_loader import Config

router = APIRouter()
security = HTTPBearer()


def setup_routes(db: Database, site_backend, oauth_backend, rate_limiter, config: Config):
    """设置路由（注入依赖）"""

    def get_oauth_bearer_token(request: Request) -> str:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        access_token = auth_header[7:].strip()
        if not access_token:
            raise HTTPException(status_code=401, detail="missing bearer token")
        return access_token

    async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
        token = creds.credentials
        payload = decode_jwt_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        return payload

    @router.post("/site-login")
    async def site_login(req: dict, request: Request):
        await rate_limiter.check(request, is_auth_endpoint=True)
        result = await site_backend.login(req.get("email"), req.get("password"))
        rate_limiter.reset(request.client.host, request.url.path)
        return result

    @router.post("/register")
    async def register(req: dict, request: Request):
        await rate_limiter.check(request, is_auth_endpoint=True)

        email = req.get("email")
        password = req.get("password")
        username = req.get("username")
        invite = req.get("invite")
        code = req.get("code")

        if not email or not password or not username:
            raise HTTPException(status_code=400, detail="email, password and username required")

        user_id = await site_backend.register(email, password, username, invite, code)
        return {"id": user_id}

    @router.post("/send-verification-code")
    async def send_code(req: dict, request: Request):
        # Using auth endpoint rate limit for code sending
        await rate_limiter.check(request, is_auth_endpoint=True)
        email = req.get("email")
        type = req.get("type", "register") # register or reset
        if not email:
            raise HTTPException(status_code=400, detail="email required")
        return await site_backend.send_verification_code(email, type)

    @router.post("/reset-password")
    async def reset_password(req: dict, request: Request):
        await rate_limiter.check(request, is_auth_endpoint=True)
        email = req.get("email")
        password = req.get("password")
        code = req.get("code")
        if not email or not password or not code:
            raise HTTPException(status_code=400, detail="email, password and code required")
        await site_backend.reset_password(email, password, code)
        return {"ok": True}

    @router.get("/me")
    async def me(payload: dict = Depends(get_current_user)):
        return await site_backend.get_user_info(payload.get("sub"))

    @router.post("/me/avatar/from-texture")
    async def me_set_avatar_from_texture(
        payload: dict = Depends(get_current_user),
        body: dict = Body(...),
    ):
        texture_hash = body.get("hash")
        return await site_backend.set_avatar_from_texture(payload.get("sub"), texture_hash)

    @router.post("/me/refresh-token")
    async def refresh_jwt(payload: dict = Depends(get_current_user)):
        return await site_backend.refresh_token(payload.get("sub"))

    @router.patch("/me")
    async def me_update(
        payload: dict = Depends(get_current_user), body: dict = Body(...)
    ):
        await site_backend.update_user_info(payload.get("sub"), body)
        return {"ok": True}

    @router.delete("/me")
    async def delete_me(payload: dict = Depends(get_current_user)):
        await site_backend.delete_user(payload.get("sub"), is_admin_action=False)
        return {"ok": True}

    @router.post("/me/password")
    async def change_password(
        payload: dict = Depends(get_current_user), body: dict = Body(...)
    ):
        await site_backend.change_password(
            payload.get("sub"), body.get("old_password"), body.get("new_password")
        )
        return {"ok": True, "message": "密码修改成功"}

    @router.post("/me/profiles")
    async def create_profile(
        payload: dict = Depends(get_current_user), body: dict = Body(...)
    ):
        return await site_backend.create_profile(
            payload.get("sub"), body.get("name"), body.get("model", "default")
        )

    @router.delete("/me/profiles/{pid}")
    async def delete_profile(pid: str, payload: dict = Depends(get_current_user)):
        await site_backend.delete_profile(payload.get("sub"), pid)
        return {"ok": True}

    @router.delete("/me/profiles/{pid}/skin")
    async def clear_profile_skin(pid: str, payload: dict = Depends(get_current_user)):
        await site_backend.clear_profile_texture(payload.get("sub"), pid, "skin")
        return {"ok": True}

    @router.delete("/me/profiles/{pid}/cape")
    async def clear_profile_cape(pid: str, payload: dict = Depends(get_current_user)):
        await site_backend.clear_profile_texture(payload.get("sub"), pid, "cape")
        return {"ok": True}

    @router.post("/me/textures")
    async def upload_texture_to_library(
        payload: dict = Depends(get_current_user),
        file: UploadFile = File(...),
        texture_type: str = Form(...),
        note: str = Form(""),
        is_public: str = Form("false"),
        model: str = Form("default"),
    ):
        user_id = payload.get("sub")
        content = await file.read()
        public_bool = is_public.lower() == "true"
        try:
            texture_hash, texture_type = await db.texture.upload(
                user_id, content, texture_type, note, is_public=public_bool, model=model
            )
            return {"hash": texture_hash, "type": texture_type, "note": note, "is_public": 1 if public_bool else 0, "model": model}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/me/textures")
    async def list_my_textures(payload: dict = Depends(get_current_user)):
        textures = await db.texture.get_for_user(payload.get("sub"))
        # 返回基础信息用于网格展示
        return [
            {"hash": r[0], "type": r[1], "note": r[2], "model": r[4]}
            for r in textures
        ]

    @router.get("/me/textures/{hash}/{texture_type}")
    async def get_my_texture_detail(
        hash: str,
        texture_type: str,
        payload: dict = Depends(get_current_user)
    ):
        user_id = payload.get("sub")
        info = await db.texture.get_texture_info(user_id, hash, texture_type)
        if not info:
            raise HTTPException(status_code=404, detail="Texture not found")
        return info

    @router.patch("/me/textures/{hash}/{texture_type}")
    async def update_my_texture(
        hash: str,
        texture_type: str,
        payload: dict = Depends(get_current_user),
        body: dict = Body(...),
    ):
        user_id = payload.get("sub")
        if "note" in body:
            await db.texture.update_note(user_id, hash, texture_type, body["note"])
        if "model" in body:
            await db.texture.update_model(user_id, hash, texture_type, body["model"])
        if "is_public" in body:
            await db.texture.update_is_public(user_id, hash, texture_type, body["is_public"])
        
        info = await db.texture.get_texture_info(user_id, hash, texture_type)
        return {"ok": True, **info}

    @router.delete("/me/textures/{hash}/{texture_type}")
    async def delete_my_texture(
        hash: str, texture_type: str, payload: dict = Depends(get_current_user)
    ):
        await db.texture.delete_from_library(payload.get("sub"), hash, texture_type)
        return {"ok": True}

    @router.post("/me/textures/{hash}/add")
    async def add_texture_to_wardrobe(
        hash: str, payload: dict = Depends(get_current_user)
    ):
        success = await db.texture.add_to_user_wardrobe(payload.get("sub"), hash)
        if not success:
            raise HTTPException(status_code=404, detail="Texture not found in library")
        return {"ok": True}

    @router.get("/public/skin-library")
    async def get_skin_library(
        page: int = 1,
        limit: int = 20,
        texture_type: Optional[str] = None
    ):
        enabled = await db.setting.get("enable_skin_library", "true")
        if enabled != "true":
            raise HTTPException(status_code=403, detail="Skin library is disabled by administrator")
        
        offset = (page - 1) * limit
        total = await db.texture.count_library(texture_type=texture_type)
        items = await db.texture.get_from_library(limit=limit, offset=offset, texture_type=texture_type)
        
        # 批量获取上传者名称
        uploader_ids = list(set(r[3] for r in items if r[3]))
        uploader_names = await db.user.get_display_names_by_ids(uploader_ids)
        
        return {
            "total": total,
            "items": [
                {
                    "hash": r[0],
                    "type": r[1],
                    "is_public": r[2],
                    "uploader": r[3],
                    "uploader_name": uploader_names.get(r[3], ""),
                    "created_at": r[4],
                    "model": r[5],
                    "name": r[6]
                }
                for r in items
            ]
        }

    @router.post("/me/textures/{hash}/apply")
    async def apply_texture_to_profile(
        hash: str, payload: dict = Depends(get_current_user), body: dict = Body(...)
    ):
        user_id = payload.get("sub")
        profile_id = body.get("profile_id")
        texture_type = body.get("texture_type")
        try:
            await site_backend.apply_texture_to_profile(
                user_id, profile_id, hash, texture_type
            )
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))

    @router.post("/textures/upload")
    async def textures_upload(
        payload: dict = Depends(get_current_user),  # Enforce JWT auth
        file: UploadFile = File(...),
        uuid: str = Form(...),
        texture_type: str = Form(...),
        model: str = Form(""),
        is_public: str = Form("false"),
    ):
        """
        前端直接上传材质接口.
        此接口现在是 Web API 的一部分，强制使用 JWT 进行身份验证。
        """
        content = await file.read()
        user_id = payload.get("sub")
        public_bool = is_public.lower() == "true"

        try:
            # 1. 上传材质到用户库 (或直接保存文件)
            texture_hash, _ = await db.texture.upload(
                user_id, content, texture_type, f"Direct upload to profile {uuid}", is_public=public_bool
            )

            # 2. 应用到角色
            await site_backend.apply_texture_to_profile(
                user_id, uuid, texture_hash, texture_type
            )

            # 3. 如果是皮肤，则更新模型
            if texture_type.lower() == "skin":
                m_val = "slim" if model == "slim" else "default"
                await db.user.update_profile_texture_model(uuid, m_val)

            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            print(f"Error during direct texture upload: {e}")
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during texture upload.",
            )

    @router.get("/public/settings")
    async def get_public_settings():
        settings = await db.setting.get_all()
        fallbacks = await site_backend.get_fallback_services()
        primary = fallbacks[0] if fallbacks else None
        site_name = settings.get("site_name", "皮肤站")
        raw_suffixes = settings.get("register_email_suffixes", "")
        if isinstance(raw_suffixes, list):
            suffix_list = [str(item).strip() for item in raw_suffixes if str(item).strip()]
        else:
            suffix_list = [
                item.strip()
                for item in str(raw_suffixes or "").replace("\n", ",").split(",")
                if item.strip()
            ]
        normalized_suffixes = []
        for item in suffix_list:
            token = str(item).strip().lower()
            token = token.lstrip("@")
            if token.startswith("."):
                token = token[1:]
            if token:
                normalized_suffixes.append(token)
        normalized_suffixes = list(dict.fromkeys(normalized_suffixes))

        return {
            "site_name": site_name,
            "site_title": settings.get("site_title", site_name),
            "site_logo": settings.get("site_logo", ""),
            "site_subtitle": settings.get("site_subtitle", "简洁、高效、现代的 Minecraft 皮肤管理站"),
            "allow_register": settings.get("allow_register", "true") == "true",
            "register_email_suffixes": normalized_suffixes,
            "enable_skin_library": settings.get("enable_skin_library", "true") == "true",
            "email_verify_enabled": settings.get("email_verify_enabled", "false") == "true",
            "footer_text": settings.get("footer_text", ""),
            "filing_icp": settings.get("filing_icp", ""),
            "filing_icp_link": settings.get("filing_icp_link", ""),
            "filing_mps": settings.get("filing_mps", ""),
            "filing_mps_link": settings.get("filing_mps_link", ""),
            "mojang_status_urls": {
                "session": (primary or {}).get(
                    "session_url", "https://sessionserver.mojang.com"
                ),
                "account": (primary or {}).get(
                    "account_url", "https://api.mojang.com"
                ),
                "services": (primary or {}).get(
                    "services_url", "https://api.minecraftservices.com"
                ),
            },
        }

    @router.get("/public/carousel")
    async def get_carousel():
        return await site_backend.list_carousel_images()

    @router.get("/public/default-avatar")
    async def get_default_avatar():
        png_data = default_steve_head_avatar(output_size=256)
        return Response(content=png_data, media_type="image/png")

    # ========== OAuth 2 ========== 

    @router.get("/oauth/authorize/check")
    async def oauth_authorize_check(
        client_id: int = Query(...),
        redirect_uri: str = Query(...),
        state: str = Query(default=""),
        scope: str = Query(default="userinfo"),
    ):
        return await oauth_backend.build_authorize_preview(client_id, redirect_uri, state, scope)

    @router.post("/oauth/authorize/decision")
    async def oauth_authorize_decision(
        payload: dict = Depends(get_current_user),
        body: dict = Body(...),
    ):
        client_id = body.get("client_id")
        redirect_uri = body.get("redirect_uri")
        state = body.get("state", "")
        approved = bool(body.get("approved", False))
        scope = body.get("scope", "basic")
        if client_id is None or not redirect_uri:
            raise HTTPException(status_code=400, detail="client_id and redirect_uri required")
        return await oauth_backend.authorize_decision(
            user_id=payload.get("sub"),
            client_id=int(client_id),
            redirect_uri=redirect_uri,
            state=state,
            approved=approved,
            scope=scope,
        )

    @router.get("/.well-known/openid-configuration")
    async def openid_configuration():
        return await oauth_backend.openid_configuration()

    @router.get("/oauth/jwks")
    async def oauth_jwks():
        return oauth_backend.jwks()

    @router.post("/oauth/device/code")
    async def oauth_device_code(
        client_id: int = Form(...),
        scope: str = Form(default="openid offline_access Yggdrasil.PlayerProfiles.Select Yggdrasil.Server.Join"),
    ):
        return await oauth_backend.create_device_authorization(client_id=client_id, scope=scope)

    @router.get("/oauth/device/authorize/check")
    async def oauth_device_authorize_check(user_code: str = Query(...)):
        return await oauth_backend.build_device_preview(user_code)

    @router.post("/oauth/device/authorize/decision")
    async def oauth_device_authorize_decision(
        payload: dict = Depends(get_current_user),
        body: dict = Body(...),
    ):
        user_code = body.get("user_code", "")
        approved = bool(body.get("approved", False))
        if not user_code:
            raise HTTPException(status_code=400, detail="user_code required")
        return await oauth_backend.decide_device_authorization(
            user_id=payload.get("sub"),
            user_code=user_code,
            approved=approved,
        )

    @router.post("/oauth/token")
    async def oauth_token(
        grant_type: str = Form(...),
        code: str | None = Form(default=None),
        client_id: int | None = Form(default=None),
        client_secret: str | None = Form(default=None),
        redirect_uri: str | None = Form(default=None),
        device_code: str | None = Form(default=None),
        refresh_token: str | None = Form(default=None),
    ):
        return await oauth_backend.token_endpoint(
            grant_type=grant_type,
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            device_code=device_code,
            refresh_token=refresh_token,
        )

    @router.get("/oauth/userinfo")
    async def oauth_userinfo(request: Request):
        access_token = get_oauth_bearer_token(request)
        return await oauth_backend.get_userinfo(access_token)

    @router.get("/oauth/profile")
    async def oauth_profile(request: Request):
        access_token = get_oauth_bearer_token(request)
        return await oauth_backend.get_profile_info(access_token)

    @router.get("/oauth/avatar")
    async def oauth_avatar(request: Request):
        access_token = get_oauth_bearer_token(request)
        return await oauth_backend.get_avatar_info(access_token)

    @router.get("/oauth/email")
    async def oauth_email(request: Request):
        access_token = get_oauth_bearer_token(request)
        return await oauth_backend.get_email_info(access_token)

    @router.get("/oauth/permissions")
    async def oauth_permissions(request: Request):
        access_token = get_oauth_bearer_token(request)
        return await oauth_backend.get_permissions_info(access_token)

    @router.get("/oauth/skin")
    async def oauth_skin(request: Request):
        access_token = get_oauth_bearer_token(request)
        skin_info = await oauth_backend.get_skin_info(access_token)
        return FileResponse(
            skin_info["path"],
            media_type="image/png",
            filename=f"{skin_info['profile_name']}.png",
            headers={
                "X-VSkin-Profile-Id": skin_info["profile_id"],
                "X-VSkin-Profile-Name": skin_info["profile_name"],
                "X-VSkin-Skin-Hash": skin_info["skin_hash"],
                "X-VSkin-Skin-Model": skin_info["model"],
                "Cache-Control": "private, max-age=300",
            },
        )

    # ========== Embedded Janus Compatibility ==========

    async def ensure_janus_enabled():
        if not await oauth_backend._janus_enabled():
            raise HTTPException(status_code=404, detail="janus is disabled")

    async def ensure_janus_prefix(janus_prefix: str):
        configured = await oauth_backend._janus_base_path()
        incoming = "/" + str(janus_prefix or "").strip("/")
        if len(incoming) > 1:
            incoming = incoming.rstrip("/")
        if incoming != configured:
            raise HTTPException(status_code=404, detail="janus endpoint not found")

    @router.get("/api/janus/.well-known/openid-configuration")
    @router.get("/{janus_prefix:path}/.well-known/openid-configuration")
    async def janus_openid_configuration(janus_prefix: str = "api/janus"):
        await ensure_janus_prefix(janus_prefix)
        return await oauth_backend.janus_openid_configuration()

    @router.get("/api/janus/oauth/jwks")
    @router.get("/{janus_prefix:path}/oauth/jwks")
    async def janus_oauth_jwks(janus_prefix: str = "api/janus"):
        await ensure_janus_enabled()
        await ensure_janus_prefix(janus_prefix)
        return oauth_backend.jwks()

    @router.post("/api/janus/oauth/device/code")
    @router.post("/{janus_prefix:path}/oauth/device/code")
    async def janus_oauth_device_code(
        client_id: int = Form(...),
        scope: str = Form(default="openid offline_access Yggdrasil.PlayerProfiles.Select Yggdrasil.Server.Join"),
        janus_prefix: str = "api/janus",
    ):
        await ensure_janus_enabled()
        await ensure_janus_prefix(janus_prefix)
        return await oauth_backend.create_device_authorization(client_id=client_id, scope=scope)

    @router.post("/api/janus/oauth/token")
    @router.post("/{janus_prefix:path}/oauth/token")
    async def janus_oauth_token(
        grant_type: str = Form(...),
        code: str | None = Form(default=None),
        client_id: int | None = Form(default=None),
        client_secret: str | None = Form(default=None),
        redirect_uri: str | None = Form(default=None),
        device_code: str | None = Form(default=None),
        refresh_token: str | None = Form(default=None),
        janus_prefix: str = "api/janus",
    ):
        await ensure_janus_enabled()
        await ensure_janus_prefix(janus_prefix)
        return await oauth_backend.token_endpoint(
            grant_type=grant_type,
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            device_code=device_code,
            refresh_token=refresh_token,
        )

    @router.get("/api/janus/oauth/userinfo")
    @router.get("/{janus_prefix:path}/oauth/userinfo")
    async def janus_oauth_userinfo(request: Request, janus_prefix: str = "api/janus"):
        await ensure_janus_enabled()
        await ensure_janus_prefix(janus_prefix)
        access_token = get_oauth_bearer_token(request)
        return await oauth_backend.get_userinfo(access_token)

    return router
