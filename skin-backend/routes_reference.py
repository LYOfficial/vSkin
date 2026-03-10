"""vSkin Backend - 主入口文件"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from config_loader import config
from database_module import Database
from backends.yggdrasil_backend import YggdrasilBackend, YggdrasilError
from backends.site_backend import SiteBackend
from backends.admin_backend import AdminBackend
from utils.crypto import CryptoUtils
from utils.rate_limiter import RateLimiter
from utils.cached_static import CachedStaticFiles
from routers import yggdrasil_routes, site_routes, microsoft_routes, admin_routes


def normalize_path_prefix(value: str) -> str:
    """标准化路由前缀，确保为空或以 / 开头且不以 / 结尾。"""
    if not value:
        return ""

    normalized = "/" + value.strip("/")
    return "" if normalized == "/" else normalized


def safe_join(base_dir: str, requested_path: str) -> str | None:
    """安全拼接静态文件路径，防止目录穿越。"""
    candidate = os.path.abspath(os.path.join(base_dir, requested_path))
    base_path = os.path.abspath(base_dir)

    if os.path.commonpath([base_path, candidate]) != base_path:
        return None
    return candidate

# ========== 初始化核心组件 ==========
db_path = config.get("database.path", "yggdrasil.db")
max_conns = config.get("database.max_connections", 10)
db = Database(db_path, max_connections=max_conns)
private_key_path = config.get("keys.private_key", "private.pem")
crypto = CryptoUtils(private_key_path)
rate_limiter = RateLimiter(db)  # New dependency-injected rate limiter
ygg_backend = YggdrasilBackend(db, crypto)
site_backend = SiteBackend(db, config)
admin_backend = AdminBackend(db, config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    await db.connect()
    await db.init()
    try:
        yield
    finally:
        await db.close()


# ========== 创建 FastAPI 应用 ==========
api_prefix = normalize_path_prefix(config.get("server.root_path", ""))

app = FastAPI(
    title="vSkin Backend",
    description="Yggdrasil 皮肤站后端服务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=f"{api_prefix}/docs" if api_prefix else "/docs",
    redoc_url=f"{api_prefix}/redoc" if api_prefix else "/redoc",
    openapi_url=f"{api_prefix}/openapi.json" if api_prefix else "/openapi.json",
)

# ========== 中间件配置 ==========

# CORS 跨域配置
cors_origins = config.get("cors.allow_origins", ["*"])
cors_credentials = config.get("cors.allow_credentials", True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# # 统一路径结尾斜杠中间件
# @app.middleware("http")
# async def append_slash_middleware(request: Request, call_next):    
#     # 为非根路径且不以斜杠结尾的路径添加斜杠
#     request.scope["path"] += "/"
#     # 去除重复斜杠
#     request.scope["path"] = request.scope["path"].replace("//", "/")
        
#     response = await call_next(request)
#     return response

# ========== 静态资源目录准备 ==========
# 单容器部署时由 FastAPI 直接提供静态资源和前端页面

textures_path = config.get("textures.directory", "textures")
os.makedirs(textures_path, exist_ok=True)

carousel_path = config.get("carousel.directory", "carousel")
os.makedirs(carousel_path, exist_ok=True)

app.mount(
    "/static/textures",
    CachedStaticFiles(directory=textures_path, cache_max_age=604800),
    name="textures",
)
app.mount(
    "/static/carousel",
    CachedStaticFiles(directory=carousel_path, cache_max_age=3600),
    name="carousel",
)

frontend_dist_path = os.path.join(os.path.dirname(__file__), "frontend-dist")
frontend_index_path = os.path.join(frontend_dist_path, "index.html")
frontend_enabled = bool(api_prefix) and os.path.isfile(frontend_index_path)


@app.exception_handler(YggdrasilError)
async def ygg_exception_handler(request: Request, exc: YggdrasilError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "errorMessage": exc.message},
    )


# ========== 注册路由模块 ==========

yggdrasil_router = yggdrasil_routes.setup_routes(ygg_backend, db, crypto, rate_limiter)
app.include_router(yggdrasil_router, prefix=api_prefix)

site_router = site_routes.setup_routes(db, site_backend, rate_limiter, config)
app.include_router(site_router, prefix=api_prefix)

admin_router = admin_routes.setup_routes(db, admin_backend, rate_limiter, config)
app.include_router(admin_router, prefix=api_prefix)

microsoft_router = microsoft_routes.setup_routes(db, config)
app.include_router(microsoft_router, prefix=api_prefix)


if frontend_enabled:

    @app.get("/", include_in_schema=False)
    async def serve_frontend_root():
        return FileResponse(frontend_index_path)


    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str, request: Request):
        prefix_path = api_prefix.lstrip("/")
        if prefix_path and (full_path == prefix_path or full_path.startswith(f"{prefix_path}/")):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = safe_join(frontend_dist_path, full_path)
        if candidate and os.path.isfile(candidate):
            return FileResponse(candidate)

        if "text/html" in request.headers.get("accept", "").lower():
            return FileResponse(frontend_index_path)

        raise HTTPException(status_code=404, detail="Not Found")

# ========== 应用启动 ==========

if __name__ == "__main__":
    import uvicorn

    host = config.get("server.host", "0.0.0.0")
    port = config.get("server.port", 8000)
    debug = config.get("server.debug", False)

    print(f"Starting vSkin Backend Server...")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Debug: {debug}")

    uvicorn.run(
        "routes_reference:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if debug else "warning",
    )
