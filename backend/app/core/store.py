"""数据持久层：基于 SQLite 的线程安全数据存储类，支持从旧版 JSON 迁移。"""
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Callable


class DataStore:
    """线程安全的 SQLite 数据存储，负责项目（projects）和任务（tasks）的 CRUD 操作。"""

    def __init__(self, db_file: Path, legacy_store_file: Path | None = None) -> None:
        """初始化：创建数据库表、必要时从旧版 JSON 文件迁移数据。"""
        self.db_file = db_file
        self.legacy_store_file = legacy_store_file
        self._lock = Lock()  # 线程锁，保证并发安全
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._migrate_legacy_store()

    def _connect(self) -> sqlite3.Connection:
        """创建数据库连接，返回以 Row 对象形式访问结果。"""
        connection = sqlite3.connect(self.db_file)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        """初始化数据库表结构：projects 表与 tasks 表。"""
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")  # WAL 模式提高并发性能
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_project_id
                ON tasks(project_id)
                """
            )

    def _migrate_legacy_store(self) -> None:
        """如果当前数据库为空且有旧版 JSON 文件，则迁移数据。"""
        if self.legacy_store_file is None or not self.legacy_store_file.is_file():
            return

        with self._lock:
            with self._connect() as connection:
                project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                task_count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                if project_count or task_count:
                    return  # 已有数据，不重复迁移

                with self.legacy_store_file.open("r", encoding="utf-8") as file:
                    data = json.load(file)

                for project in data.get("projects", {}).values():
                    self._upsert_project_unlocked(connection, project)
                for task in data.get("tasks", {}).values():
                    self._upsert_task_unlocked(connection, task)

    # ---------- payload 编解码 ----------

    @staticmethod
    def _decode_payload(value: str | bytes) -> dict[str, Any]:
        """将数据库中的 JSON 字符串/字节解码为 dict。"""
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    @staticmethod
    def _encode_payload(value: dict[str, Any]) -> str:
        """将 dict 编码为紧凑的 JSON 字符串（保留中文）。"""
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    # ---------- 项目 CRUD ----------

    def _get_project_unlocked(self, connection: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
        """（无锁内部方法）根据 project_id 获取项目。"""
        row = connection.execute(
            "SELECT payload FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return self._decode_payload(row["payload"]) if row else None

    def _upsert_project_unlocked(self, connection: sqlite3.Connection, project: dict[str, Any]) -> None:
        """（无锁内部方法）插入或更新项目记录。"""
        connection.execute(
            """
            INSERT INTO projects(project_id, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                payload = excluded.payload,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                project["project_id"],
                self._encode_payload(project),
                project.get("created_at"),
                project.get("updated_at"),
            ),
        )

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """（线程安全）获取项目，返回深拷贝避免外部修改。"""
        with self._lock:
            with self._connect() as connection:
                project = self._get_project_unlocked(connection, project_id)
                return deepcopy(project) if project else None

    def list_projects(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """（线程安全）列出所有项目，默认不包含已归档项目。"""
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT payload FROM projects ORDER BY COALESCE(updated_at, created_at) DESC"
                ).fetchall()
                projects = [self._decode_payload(row["payload"]) for row in rows]
                if not include_archived:
                    projects = [project for project in projects if not project.get("archived")]
                return deepcopy(projects)

    def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        """（线程安全）插入或更新项目。"""
        with self._lock:
            with self._connect() as connection:
                self._upsert_project_unlocked(connection, deepcopy(project))
            return deepcopy(project)

    def mutate_project(
        self,
        project_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        """（线程安全）原子性地读取并修改项目，通过传入的 updater 函数实现。
        如果项目不存在返回 None，否则返回更新后的项目。
        """
        with self._lock:
            with self._connect() as connection:
                project = self._get_project_unlocked(connection, project_id)
                if project is None:
                    return None
                updated = updater(deepcopy(project))
                self._upsert_project_unlocked(connection, updated)
                return deepcopy(updated)

    def delete_project(self, project_id: str) -> bool:
        """（线程安全）删除项目及其关联的所有任务。返回是否成功删除。"""
        with self._lock:
            with self._connect() as connection:
                cursor = connection.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
                connection.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
                return cursor.rowcount > 0

    # ---------- 任务 CRUD ----------

    def _get_task_unlocked(self, connection: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
        """（无锁内部方法）根据 task_id 获取任务。"""
        row = connection.execute(
            "SELECT payload FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return self._decode_payload(row["payload"]) if row else None

    def _upsert_task_unlocked(self, connection: sqlite3.Connection, task: dict[str, Any]) -> None:
        """（无锁内部方法）插入或更新任务记录。"""
        connection.execute(
            """
            INSERT INTO tasks(task_id, project_id, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                project_id = excluded.project_id,
                payload = excluded.payload,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                task["task_id"],
                task["project_id"],
                self._encode_payload(task),
                task.get("created_at"),
                task.get("updated_at"),
            ),
        )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """（线程安全）获取任务，返回深拷贝避免外部修改。"""
        with self._lock:
            with self._connect() as connection:
                task = self._get_task_unlocked(connection, task_id)
                return deepcopy(task) if task else None

    def upsert_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """（线程安全）插入或更新任务。"""
        with self._lock:
            with self._connect() as connection:
                self._upsert_task_unlocked(connection, deepcopy(task))
            return deepcopy(task)

    def list_tasks(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """（线程安全）列出任务，可按项目过滤。"""
        with self._lock:
            with self._connect() as connection:
                if project_id:
                    rows = connection.execute(
                        "SELECT payload FROM tasks WHERE project_id = ? ORDER BY COALESCE(updated_at, created_at) DESC",
                        (project_id,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT payload FROM tasks ORDER BY COALESCE(updated_at, created_at) DESC"
                    ).fetchall()
                return deepcopy([self._decode_payload(row["payload"]) for row in rows])

    def mutate_task(
        self,
        task_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        """（线程安全）原子性地读取并修改任务，通过传入的 updater 函数实现。"""
        with self._lock:
            with self._connect() as connection:
                task = self._get_task_unlocked(connection, task_id)
                if task is None:
                    return None
                updated = updater(deepcopy(task))
                self._upsert_task_unlocked(connection, updated)
                return deepcopy(updated)
