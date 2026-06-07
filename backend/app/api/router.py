"""API 路由定义：注册所有 RESTful 接口，使用 BackgroundTasks 执行异步任务。"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app.core import config
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
    PROJECT_ARCHIVED,
    PROJECT_GENERATING,
    PROJECT_READY,
    TASK_FAILED,
    TASK_RUNNING,
    compare_scripts,
    create_project_record,
    create_task_record,
    dump_script_content,
    ensure_current_script,
    ensure_project,
    ensure_task,
    export_script_task,
    generate_project_script,
    make_error_response,
    make_success_response,
    now_iso,
    parse_project_source,
    patch_scene,
    rewrite_scene_task,
    save_upload_file,
    summarize_project,
    touch_project,
    update_task,
)


def create_router(store: DataStore) -> APIRouter:
    """创建并返回已注册所有路由的 APIRouter 实例。"""
    router = APIRouter()
    stale_task_limits = {
        "GENERATE_SCRIPT": timedelta(minutes=45),
        "REWRITE_SCENE": timedelta(minutes=20),
        "EXPORT_FILE": timedelta(minutes=15),
        "PARSE_CHAPTERS": timedelta(minutes=10),
    }

    def reconcile_project_status(project: dict[str, Any]) -> dict[str, Any]:
        """修复被中断后台任务遗留的 GENERATING 状态。"""
        if project.get("status") != PROJECT_GENERATING:
            return project
        running_tasks = [
            task for task in store.list_tasks(project.get("project_id"))
            if task.get("status") == TASK_RUNNING
        ]
        if running_tasks:
            return project
        return touch_project(store, project["project_id"], status=PROJECT_READY) or project

    # ---------- 健康检查 ----------

    @router.get("/health")
    def health() -> dict[str, Any]:
        """健康检查接口"""
        return make_success_response({"status": "ok"})

    # ---------- 项目基本操作 ----------

    @router.post("/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: CreateProjectRequest) -> dict[str, Any]:
        """创建新项目"""
        project = create_project_record(payload.title, payload.language)
        store.upsert_project(project)
        return make_success_response(
            {
                "project_id": project["project_id"],
                "title": project["title"],
                "status": project["status"],
            }
        )

    @router.get("/projects")
    def list_projects(include_archived: bool = Query(default=False)) -> dict[str, Any]:
        """获取项目列表，默认不包含已归档项目"""
        projects = [
            summarize_project(reconcile_project_status(project))
            for project in store.list_projects(include_archived)
        ]
        return make_success_response({"total": len(projects), "items": projects})

    @router.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        """获取单个项目详情"""
        project = ensure_project(store, project_id)
        project = reconcile_project_status(project)
        return make_success_response(summarize_project(project))

    @router.post("/projects/{project_id}/archive")
    def archive_project(project_id: str) -> dict[str, Any]:
        """归档项目"""
        project = ensure_project(store, project_id)
        updated = touch_project(
            store,
            project["project_id"],
            status=PROJECT_ARCHIVED,
            archived=True,
            archived_at=project.get("archived_at") or now_iso(),
        )
        assert updated is not None
        return make_success_response(summarize_project(updated))

    @router.post("/projects/{project_id}/unarchive")
    def unarchive_project(project_id: str) -> dict[str, Any]:
        """取消归档，恢复为可用状态"""
        project = ensure_project(store, project_id)
        updated = touch_project(
            store,
            project["project_id"],
            archived=False,
            archived_at=None,
            status=project.get("status") if project.get("status") != PROJECT_ARCHIVED else "READY",
        )
        assert updated is not None
        return make_success_response(summarize_project(updated))

    @router.delete("/projects/{project_id}")
    def delete_project(project_id: str) -> dict[str, Any]:
        """删除项目及其关联任务，同时清理上传和导出的物理文件。"""
        # 先清理物理文件
        for directory in (config.UPLOADS_DIR, config.EXPORTS_DIR):
            for f in directory.iterdir():
                if f.name.startswith(project_id):
                    f.unlink(missing_ok=True)
        # 再删数据库
        deleted = store.delete_project(project_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40401, "project not found"),
            )
        return make_success_response({"project_id": project_id, "deleted": True})

    # ---------- 源文件上传与解析 ----------

    @router.post("/projects/{project_id}/source")
    async def upload_source(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        """上传小说源文件（支持 .txt 和 .md 格式）"""
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
        """启动后台任务：解析章节"""
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
        """获取项目已解析的章节列表"""
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

    # ---------- 剧本生成 ----------

    @router.post("/projects/{project_id}/generate", status_code=status.HTTP_202_ACCEPTED)
    def generate_script(
        project_id: str,
        payload: GenerateScriptRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        """启动后台任务：生成剧本"""
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
        """获取指定版本（或当前版本）的完整剧本"""
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

    # ---------- 场景操作 ----------

    @router.get("/projects/{project_id}/scenes")
    def get_scenes(project_id: str) -> dict[str, Any]:
        """获取当前版本的所有场景摘要列表"""
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
        """获取单个场景的完整详情"""
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
        """编辑场景内容（仅允许当前版本）"""
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
        """启动后台任务：AI 重写指定场景"""
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

    # ---------- 版本管理 ----------

    @router.get("/projects/{project_id}/versions")
    def get_versions(project_id: str) -> dict[str, Any]:
        """获取项目的所有版本记录"""
        project = ensure_project(store, project_id)
        return make_success_response(
            {
                "total": len(project["versions"]),
                "items": project["versions"],
            }
        )

    @router.get("/projects/{project_id}/versions/compare")
    def compare_versions(
        project_id: str,
        base_version_id: str = Query(...),
        target_version_id: str = Query(...),
    ) -> dict[str, Any]:
        """对比两个版本的差异"""
        project = ensure_project(store, project_id)
        base_script = project["scripts"].get(base_version_id)
        target_script = project["scripts"].get(target_version_id)
        if base_script is None or target_script is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40403, "version not found"),
            )
        comparison = compare_scripts(base_script, target_script)
        return make_success_response(
            {
                "base_version_id": base_version_id,
                "target_version_id": target_version_id,
                **comparison,
            }
        )

    @router.get("/projects/{project_id}/versions/{version_id}")
    def get_version(project_id: str, version_id: str) -> dict[str, Any]:
        """获取指定版本的详细信息"""
        project = ensure_project(store, project_id)
        version = next((item for item in project["versions"] if item["version_id"] == version_id), None)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40403, "version not found"),
            )
        return make_success_response(version)

    # ---------- 导出 ----------

    @router.post("/projects/{project_id}/export", status_code=status.HTTP_202_ACCEPTED)
    def export_script(
        project_id: str,
        payload: ExportScriptRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        """启动后台任务：导出剧本为 YAML/JSON 文件"""
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

    # ---------- 同步导出下载（直出文件，不写磁盘） ----------

    @router.get("/projects/{project_id}/export/download")
    def download_export(
        project_id: str,
        format: str = Query(default="yaml"),
        include_report: bool = Query(default=True),
    ) -> Response:
        """同步导出剧本，直接以文件下载形式返回，同时保存一份到 exports 目录。"""
        project = ensure_project(store, project_id)
        version_id = project.get("current_version_id")
        if not version_id or version_id not in project["scripts"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=make_error_response(40901, "script has not been generated"),
            )
        script = project["scripts"][version_id]
        if include_report:
            from app.services.quality_report import attach_quality_report
            script = attach_quality_report(script, use_llm=False)
        content = dump_script_content(script, format)
        suffix = "yaml" if format.lower() != "json" else "json"
        filename = f"{project.get('title', 'script')}.{suffix}"
        file_name = f"{project_id}_{version_id}.{suffix}"
        # 同步保存一份到 exports 目录
        config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        export_path = config.EXPORTS_DIR / file_name
        export_path.write_text(content, encoding="utf-8")
        # 返回直接下载响应
        media_type = "application/x-yaml" if suffix == "yaml" else "application/json"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    # ---------- 任务查询与文件下载 ----------

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        """查询异步任务的执行状态和结果"""
        task = ensure_task(store, task_id)
        if task.get("status") == TASK_RUNNING:
            try:
                updated_at = datetime.fromisoformat(task.get("updated_at", ""))
            except ValueError:
                updated_at = None
            stale_limit = stale_task_limits.get(task.get("task_type"), timedelta(minutes=10))
            if updated_at and datetime.now(updated_at.tzinfo) - updated_at > stale_limit:
                task = update_task(
                    store,
                    task_id,
                    status=TASK_FAILED,
                    progress=100,
                    error_message="task interrupted or timed out; please retry",
                ) or task
                project_id = task.get("project_id")
                if project_id:
                    project = store.get_project(project_id)
                    if project and project.get("status") == PROJECT_GENERATING:
                        touch_project(store, project_id, status=PROJECT_READY)
        return make_success_response(task)

    @router.get("/downloads/{file_name}")
    def download_file(file_name: str) -> FileResponse:
        """下载导出文件（仅允许 exports 目录内的文件）"""
        from app.core.config import EXPORTS_DIR

        exports_dir = EXPORTS_DIR.resolve()
        file_path = (exports_dir / file_name).resolve()

        # 安全检查：防止路径遍历攻击
        if exports_dir not in file_path.parents or not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error_response(40405, "file not found"),
            )
        return FileResponse(path=file_path, filename=file_name)

    return router
