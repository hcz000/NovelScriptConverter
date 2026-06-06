from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import create_router
from app.core.config import API_PREFIX, APP_TITLE, APP_VERSION, DATABASE_FILE, EXPORTS_DIR, LEGACY_STORE_FILE, UPLOADS_DIR
from app.core.store import DataStore


UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

store = DataStore(DATABASE_FILE, legacy_store_file=LEGACY_STORE_FILE)

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_router(store), prefix=API_PREFIX)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {
        "code": exc.status_code,
        "message": str(exc.detail),
        "request_id": "req_http_exception",
        "data": None,
    }
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
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
