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

from app.core.config import API_PREFIX, EXPORTS_DIR, UPLOADS_DIR
from app.core.store import DataStore
from app.schemas import validate_script_payload

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

CHARACTER_HINT_WORDS = (
    "说",
    "问",
    "答",
    "喊",
    "叫",
    "看着",
    "看向",
    "盯着",
    "望着",
    "对",
    "朝",
    "跟",
)


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


def normalize_text(text: str) -> str:
    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def clean_character_candidate(value: str) -> str:
    candidate = value.strip()
    candidate = re.sub(r"(又|也|都|仍|还|正|却)$", "", candidate)
    return candidate


def matches_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    patterns = (
        r"^第[0-9一二三四五六七八九十百千]+章.*$",
        r"^第[0-9一二三四五六七八九十百千]+节.*$",
        r"^第[0-9一二三四五六七八九十百千]+回.*$",
        r"^序章.*$",
        r"^楔子.*$",
        r"^Chapter\s+\d+.*$",
        r"^#\s+.+$",
        r"^##\s+.+$",
        r"^\d+[.、]\s*.+$",
        r"^[（(]?[0-9一二三四五六七八九十]+[）)]\s*.+$",
    )
    return any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in patterns)


def split_chapters(text: str, min_chapter_count: int) -> list[dict[str, Any]]:
    normalized = normalize_text(text)
    lines = normalized.split("\n")
    chapters: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        content = "\n".join(line for line in current_lines if line.strip()).strip()
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

    paragraphs = [segment.strip() for segment in re.split(r"\n{2,}", normalized) if segment.strip()]
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
    cleaned = normalize_text(text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", cleaned) if item.strip()]
    if sentences:
        summary = "".join(sentences[:2]).strip()
    else:
        summary = cleaned.strip()
    return summary[:limit]


def extract_characters(text: str) -> list[str]:
    normalized = normalize_text(text)
    counter = Counter()
    patterns = [
        re.compile(rf"([\u4e00-\u9fff]{{2,4}})(?={'|'.join(CHARACTER_HINT_WORDS)})"),
        re.compile(rf"(?:对|朝|看向|望向)([\u4e00-\u9fff]{{2,4}})"),
    ]

    for pattern in patterns:
        for match in pattern.findall(normalized):
            match = clean_character_candidate(match)
            if match in STOP_WORDS or any(char.isdigit() for char in match):
                continue
            if len(match) < 2:
                continue
            counter[match] += 2

    for match in re.findall(r"[\u4e00-\u9fff]{2,4}", normalized):
        match = clean_character_candidate(match)
        if match in STOP_WORDS:
            continue
        if any(char.isdigit() for char in match):
            continue
        if len(match) < 2:
            continue
        if match.endswith(("起来", "下去", "出来", "进去", "不是", "可以")):
            continue
        counter[match] += 1

    names = [name for name, count in counter.most_common(6) if count >= 2]
    return names or ["主角"]


def build_chapters(raw_chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for index, chapter in enumerate(raw_chapters, start=1):
        chapter_text = chapter["text"].strip()
        summary = summarize_text(chapter_text)
        chapter_record = {
            "chapter_id": f"CH{index:03d}",
            "title": chapter["title"][:80],
            "word_count": len(chapter_text),
            "summary": summary,
            "characters": extract_characters(chapter_text),
            "scene_candidates": 1,
            "chapter_text": chapter_text,
        }
        chapter_record["scene_candidates"] = max(1, len(derive_scene_groups(chapter_record)))
        chapters.append(chapter_record)
    return chapters


def split_paragraphs(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    paragraphs = [segment.strip() for segment in re.split(r"\n{2,}", normalized) if segment.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]
    return paragraphs or [normalized]


def extract_keywords(text: str, limit: int = 5) -> list[str]:
    counter = Counter()
    for token in re.findall(r"[\u4e00-\u9fff]{2,4}", text):
        if token in STOP_WORDS:
            continue
        counter[token] += 1
    return [token for token, _ in counter.most_common(limit)]


def derive_scene_groups(chapter: dict[str, Any]) -> list[list[str]]:
    paragraphs = split_paragraphs(chapter["chapter_text"])
    if len(paragraphs) <= 2:
        return [paragraphs]

    max_group_size = 3 if len(paragraphs) <= 6 else 4
    transition_markers = (
        "与此同时",
        "另一边",
        "次日",
        "第二天",
        "当天夜里",
        "夜里",
        "片刻后",
        "不久",
        "随后",
        "忽然",
        "突然",
        "回到",
    )

    groups: list[list[str]] = []
    current_group: list[str] = []
    for paragraph in paragraphs:
        should_split = bool(
            current_group
            and (
                len(current_group) >= max_group_size
                or (len(current_group) >= 2 and paragraph.startswith(transition_markers))
            )
        )
        if should_split:
            groups.append(current_group)
            current_group = []
        current_group.append(paragraph)

    if current_group:
        groups.append(current_group)

    if len(groups) == 1 and len(paragraphs) >= 5:
        midpoint = math.ceil(len(paragraphs) / 2)
        return [paragraphs[:midpoint], paragraphs[midpoint:]]
    return groups


def extract_dialogue_fragments(paragraph: str) -> list[dict[str, str]]:
    fragments: list[dict[str, str]] = []
    quote_matches = re.findall(r"[“\"]([^”\"]{2,40})[”\"]", paragraph)
    if quote_matches:
        speaker_match = re.search(r"([\u4e00-\u9fff]{2,4})[说道问喊答叫]", paragraph)
        speaker = speaker_match.group(1) if speaker_match else ""
        for content in quote_matches:
            fragments.append({"character": speaker, "content": content.strip()})
        return fragments

    colon_match = re.match(r"^\s*([\u4e00-\u9fff]{2,4})[：:]\s*(.+)$", paragraph)
    if colon_match:
        fragments.append(
            {
                "character": colon_match.group(1).strip(),
                "content": colon_match.group(2).strip(),
            }
        )
    return fragments


def infer_time_of_day(text: str) -> str:
    if re.search(r"夜|晚|月|深夜|凌晨", text):
        return "夜晚"
    if re.search(r"晨|清晨|早上|黎明", text):
        return "清晨"
    if re.search(r"黄昏|傍晚|日落", text):
        return "傍晚"
    return "白天"


def infer_scene_pacing(paragraphs: list[str]) -> str:
    joined = "".join(paragraphs)
    action_hits = len(re.findall(r"冲|追|逃|打|杀|撞|喊|奔|闯|爆|推|拦|逼", joined))
    if action_hits >= 4 or len(paragraphs) <= 2:
        return "快"
    if action_hits >= 2:
        return "中"
    return "慢"


def infer_scene_style(paragraphs: list[str]) -> str:
    joined = "".join(paragraphs)
    if re.search(r"争|怒|逼|威胁|质问|反击", joined):
        return "冲突推进"
    if re.search(r"想|心|沉默|回忆|犹豫|目光", joined):
        return "情绪沉浸"
    return "叙事铺垫"


def summarize_paragraph_group(paragraphs: list[str], fallback: str) -> str:
    summary_source = " ".join(paragraphs[:2]) if paragraphs else fallback
    return summarize_text(summary_source or fallback, limit=120)


def find_scene_characters(paragraphs: list[str], chapter_characters: list[str]) -> list[str]:
    group_text = "".join(paragraphs)
    matched = [character for character in chapter_characters if character in group_text]
    if matched:
        return matched[:4]
    extracted = extract_characters(group_text)
    return extracted[:4] if extracted else (chapter_characters[:4] or ["主角"])


def build_beats_from_paragraphs(paragraphs: list[str], characters: list[str]) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []
    fallback_character = characters[0] if characters else "主角"

    for paragraph in paragraphs:
        dialogues = extract_dialogue_fragments(paragraph)
        narration = re.sub(r"[“\"][^”\"]{2,40}[”\"]", "", paragraph).strip()
        if narration:
            beats.append(
                {
                    "type": "action",
                    "content": summarize_text(narration, limit=80),
                }
            )
        for dialogue in dialogues:
            beats.append(
                {
                    "type": "dialogue",
                    "character": dialogue["character"] or fallback_character,
                    "content": dialogue["content"],
                }
            )

    if not beats:
        beats.append(
            {
                "type": "action",
                "content": summarize_text(" ".join(paragraphs), limit=90),
            }
        )
    return beats


def build_scene_dramatic_structure(
    chapter: dict[str, Any],
    paragraphs: list[str],
    scene_summary: str,
    characters: list[str],
) -> dict[str, Any]:
    primary_character = characters[0] if characters else "主角"
    conflict_keywords = extract_keywords("".join(paragraphs), limit=3)
    conflict_label = "、".join(conflict_keywords[:2]) if conflict_keywords else "外部压力"
    return {
        "objective": f"{primary_character}希望推进当前局势，确保“{scene_summary[:18] or chapter['title']}”落地。",
        "obstacle": f"场景中持续存在{conflict_label}带来的阻碍与误判。",
        "stakes": f"如果这一场失败，{primary_character}后续将失去主动权。",
        "turning_point": f"场景后段围绕“{scene_summary[:18] or chapter['title']}”出现新的信息或态度反转。",
        "emotion_curve": ["铺垫", "拉紧", "转折", "推进"],
    }


def build_character_profiles(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    appearances = Counter()
    for chapter in chapters:
        for character in chapter["characters"]:
            appearances[character] += 1

    roles = ["主角", "关键配角", "关键配角", "支撑角色", "支撑角色"]
    default_traits = [
        ["目标明确", "承压前进", "推动剧情"],
        ["立场鲜明", "影响决策"],
        ["制造变量", "推动冲突"],
        ["补充信息", "强化氛围"],
        ["辅助推进", "承担功能位"],
    ]

    profiles: list[dict[str, Any]] = []
    for index, (name, _) in enumerate(appearances.most_common(5)):
        profiles.append(
            {
                "name": name,
                "role": roles[index] if index < len(roles) else "支撑角色",
                "traits": default_traits[index] if index < len(default_traits) else ["待补充"],
            }
        )
    return profiles


def build_scene_from_group(
    chapter: dict[str, Any],
    scene_index: int,
    group_index: int,
    paragraphs: list[str],
    total_groups: int,
) -> dict[str, Any]:
    scene_summary = summarize_paragraph_group(paragraphs, chapter["summary"])
    characters = find_scene_characters(paragraphs, chapter["characters"])
    scene_text = "".join(paragraphs)
    scene_title = chapter["title"][:48]
    if total_groups > 1:
        scene_title = f"{scene_title} - 场景{group_index}"

    return {
        "scene_id": f"SC{scene_index:03d}",
        "title": scene_title,
        "slugline": f"INT. 改编场景 {scene_index} - {infer_time_of_day(scene_text)}",
        "purpose": scene_summary,
        "source_refs": [
            {
                "chapter_id": chapter["chapter_id"],
                "excerpt_summary": scene_summary,
            }
        ],
        "characters": characters,
        "dramatic_structure": build_scene_dramatic_structure(chapter, paragraphs, scene_summary, characters),
        "beats": build_beats_from_paragraphs(paragraphs, characters),
        "adaptation_notes": {
            "pacing": infer_scene_pacing(paragraphs),
            "style": infer_scene_style(paragraphs),
            "coverage": f"{chapter['chapter_id']} 第 {group_index}/{total_groups} 段场景",
        },
    }


def build_script(project: dict[str, Any], chapters: list[dict[str, Any]]) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    chapter_summaries = [
        {
            "chapter_id": chapter["chapter_id"],
            "title": chapter["title"],
            "summary": chapter["summary"],
        }
        for chapter in chapters
    ]

    scene_index = 1
    for chapter in chapters:
        groups = derive_scene_groups(chapter)
        for group_index, paragraphs in enumerate(groups, start=1):
            scenes.append(build_scene_from_group(chapter, scene_index, group_index, paragraphs, len(groups)))
            scene_index += 1

    premise = summarize_text(" ".join(chapter["summary"] for chapter in chapters[:3]), limit=140)
    conflict_seed = extract_keywords(" ".join(chapter["summary"] for chapter in chapters), limit=4)
    main_conflict = (
        f"故事围绕{'、'.join(conflict_seed[:2])}展开，角色必须在连续冲突中争取主动。"
        if conflict_seed
        else "故事围绕角色目标与外部阻力之间的持续冲突展开。"
    )

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
            "premise": premise,
            "main_conflict": main_conflict,
            "main_characters": build_character_profiles(chapters),
        },
        "chapters": chapter_summaries,
        "scenes": scenes,
        "metadata": {
            "total_scenes": len(scenes),
            "estimated_runtime_minutes": max(5, len(scenes) * 4),
            "editable": True,
            "scene_density": round(len(scenes) / max(1, len(chapters)), 2),
        },
        "versions": [],
    }


def build_rewrite_profile(instruction: str) -> dict[str, bool]:
    normalized = instruction.strip()
    return {
        "compress_pacing": any(keyword in normalized for keyword in ("压缩", "更快", "短剧", "节奏")),
        "enhance_conflict": any(keyword in normalized for keyword in ("冲突", "对抗", "张力", "矛盾", "逼迫")),
        "expand_emotion": any(keyword in normalized for keyword in ("情绪", "心理", "共鸣", "感染", "情感")),
        "highlight_turning_point": any(keyword in normalized for keyword in ("反转", "爆点", "爽点", "钩子")),
    }


def rewrite_action_content(content: str, profile: dict[str, bool]) -> str:
    rewritten = content.strip()
    if profile["compress_pacing"] and len(rewritten) > 28:
        rewritten = summarize_text(rewritten, limit=28)
    if profile["enhance_conflict"] and "对抗" not in rewritten and "冲突" not in rewritten:
        rewritten = f"{rewritten}，现场的对抗感被进一步拉高。"
    if profile["expand_emotion"] and "情绪" not in rewritten:
        rewritten = f"{rewritten}，人物情绪也因此被推到更显性的位置。"
    if profile["highlight_turning_point"] and "反转" not in rewritten and "转折" not in rewritten:
        rewritten = f"{rewritten}，并为后续反转埋下钩子。"
    return rewritten


def rewrite_dialogue_content(content: str, profile: dict[str, bool]) -> str:
    rewritten = content.strip().rstrip("。！？!?")
    if profile["compress_pacing"] and len(rewritten) > 16:
        rewritten = summarize_text(rewritten, limit=16).rstrip("。！？!?")
    if profile["enhance_conflict"]:
        return f"{rewritten}，你敢不敢正面回应？"
    if profile["highlight_turning_point"]:
        return f"{rewritten}，这次该换你接招了。"
    return f"{rewritten}。"


def apply_rewrite_instruction(scene: dict[str, Any], instruction: str) -> None:
    profile = build_rewrite_profile(instruction)
    rewritten_beats: list[dict[str, Any]] = []

    for beat in scene.get("beats", []):
        rewritten = deepcopy(beat)
        if beat["type"] == "action":
            rewritten["content"] = rewrite_action_content(beat["content"], profile)
        elif beat["type"] == "dialogue":
            rewritten["content"] = rewrite_dialogue_content(beat["content"], profile)
        rewritten_beats.append(rewritten)

    if profile["enhance_conflict"]:
        rewritten_beats.append(
            {
                "type": "action",
                "content": "双方的立场被迫提前摊开，场面进入更直接的对抗。",
            }
        )
    if profile["highlight_turning_point"]:
        rewritten_beats.append(
            {
                "type": "dialogue",
                "character": scene["characters"][0] if scene.get("characters") else "主角",
                "content": "这一回合到这里为止，真正的局面现在才开始。",
            }
        )

    if profile["compress_pacing"] and len(rewritten_beats) > 5:
        rewritten_beats = rewritten_beats[:4] + [rewritten_beats[-1]]

    scene["beats"] = rewritten_beats
    scene["purpose"] = rewrite_action_content(scene.get("purpose", ""), profile)
    scene["dramatic_structure"] = {
        **scene.get("dramatic_structure", {}),
        "obstacle": rewrite_action_content(scene["dramatic_structure"]["obstacle"], profile),
        "stakes": rewrite_action_content(scene["dramatic_structure"]["stakes"], profile),
        "turning_point": rewrite_action_content(scene["dramatic_structure"]["turning_point"], profile),
    }
    scene["adaptation_notes"] = {
        **scene.get("adaptation_notes", {}),
        "style": instruction,
        "pacing": (
            "快"
            if profile["compress_pacing"] or profile["highlight_turning_point"]
            else scene.get("adaptation_notes", {}).get("pacing", "中")
        ),
        "rewrite_focus": "、".join(
            label
            for enabled, label in (
                (profile["compress_pacing"], "节奏压缩"),
                (profile["enhance_conflict"], "冲突强化"),
                (profile["expand_emotion"], "情绪放大"),
                (profile["highlight_turning_point"], "反转前置"),
            )
            if enabled
        )
        or "局部润色",
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


def validate_script_or_raise(script: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_script_payload(script)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=make_error_response(42201, f"script validation failed: {error}"),
        ) from error


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

    script = validate_script_or_raise(build_script(project, chapters))
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

    apply_rewrite_instruction(scene, instruction)

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
    script = validate_script_or_raise(project["scripts"][active_version_id])
    content = dump_script_content(script, export_format)
    suffix = "json" if export_format.lower() == "json" else "yaml"
    file_name = f"{project_id}_{active_version_id}.{suffix}"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    export_path = EXPORTS_DIR / file_name
    export_path.write_text(content, encoding="utf-8")

    result = {
        "download_url": f"{API_PREFIX}/downloads/{file_name}",
        "file_name": file_name,
    }
    if include_report:
        result["report"] = {
            "version_id": active_version_id,
            "total_scenes": len(script["scenes"]),
        }

    update_task(store, task_id, status=TASK_SUCCEEDED, progress=100, result=result)
