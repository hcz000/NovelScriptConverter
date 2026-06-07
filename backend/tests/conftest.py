"""Pytest 共享夹具（fixtures）：提供临时 SQLite 存储和 API 测试客户端。"""
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 确保 backend 根目录在 sys.path 中
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.router import create_router
from app.core.store import DataStore
from app.main import http_exception_handler, unhandled_exception_handler


@pytest.fixture()
def temp_store(tmp_path: Path) -> DataStore:
    """创建临时 SQLite 数据库的 DataStore 实例。"""
    return DataStore(tmp_path / "studio.sqlite3")


@pytest.fixture()
def app_client(temp_store: DataStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """创建使用临时存储和临时目录的 FastAPI TestClient。
    通过 monkeypatch 替换配置中的路径和 store 引用，确保测试隔离。
    """
    from app import main as app_main
    from app import services

    uploads_dir = tmp_path / "uploads"
    exports_dir = tmp_path / "exports"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(app_main, "store", temp_store, raising=False)
    monkeypatch.setattr("app.core.config.UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr("app.core.config.EXPORTS_DIR", exports_dir)
    monkeypatch.setattr("app.services.pipeline.UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr("app.services.pipeline.EXPORTS_DIR", exports_dir)

    app = FastAPI()
    app.include_router(create_router(temp_store), prefix="/api/v1")
    from fastapi import HTTPException

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    with TestClient(app) as client:
        yield client
