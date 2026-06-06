from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.store import DataStore
from app.schemas import (
    CreateProjectRequest,
    ExportScriptRequest,
    GenerateScriptRequest,
    ParseProjectRequest,
    RewriteSceneRequest,
    UpdateSceneRequest,
)
from app.services.pipeline import (
    create_project_record,
    create_task_record,
    ensure_current_script,
    ensure_project,
    ensure_task,
    export_script_task,
    generate_project_script,
    make_error_response,
    make_success_response,
    parse_project_source,
    patch_scene,
    rewrite_scene_task,
    save_upload_file,
    touch_project,
)


def create_router(store: DataStore) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, Any]:
        return make_success_response({"status": "ok"})

    @router.post("/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: CreateProjectRequest) -> dict[str, Any]:
        project = create_project_record(payload.title, payload.language)
        store.upsert_project(project)
        return make_success_response(
            {
                "project_id": project["project_id"],
                "title": project["title"],
                "status": project["status"],
            }
        )

    @router.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        payload = {
            "project_id": project["project_id"],
            "title": project["title"],
            "status": project["status"],
            "source_chapter_count": project["source_chapter_count"],
            "current_version_id": project["current_version_id"],
            "created_at": project["created_at"],
            "updated_at": project["updated_at"],
        }
        return make_success_response(payload)

    @router.post("/projects/{project_id}/source")
    async def upload_source(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".txt", ".md"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=make_error_response(40002, "unsupported file type"),
            )
        content = await file.read()
        path = save_upload_file(project_id, file.filename or "source.txt", content)
        updated = touch_project(
            store,
            project["project_id"],
            source_file_name=file.filename,
            source_file_path=str(path),
            status="SOURCE_UPLOADED",
        )
        assert updated is not None
        return make_success_response(
            {
                "project_id": project["project_id"],
                "file_name": file.filename,
                "source_type": suffix.lstrip("."),
                "status": updated["status"],
            }
        )

    @router.post("/projects/{project_id}/parse", status_code=status.HTTP_202_ACCEPTED)
    def parse_project(
        project_id: str,
        payload: ParseProjectRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        ensure_project(store, project_id)
        task = create_task_record(project_id, "PARSE_CHAPTERS")
        store.upsert_task(task)
        background_tasks.add_task(
            parse_project_source,
            store,
            project_id,
            task["task_id"],
            payload.min_chapter_count,
        )
        return make_success_response(
            {
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "status": task["status"],
            },
            message="accepted",
        )

    @router.get("/projects/{project_id}/chapters")
    def get_chapters(project_id: str) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        items = [
            {
                "chapter_id": chapter["chapter_id"],
                "title": chapter["title"],
                "word_count": chapter["word_count"],
                "summary": chapter["summary"],
                "characters": chapter["characters"],
                "scene_candidates": chapter["scene_candidates"],
            }
            for chapter in project.get("chapters", [])
        ]
        return make_success_response({"total": len(items), "items": items})

    @router.post("/projects/{project_id}/generate", status_code=status.HTTP_202_ACCEPTED)
    def generate_script(
        project_id: str,
        payload: GenerateScriptRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        ensure_project(store, project_id)
        task = create_task_record(project_id, "GENERATE_SCRIPT")
        store.upsert_task(task)
        background_tasks.add_task(
            generate_project_script,
            store,
            project_id,
            task["task_id"],
            payload.include_report,
        )
        return make_success_response(
            {
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "status": task["status"],
            },
            message="accepted",
        )

    @router.get("/projects/{project_id}/script")
    def get_script(
        project_id: str,
        version_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        current_version_id = version_id or project.get("current_version_id")
        if not current_version_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=make_error_response(40901, "script has not been generated"),
            )
        script = project["scripts"].get(current_version_id)
        if script is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40403, "version not found"),
            )
        return make_success_response(script)

    @router.get("/projects/{project_id}/scenes")
    def get_scenes(project_id: str) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        _, script = ensure_current_script(project)
        items = [
            {
                "scene_id": scene["scene_id"],
                "title": scene["title"],
                "purpose": scene["purpose"],
                "characters": scene["characters"],
            }
            for scene in script["scenes"]
        ]
        return make_success_response({"total": len(items), "items": items})

    @router.get("/projects/{project_id}/scenes/{scene_id}")
    def get_scene(project_id: str, scene_id: str) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        _, script = ensure_current_script(project)
        scene = next((item for item in script["scenes"] if item["scene_id"] == scene_id), None)
        if scene is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40402, "scene not found"),
            )
        return make_success_response(scene)

    @router.patch("/projects/{project_id}/scenes/{scene_id}")
    def update_scene(
        project_id: str,
        scene_id: str,
        payload: UpdateSceneRequest,
    ) -> dict[str, Any]:
        scene, version_id = patch_scene(store, project_id, scene_id, payload.model_dump(exclude_none=True))
        return make_success_response(
            {
                "scene_id": scene["scene_id"],
                "saved": True,
                "current_version_id": version_id,
            }
        )

    @router.post(
        "/projects/{project_id}/scenes/{scene_id}/rewrite",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def rewrite_scene(
        project_id: str,
        scene_id: str,
        payload: RewriteSceneRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        ensure_project(store, project_id)
        task = create_task_record(project_id, "REWRITE_SCENE")
        store.upsert_task(task)
        background_tasks.add_task(
            rewrite_scene_task,
            store,
            project_id,
            scene_id,
            task["task_id"],
            payload.instruction,
            payload.create_new_version,
        )
        return make_success_response(
            {
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "status": task["status"],
            },
            message="accepted",
        )

    @router.get("/projects/{project_id}/versions")
    def get_versions(project_id: str) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        return make_success_response(
            {
                "total": len(project["versions"]),
                "items": project["versions"],
            }
        )

    @router.get("/projects/{project_id}/versions/{version_id}")
    def get_version(project_id: str, version_id: str) -> dict[str, Any]:
        project = ensure_project(store, project_id)
        version = next((item for item in project["versions"] if item["version_id"] == version_id), None)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40403, "version not found"),
            )
        return make_success_response(version)

    @router.post("/projects/{project_id}/export", status_code=status.HTTP_202_ACCEPTED)
    def export_script(
        project_id: str,
        payload: ExportScriptRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        ensure_project(store, project_id)
        task = create_task_record(project_id, "EXPORT_FILE")
        store.upsert_task(task)
        background_tasks.add_task(
            export_script_task,
            store,
            project_id,
            task["task_id"],
            payload.version_id,
            payload.format,
            payload.include_report,
        )
        return make_success_response(
            {
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "status": task["status"],
            },
            message="accepted",
        )

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        task = ensure_task(store, task_id)
        return make_success_response(task)

    @router.get("/downloads/{file_name}")
    def download_file(file_name: str) -> FileResponse:
        from app.core.config import EXPORTS_DIR

        exports_dir = EXPORTS_DIR.resolve()
        file_path = (exports_dir / file_name).resolve()

        if exports_dir not in file_path.parents or not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40405, "file not found"),
            )
        return FileResponse(path=file_path, filename=file_name)

    return router
