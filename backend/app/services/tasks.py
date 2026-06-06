from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core import config
from app.core.store import DataStore
from app.services.common import (
    PROJECT_GENERATING,
    PROJECT_PARSING,
    PROJECT_READY,
    PROJECT_SCRIPT_READY,
    PROJECT_SOURCE_UPLOADED,
    TASK_FAILED,
    TASK_RUNNING,
    TASK_SUCCEEDED,
    date_str,
    ensure_current_script,
    ensure_project,
    make_error_response,
    make_id,
    now_iso,
    read_source_text,
    touch_project,
    update_task,
)
from app.services.scene_rewriter import apply_rewrite_instruction, llm_rewrite_scene
from app.services.script_builder import build_chapters, build_script, llm_generate_script
from app.services.quality_report import attach_quality_report
from app.services.script_ops import (
    clone_script,
    dump_script_content,
    find_scene,
    next_version_name,
    validate_script_or_raise,
)
from app.services.text_analysis import split_chapters


def parse_project_source(store: DataStore, project_id: str, task_id: str, min_chapter_count: int) -> None:
    update_task(store, task_id, status=TASK_RUNNING, progress=10)
    touch_project(store, project_id, status=PROJECT_PARSING)
    project = ensure_project(store, project_id)
    text = read_source_text(project)
    raw_chapters = split_chapters(text, min_chapter_count)
    if len(raw_chapters) < min_chapter_count:
        touch_project(store, project_id, status=PROJECT_SOURCE_UPLOADED)
        update_task(
            store,
            task_id,
            status=TASK_FAILED,
            progress=100,
            error_message="chapter count is less than required minimum",
        )
        return
    chapters = build_chapters(raw_chapters)

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        current["chapters"] = chapters
        current["source_chapter_count"] = len(chapters)
        current["status"] = PROJECT_READY
        current["updated_at"] = now_iso()
        return current

    store.mutate_project(project_id, updater)
    update_task(
        store,
        task_id,
        status=TASK_SUCCEEDED,
        progress=100,
        result={
            "project_id": project_id,
            "source_chapter_count": len(chapters),
        },
    )


def generate_project_script(
    store: DataStore,
    project_id: str,
    task_id: str,
    include_report: bool,
) -> None:
    update_task(store, task_id, status=TASK_RUNNING, progress=10)
    touch_project(store, project_id, status=PROJECT_GENERATING)
    project = ensure_project(store, project_id)
    chapters = project.get("chapters", [])
    if not chapters:
        touch_project(store, project_id, status=PROJECT_SOURCE_UPLOADED)
        update_task(
            store,
            task_id,
            status=TASK_FAILED,
            progress=100,
            error_message="chapters have not been parsed",
        )
        return

    rule_script = validate_script_or_raise(build_script(project, chapters))
    script = attach_quality_report(llm_generate_script(project, chapters, rule_script) or rule_script)
    version_id = make_id("ver")
    version_name = next_version_name(project.get("versions", []))
    version_record = {
        "version_id": version_id,
        "version_name": version_name,
        "description": "初稿版本",
        "source_version_id": None,
        "is_current": True,
        "created_at": now_iso(),
        "modified_scenes": [],
    }
    script["versions"] = [
        {
            "version": version_name,
            "created_at": date_str(),
            "description": "根据章节生成的初稿版本",
        }
    ]

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        for version in current["versions"]:
            version["is_current"] = False
        current["versions"].append(version_record)
        current["scripts"][version_id] = script
        current["current_version_id"] = version_id
        current["status"] = PROJECT_SCRIPT_READY
        current["updated_at"] = now_iso()
        return current

    store.mutate_project(project_id, updater)
    result = {
        "current_version_id": version_id,
        "total_scenes": len(script["scenes"]),
    }
    if include_report:
        result["report"] = {
            "structure_complete": True,
            "scene_count": len(script["scenes"]),
            "chapter_coverage": len(chapters),
        }
    update_task(store, task_id, status=TASK_SUCCEEDED, progress=100, result=result)


