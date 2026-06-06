import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.router import create_router
from app.core.store import DataStore


@pytest.fixture()
def temp_store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "store.json")


@pytest.fixture()
def app_client(temp_store: DataStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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

    with TestClient(app) as client:
        yield client
