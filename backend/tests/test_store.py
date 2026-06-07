"""数据存储层测试：测试 DataStore 的 CRUD 操作正确性，包括迁移、增删改查。"""
import json
from pathlib import Path

from app.core.store import DataStore


def make_project(project_id: str = "proj_test") -> dict:
    return {
        "project_id": project_id,
        "title": "测试项目",
        "source_type": "novel",
        "language": "zh-CN",
        "status": "INIT",
        "source_chapter_count": 0,
        "current_version_id": None,
        "created_at": "2026-06-06T00:00:00+08:00",
        "updated_at": "2026-06-06T00:00:00+08:00",
        "source_file_name": None,
        "source_file_path": None,
        "chapters": [],
        "versions": [],
        "scripts": {},
    }


def make_task(project_id: str = "proj_test", task_id: str = "task_test") -> dict:
    return {
        "task_id": task_id,
        "task_type": "PARSE_CHAPTERS",
        "status": "PENDING",
        "progress": 0,
        "project_id": project_id,
        "result": None,
        "error_message": None,
        "created_at": "2026-06-06T00:00:00+08:00",
        "updated_at": "2026-06-06T00:00:00+08:00",
    }


def test_sqlite_store_persists_projects_and_tasks(tmp_path: Path) -> None:
    db_file = tmp_path / "studio.sqlite3"
    store = DataStore(db_file)
    project = make_project()
    task = make_task()

    store.upsert_project(project)
    store.upsert_task(task)

    reopened = DataStore(db_file)
    assert reopened.get_project(project["project_id"])["title"] == "测试项目"
    assert reopened.get_task(task["task_id"])["status"] == "PENDING"


def test_sqlite_store_mutates_records(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "studio.sqlite3")
    project = make_project()
    task = make_task()
    store.upsert_project(project)
    store.upsert_task(task)

    store.mutate_project(project["project_id"], lambda current: {**current, "status": "READY"})
    store.mutate_task(task["task_id"], lambda current: {**current, "status": "SUCCEEDED", "progress": 100})

    assert store.get_project(project["project_id"])["status"] == "READY"
    assert store.get_task(task["task_id"])["progress"] == 100


def test_sqlite_store_lists_and_deletes_projects(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "studio.sqlite3")
    active_project = make_project("proj_active")
    archived_project = {**make_project("proj_archived"), "archived": True}
    task = make_task(active_project["project_id"], "task_active")

    store.upsert_project(active_project)
    store.upsert_project(archived_project)
    store.upsert_task(task)

    active_projects = store.list_projects()
    all_projects = store.list_projects(include_archived=True)
    assert [project["project_id"] for project in active_projects] == ["proj_active"]
    assert {project["project_id"] for project in all_projects} == {"proj_active", "proj_archived"}

    assert store.delete_project(active_project["project_id"]) is True
    assert store.get_project(active_project["project_id"]) is None
    assert store.get_task(task["task_id"]) is None
    assert store.delete_project("missing") is False


def test_sqlite_store_imports_legacy_json_once(tmp_path: Path) -> None:
    legacy_file = tmp_path / "store.json"
    project = make_project("proj_legacy")
    task = make_task(project["project_id"], "task_legacy")
    legacy_file.write_text(
        json.dumps(
            {
                "projects": {project["project_id"]: project},
                "tasks": {task["task_id"]: task},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = DataStore(tmp_path / "studio.sqlite3", legacy_store_file=legacy_file)
    assert store.get_project(project["project_id"])["title"] == "测试项目"
    assert store.get_task(task["task_id"])["project_id"] == project["project_id"]

    project["title"] = "不应重复导入"
    legacy_file.write_text(
        json.dumps({"projects": {project["project_id"]: project}, "tasks": {}}, ensure_ascii=False),
        encoding="utf-8",
    )

    reopened = DataStore(tmp_path / "studio.sqlite3", legacy_store_file=legacy_file)
    assert reopened.get_project(project["project_id"])["title"] == "测试项目"
