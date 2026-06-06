import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Callable


class DataStore:
    def __init__(self, db_file: Path, legacy_store_file: Path | None = None) -> None:
        self.db_file = db_file
        self.legacy_store_file = legacy_store_file
        self._lock = Lock()
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._migrate_legacy_store()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_file)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
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
        if self.legacy_store_file is None or not self.legacy_store_file.is_file():
            return

        with self._lock:
            with self._connect() as connection:
                project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                task_count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                if project_count or task_count:
                    return

                with self.legacy_store_file.open("r", encoding="utf-8") as file:
                    data = json.load(file)

                for project in data.get("projects", {}).values():
                    self._upsert_project_unlocked(connection, project)
                for task in data.get("tasks", {}).values():
                    self._upsert_task_unlocked(connection, task)

    @staticmethod
    def _decode_payload(value: str | bytes) -> dict[str, Any]:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    @staticmethod
    def _encode_payload(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _get_project_unlocked(self, connection: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT payload FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return self._decode_payload(row["payload"]) if row else None

    def _upsert_project_unlocked(self, connection: sqlite3.Connection, project: dict[str, Any]) -> None:
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
        with self._lock:
            with self._connect() as connection:
                project = self._get_project_unlocked(connection, project_id)
                return deepcopy(project) if project else None

    def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                self._upsert_project_unlocked(connection, deepcopy(project))
            return deepcopy(project)

    def mutate_project(
        self,
        project_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as connection:
                project = self._get_project_unlocked(connection, project_id)
                if project is None:
                    return None
                updated = updater(deepcopy(project))
                self._upsert_project_unlocked(connection, updated)
                return deepcopy(updated)

    def _get_task_unlocked(self, connection: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT payload FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return self._decode_payload(row["payload"]) if row else None

    def _upsert_task_unlocked(self, connection: sqlite3.Connection, task: dict[str, Any]) -> None:
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
        with self._lock:
            with self._connect() as connection:
                task = self._get_task_unlocked(connection, task_id)
                return deepcopy(task) if task else None

    def upsert_task(self, task: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                self._upsert_task_unlocked(connection, deepcopy(task))
            return deepcopy(task)

    def mutate_task(
        self,
        task_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as connection:
                task = self._get_task_unlocked(connection, task_id)
                if task is None:
                    return None
                updated = updater(deepcopy(task))
                self._upsert_task_unlocked(connection, updated)
                return deepcopy(updated)