def patch_scene(
    store: DataStore,
    project_id: str,
    scene_id: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    project = ensure_project(store, project_id)
    version_id, _ = ensure_current_script(project)

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        script = current["scripts"][version_id]
        scene = find_scene(script, scene_id)
        if scene is None:
            raise ValueError("scene not found")
        for field in ("title", "slugline", "purpose", "beats", "adaptation_notes"):
            value = payload.get(field)
            if value is not None:
                scene[field] = value
        if script["versions"]:
            script["versions"].append(
                {
                    "version": current["versions"][-1]["version_name"],
                    "created_at": date_str(),
                    "description": payload.get("change_note") or f"手动编辑 {scene_id}",
                }
            )
        current_version = next(
            (version for version in current["versions"] if version["version_id"] == version_id),
            None,
        )
        if current_version is not None:
            modified_scenes = current_version.setdefault("modified_scenes", [])
            if scene_id not in modified_scenes:
                modified_scenes.append(scene_id)
            current_version["created_at"] = now_iso()
        attach_quality_report(script)
        script = validate_script_or_raise(script)
        current["scripts"][version_id] = script
        current["updated_at"] = now_iso()
        return current

    try:
        updated = store.mutate_project(project_id, updater)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=make_error_response(40402, str(error)),
        ) from error
    assert updated is not None
    script = updated["scripts"][version_id]
    scene = find_scene(script, scene_id)
    assert scene is not None
    return scene, version_id


def rewrite_scene_task(
    store: DataStore,
    project_id: str,
    scene_id: str,
    task_id: str,
    instruction: str,
    create_new_version: bool,
) -> None:
    update_task(store, task_id, status=TASK_RUNNING, progress=15)
    project = ensure_project(store, project_id)
    source_version_id, current_script = ensure_current_script(project)
    target_version_id = source_version_id
    working_script = current_script

    if create_new_version:
        working_script = clone_script(current_script)
        target_version_id = make_id("ver")

    scene = find_scene(working_script, scene_id)
    if scene is None:
        update_task(
            store,
            task_id,
            status=TASK_FAILED,
            progress=100,
            error_message="scene not found",
        )
        return

    llm_result = llm_rewrite_scene(scene, instruction)
    if llm_result:
        for field in ("purpose", "dramatic_structure", "beats", "adaptation_notes"):
            if field in llm_result and llm_result[field] is not None:
                scene[field] = llm_result[field]
        scene["adaptation_notes"] = {
            **scene.get("adaptation_notes", {}),
            "style": instruction,
        }
    else:
        apply_rewrite_instruction(scene, instruction)

    attach_quality_report(working_script)
    working_script = validate_script_or_raise(working_script)

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        if create_new_version:
            for version in current["versions"]:
                version["is_current"] = False
            version_record = {
                "version_id": target_version_id,
                "version_name": next_version_name(current["versions"]),
                "description": f"重写 {scene_id} 后生成的新版本",
                "source_version_id": source_version_id,
                "is_current": True,
                "created_at": now_iso(),
                "modified_scenes": [scene_id],
            }
            current["versions"].append(version_record)
            current["scripts"][target_version_id] = working_script
            current["current_version_id"] = target_version_id
        else:
            current["scripts"][target_version_id] = working_script
        current["updated_at"] = now_iso()
        return current

    store.mutate_project(project_id, updater)
    update_task(
        store,
        task_id,
        status=TASK_SUCCEEDED,
        progress=100,
        result={
            "current_version_id": target_version_id,
            "modified_scene_id": scene_id,
        },
    )


def export_script_task(
    store: DataStore,
    project_id: str,
    task_id: str,
    version_id: str | None,
    export_format: str,
    include_report: bool,
) -> None:
    update_task(store, task_id, status=TASK_RUNNING, progress=20)
    project = ensure_project(store, project_id)
    active_version_id = version_id or project.get("current_version_id")
    if not active_version_id or active_version_id not in project["scripts"]:
        update_task(
            store,
            task_id,
            status=TASK_FAILED,
            progress=100,
            error_message="version not found",
        )
        return
    script = validate_script_or_raise(attach_quality_report(project["scripts"][active_version_id]))
    content = dump_script_content(script, export_format)
    suffix = "json" if export_format.lower() == "json" else "yaml"
    file_name = f"{project_id}_{active_version_id}.{suffix}"
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    export_path = config.EXPORTS_DIR / file_name
    export_path.write_text(content, encoding="utf-8")

    result = {
        "download_url": f"{config.API_PREFIX}/downloads/{file_name}",
        "file_name": file_name,
    }
    if include_report:
        result["report"] = {
            "version_id": active_version_id,
            "total_scenes": len(script["scenes"]),
        }

    update_task(store, task_id, status=TASK_SUCCEEDED, progress=100, result=result)
