from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.core import config
from app.core.store import DataStore


TASK_PENDING = "PENDING"
TASK_RUNNING = "RUNNING"
TASK_SUCCEEDED = "SUCCEEDED"
TASK_FAILED = "FAILED"

PROJECT_INIT = "INIT"
PROJECT_SOURCE_UPLOADED = "SOURCE_UPLOADED"
PROJECT_PARSING = "PARSING"
PROJECT_READY = "READY"
PROJECT_GENERATING = "GENERATING"
PROJECT_SCRIPT_READY = "SCRIPT_READY"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def date_str() -> str:
    return datetime.now().astimezone().date().isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def build_request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def make_success_response(data: Any, message: str = "ok") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "request_id": build_request_id(),
        "data": data,
    }


def make_error_response(code: int, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "request_id": build_request_id(),
        "data": None,
    }


def create_project_record(title: str, language: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "project_id": make_id("proj"),
        "title": title,
        "source_type": "novel",
        "language": language,
        "status": PROJECT_INIT,
        "source_chapter_count": 0,
        "current_version_id": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source_file_name": None,
        "source_file_path": None,
        "chapters": [],
        "versions": [],
        "scripts": {},
    }


def create_task_record(project_id: str, task_type: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "task_id": make_id("task"),
        "task_type": task_type,
        "status": TASK_PENDING,
        "progress": 0,
        "project_id": project_id,
        "result": None,
        "error_message": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def update_task(store: DataStore, task_id: str, **fields: Any) -> dict[str, Any] | None:
    def updater(task: dict[str, Any]) -> dict[str, Any]:
        task.update(fields)
        task["updated_at"] = now_iso()
        return task

    return store.mutate_task(task_id, updater)


def touch_project(store: DataStore, project_id: str, **fields: Any) -> dict[str, Any] | None:
    def updater(project: dict[str, Any]) -> dict[str, Any]:
        project.update(fields)
        project["updated_at"] = now_iso()
        return project

    return store.mutate_project(project_id, updater)


def ensure_project(store: DataStore, project_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=make_error_response(40401, "project not found"),
        )
    return project


def ensure_task(store: DataStore, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=make_error_response(40404, "task not found"),
        )
    return task


def ensure_current_script(project: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    version_id = project.get("current_version_id")
    if not version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=make_error_response(40901, "script has not been generated"),
        )
    script = project["scripts"].get(version_id)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=make_error_response(40403, "version not found"),
        )
    return version_id, script


def save_upload_file(project_id: str, file_name: str, content: bytes) -> Path:
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_name)
    path = config.UPLOADS_DIR / f"{project_id}_{safe_name}"
    path.write_bytes(content)
    return path


def read_source_text(project: dict[str, Any]) -> str:
    path = project.get("source_file_path")
    if not path:
        raise ValueError("source file path is missing")
    return Path(path).read_text(encoding="utf-8")
