import json
import math
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import EXPORTS_DIR, UPLOADS_DIR
from app.core.store import DataStore

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


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

STOP_WORDS = {
    "他们",
    "我们",
    "自己",
    "没有",
    "一个",
    "不是",
    "已经",
    "可以",
    "因为",
    "然后",
    "时候",
    "这里",
    "那里",
    "只是",
    "如果",
    "这个",
    "那个",
    "一种",
    "一种",
    "什么",
    "怎么",
    "事情",
    "目光",
    "声音",
    "身体",
    "心里",
    "周围",
    "测试",
    "场景",
    "章节",
}


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
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file_name)
    path = UPLOADS_DIR / f"{project_id}_{safe_name}"
    path.write_bytes(content)
    return path


def read_source_text(project: dict[str, Any]) -> str:
    path = project.get("source_file_path")
    if not path:
        raise ValueError("source file path is missing")
    return Path(path).read_text(encoding="utf-8")


def matches_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    patterns = (
        r"^第[0-9一二三四五六七八九十百千]+章.*$",
        r"^Chapter\s+\d+.*$",
        r"^#\s+.+$",
        r"^\d+[.、]\s*.+$",
    )
    return any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in patterns)


def split_chapters(text: str, min_chapter_count: int) -> list[dict[str, Any]]:
    normalized = text.replace("\r\n", "\n").strip()
    lines = normalized.split("\n")
    chapters: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        content = "\n".join(current_lines).strip()
        if not content:
            current_title = None
            current_lines = []
            return
        chapters.append(
            {
                "title": current_title or f"章节 {len(chapters) + 1}",
                "text": content,
            }
        )
        current_title = None
        current_lines = []

    for line in lines:
        if matches_heading(line):
            if current_lines:
                flush()
            current_title = line.strip().lstrip("#").strip()
            continue
        current_lines.append(line)

    if current_lines:
        flush()

    if len(chapters) >= min_chapter_count:
        return chapters

    paragraphs = [segment.strip() for segment in normalized.split("\n\n") if segment.strip()]
    if len(paragraphs) < min_chapter_count:
        return []

    chunk_count = min(max(min_chapter_count, 3), len(paragraphs))
    chunk_size = math.ceil(len(paragraphs) / chunk_count)
    fallback_chapters: list[dict[str, Any]] = []
    for index in range(chunk_count):
        start = index * chunk_size
        end = start + chunk_size
        chunk = paragraphs[start:end]
        if not chunk:
            continue
        fallback_chapters.append(
            {
                "title": f"章节 {index + 1}",
                "text": "\n\n".join(chunk),
            }
        )
    return fallback_chapters if len(fallback_chapters) >= min_chapter_count else []


def summarize_text(text: str, limit: int = 90) -> str:
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", text) if item.strip()]
    if sentences:
        summary = "".join(sentences[:2]).strip()
    else:
        summary = text.strip()
    return summary[:limit]


def extract_characters(text: str) -> list[str]:
    matches = re.findall(r"[\u4e00-\u9fff]{2,3}", text)
    counter = Counter()
    for match in matches:
        if match in STOP_WORDS:
            continue
        if any(char.isdigit() for char in match):
            continue
        counter[match] += 1
    names = [name for name, count in counter.most_common(5) if count >= 2]
    return names or ["主角"]


