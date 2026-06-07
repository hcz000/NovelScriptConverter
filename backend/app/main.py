"""FastAPI 应用入口：创建应用实例、配置中间件、注册路由和全局异常处理器。"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import create_router
from app.core.config import API_PREFIX, APP_TITLE, APP_VERSION, DATABASE_FILE, EXPORTS_DIR, LEGACY_STORE_FILE, UPLOADS_DIR
from app.core.store import DataStore

# 确保上传和导出目录存在
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# 初始化数据存储层（SQLite，支持从旧版 JSON 文件迁移）
store = DataStore(DATABASE_FILE, legacy_store_file=LEGACY_STORE_FILE)

# 创建 FastAPI 应用实例
app = FastAPI(title=APP_TITLE, version=APP_VERSION)

# 配置 CORS 中间件：允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由，统一添加 /api/v1 前缀
app.include_router(create_router(store), prefix=API_PREFIX)


# ---------- 全局异常处理 ----------

@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """HTTP 异常统一处理：将 detail 统一为结构化响应格式。"""
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "code": exc.status_code,
        "message": str(exc.detail),
        "request_id": "req_http_exception",
        "data": None,
    }
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """未捕获异常处理：特别处理 KeyError，其余异常继续抛出。"""
    if isinstance(exc, KeyError):
        return JSONResponse(
            status_code=500,
            content={
                "code": 50001,
                "message": f"missing key: {exc.args[0]}",
                "request_id": "req_unhandled",
                "data": None,
            },
        )
    raise exc
