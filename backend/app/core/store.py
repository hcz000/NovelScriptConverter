import json
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Callable


class DataStore:
    def __init__(self, store_file: Path) -> None:
        self.store_file = store_file
        self._lock = Lock()
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_file.exists():
            self._write_unlocked({"projects": {}, "tasks": {}})

    def _read_unlocked(self) -> dict[str, Any]:
        with self.store_file.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        with self.store_file.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read_unlocked()
            project = data["projects"].get(project_id)
            return deepcopy(project) if project else None

    def upsert_project(self, project: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            data["projects"][project["project_id"]] = deepcopy(project)
            self._write_unlocked(data)
            return deepcopy(project)

    def mutate_project(
        self,
        project_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        with self._lock:
            data = self._read_unlocked()
            project = data["projects"].get(project_id)
            if project is None:
                return None
            updated = updater(deepcopy(project))
            data["projects"][project_id] = updated
            self._write_unlocked(data)
            return deepcopy(updated)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read_unlocked()
            task = data["tasks"].get(task_id)
            return deepcopy(task) if task else None

    def upsert_task(self, task: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            data["tasks"][task["task_id"]] = deepcopy(task)
            self._write_unlocked(data)
            return deepcopy(task)

    def mutate_task(
        self,
        task_id: str,
        updater: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        with self._lock:
            data = self._read_unlocked()
            task = data["tasks"].get(task_id)
            if task is None:
                return None
            updated = updater(deepcopy(task))
            data["tasks"][task_id] = updated
            self._write_unlocked(data)
            return deepcopy(updated)

