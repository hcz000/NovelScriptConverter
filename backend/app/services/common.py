"""通用工具与常量：定义状态常量、ID 生成、响应构造、项目/任务记录等基础操作。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.core import config
from app.core.store import DataStore

# ---------- 任务状态常量 ----------
TASK_PENDING = "PENDING"      # 任务等待执行
TASK_RUNNING = "RUNNING"      # 任务执行中
TASK_SUCCEEDED = "SUCCEEDED"  # 任务成功完成
TASK_FAILED = "FAILED"         # 任务执行失败

# ---------- 项目状态常量 ----------
PROJECT_INIT = "INIT"                      # 项目初始化
PROJECT_SOURCE_UPLOADED = "SOURCE_UPLOADED" # 源文件已上传
PROJECT_PARSING = "PARSING"                # 正在解析章节
PROJECT_READY = "READY"                     # 章节解析完成，等待生成剧本
PROJECT_GENERATING = "GENERATING"           # 正在生成剧本
PROJECT_SCRIPT_READY = "SCRIPT_READY"       # 剧本生成完毕，可编辑
PROJECT_ARCHIVED = "ARCHIVED"              # 项目已归档


def now_iso() -> str:
    """获取当前时间的 ISO 格式字符串（精确到秒）。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def date_str() -> str:
    """获取当前日期的 ISO 格式字符串。"""
    return datetime.now().astimezone().date().isoformat()


def make_id(prefix: str) -> str:
    """生成带前缀的唯一 ID，如 proj_<8位hex>。"""
    return f"{prefix}_{uuid4().hex[:8]}"


def build_request_id() -> str:
    """生成请求唯一标识符。"""
    return f"req_{uuid4().hex[:12]}"


def make_success_response(data: Any, message: str = "ok") -> dict[str, Any]:
    """构造统一的成功响应 dict。"""
    return {
        "code": 0,
        "message": message,
        "request_id": build_request_id(),
        "data": data,
    }


def make_error_response(code: int, message: str) -> dict[str, Any]:
    """构造统一的错误响应 dict。"""
    return {
        "code": code,
        "message": message,
        "request_id": build_request_id(),
        "data": None,
    }


def create_project_record(title: str, language: str) -> dict[str, Any]:
    """创建初始项目记录（状态为 INIT）。"""
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
        "archived": False,
        "archived_at": None,
    }


def summarize_project(project: dict[str, Any]) -> dict[str, Any]:
    """提取项目的摘要信息（用于列表展示）。"""
    return {
        "project_id": project["project_id"],
        "title": project["title"],
        "status": project["status"],
        "source_chapter_count": project["source_chapter_count"],
        "current_version_id": project["current_version_id"],
        "version_count": len(project.get("versions", [])),
        "created_at": project["created_at"],
        "updated_at": project["updated_at"],
        "archived": bool(project.get("archived")),
        "archived_at": project.get("archived_at"),
    }


def create_task_record(project_id: str, task_type: str) -> dict[str, Any]:
    """创建初始任务记录（状态为 PENDING）。"""
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
    """原子更新任务字段，自动刷新 updated_at 时间戳。"""
    def updater(task: dict[str, Any]) -> dict[str, Any]:
        task.update(fields)
        task["updated_at"] = now_iso()
        return task

    return store.mutate_task(task_id, updater)


def touch_project(store: DataStore, project_id: str, **fields: Any) -> dict[str, Any] | None:
    """原子更新项目字段，自动刷新 updated_at 时间戳。"""
    def updater(project: dict[str, Any]) -> dict[str, Any]:
        project.update(fields)
        project["updated_at"] = now_iso()
        return project

    return store.mutate_project(project_id, updater)


def ensure_project(store: DataStore, project_id: str) -> dict[str, Any]:
    """确保项目存在，否则抛出 404 HTTPException。"""
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=make_error_response(40401, "project not found"),
        )
    return project


def ensure_task(store: DataStore, task_id: str) -> dict[str, Any]:
    """确保任务存在，否则抛出 404 HTTPException。"""
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=make_error_response(40404, "task not found"),
        )
    return task


def ensure_current_script(project: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """确保项目有当前版本的剧本，返回 (version_id, script)。"""
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
    """保存上传文件到 uploads 目录，返回文件路径。"""
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_name)
    path = config.UPLOADS_DIR / f"{project_id}_{safe_name}"
    path.write_bytes(content)
    return path


def read_source_text(project: dict[str, Any]) -> str:
    """读取项目的源文件全文。
    自动检测文件编码：优先尝试 UTF-8，失败则尝试 GBK（Windows 中文默认编码）。
    """
    path = project.get("source_file_path")
    if not path:
        raise ValueError("source file path is missing")
    raw_bytes = Path(path).read_bytes()
    # UTF-8 BOM 优先
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 全部失败时用 UTF-8 + replace 兜底
    return raw_bytes.decode("utf-8", errors="replace")