def build_chapters(raw_chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for index, chapter in enumerate(raw_chapters, start=1):
        chapter_text = chapter["text"].strip()
        summary = summarize_text(chapter_text)
        chapters.append(
            {
                "chapter_id": f"CH{index:03d}",
                "title": chapter["title"][:80],
                "word_count": len(chapter_text),
                "summary": summary,
                "characters": extract_characters(chapter_text),
                "scene_candidates": 1,
                "chapter_text": chapter_text,
            }
        )
    return chapters


def build_scene(chapter: dict[str, Any], index: int) -> dict[str, Any]:
    scene_title = chapter["title"][:60]
    summary = chapter["summary"]
    characters = chapter["characters"] or ["主角"]
    primary_character = characters[0]
    pacing = "快" if index % 2 == 0 else "中"
    style = "强调冲突推进" if index % 2 == 0 else "强调人物处境"
    time_of_day = "白天" if index % 2 == 1 else "夜晚"
    return {
        "scene_id": f"SC{index:03d}",
        "title": scene_title,
        "slugline": f"INT. 改编场景 {index} - {time_of_day}",
        "purpose": summary,
        "source_refs": [
            {
                "chapter_id": chapter["chapter_id"],
                "excerpt_summary": summary,
            }
        ],
        "characters": characters,
        "dramatic_structure": {
            "objective": f"{primary_character}试图推动当前剧情向前发展。",
            "obstacle": "外部压力与内部犹疑同时存在。",
            "stakes": "如果失败，后续局势会进一步失衡。",
            "turning_point": "场景末尾出现新的信息或态度转变。",
            "emotion_curve": ["铺垫", "紧张", "推进"],
        },
        "beats": [
            {
                "type": "action",
                "content": summary,
            },
            {
                "type": "dialogue",
                "character": primary_character,
                "content": "这一步，我必须继续往前走。",
            },
        ],
        "adaptation_notes": {
            "pacing": pacing,
            "style": style,
        },
    }


def build_script(project: dict[str, Any], chapters: list[dict[str, Any]]) -> dict[str, Any]:
    scenes = [build_scene(chapter, index) for index, chapter in enumerate(chapters, start=1)]
    main_characters = []
    for chapter in chapters:
        for character in chapter["characters"]:
            if character not in main_characters:
                main_characters.append(character)
    chapter_summaries = [
        {
            "chapter_id": chapter["chapter_id"],
            "title": chapter["title"],
            "summary": chapter["summary"],
        }
        for chapter in chapters
    ]
    return {
        "project": {
            "title": f"{project['title']} - 剧本初稿",
            "source_type": "novel",
            "source_chapter_count": len(chapters),
            "language": project["language"],
            "created_at": date_str(),
            "version": "1.0",
        },
        "source_summary": {
            "premise": chapter_summaries[0]["summary"] if chapter_summaries else "",
            "main_conflict": "角色需要在持续升级的冲突中完成目标。",
            "main_characters": [
                {
                    "name": character,
                    "role": "主要角色",
                    "traits": ["待补充"],
                }
                for character in main_characters[:5]
            ],
        },
        "chapters": chapter_summaries,
        "scenes": scenes,
        "metadata": {
            "total_scenes": len(scenes),
            "estimated_runtime_minutes": max(5, len(scenes) * 4),
            "editable": True,
        },
        "versions": [],
    }


def next_version_name(existing_versions: list[dict[str, Any]]) -> str:
    if not existing_versions:
        return "v1.0"
    return f"v1.{len(existing_versions)}"


def clone_script(script: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(script)


def dump_script_content(script: dict[str, Any], export_format: str) -> str:
    export_format = export_format.lower()
    if export_format == "json":
        return json.dumps(script, ensure_ascii=False, indent=2)
    if yaml is None:
        return json.dumps(script, ensure_ascii=False, indent=2)
    return yaml.safe_dump(script, allow_unicode=True, sort_keys=False)


def find_scene(script: dict[str, Any], scene_id: str) -> dict[str, Any] | None:
    return next((scene for scene in script["scenes"] if scene["scene_id"] == scene_id), None)


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

    script = build_script(project, chapters)
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

    scene["beats"].append(
        {
            "type": "action",
            "content": f"重写指令生效：{instruction}",
        }
    )
    scene["adaptation_notes"] = {
        **scene.get("adaptation_notes", {}),
        "style": instruction,
        "pacing": "快",
    }

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
    script = project["scripts"][active_version_id]
    content = dump_script_content(script, export_format)
    suffix = "json" if export_format.lower() == "json" else "yaml"
    file_name = f"{project_id}_{active_version_id}.{suffix}"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    export_path = EXPORTS_DIR / file_name
    export_path.write_text(content, encoding="utf-8")

    result = {
        "download_url": f"/downloads/{file_name}",
        "file_name": file_name,
    }
    if include_report:
        result["report"] = {
            "version_id": active_version_id,
            "total_scenes": len(script["scenes"]),
        }

    update_task(store, task_id, status=TASK_SUCCEEDED, progress=100, result=result)

