from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

from app.schemas import validate_script_payload
from app.services.common import date_str
from app.services.llm_provider import request_json_object
from app.services.quality_report import attach_quality_report
from app.services.text_analysis import (
    extract_characters,
    extract_keywords,
    split_paragraphs,
    summarize_text,
)


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


def build_character_relations(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pair_counter = Counter()
    for chapter in chapters:
        characters = chapter["characters"][:4]
        for index, left in enumerate(characters):
            for right in characters[index + 1 :]:
                pair_counter[tuple(sorted((left, right)))] += 1

    relations: list[dict[str, Any]] = []
    for (left, right), count in pair_counter.most_common(5):
        relationship = "高频同场角色关系" if count >= 2 else "同章关联角色"
        relations.append(
            {
                "pair": f"{left} / {right}",
                "relationship": relationship,
            }
        )
    return relations


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


def build_scene_plan_entry(scene: dict[str, Any]) -> dict[str, Any]:
    source_ref = scene["source_refs"][0]
    return {
        "scene_id": scene["scene_id"],
        "chapter_id": source_ref["chapter_id"],
        "focus": scene["purpose"][:120],
        "characters": scene["characters"],
    }


def build_chapter_to_scene_count(scenes: list[dict[str, Any]]) -> dict[str, int]:
    mapping = Counter()
    for scene in scenes:
        for source_ref in scene.get("source_refs", []):
            mapping[source_ref["chapter_id"]] += 1
    return dict(mapping)


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
    chapter_highlights = [chapter["summary"][:60] for chapter in chapters[:5]]
    scene_plan = [build_scene_plan_entry(scene) for scene in scenes]
    chapter_to_scene_count = build_chapter_to_scene_count(scenes)

    script = {
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
            "conflict_keywords": conflict_seed,
            "chapter_highlights": chapter_highlights,
        },
        "chapters": chapter_summaries,
        "scenes": scenes,
        "metadata": {
            "total_scenes": len(scenes),
            "estimated_runtime_minutes": max(5, len(scenes) * 4),
            "editable": True,
            "scene_density": round(len(scenes) / max(1, len(chapters)), 2),
            "chapter_to_scene_count": chapter_to_scene_count,
            "conflict_keywords": conflict_seed,
        },
        "versions": [],
        "character_relations": build_character_relations(chapters),
        "scene_plan": scene_plan,
    }
    return attach_quality_report(script, use_llm=False)


def build_llm_generation_payload(project: dict[str, Any], chapters: list[dict[str, Any]], draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": {
            "title": project["title"],
            "language": project["language"],
        },
        "chapters": [
            {
                "chapter_id": chapter["chapter_id"],
                "title": chapter["title"],
                "summary": chapter["summary"],
                "characters": chapter["characters"],
                "scene_candidates": chapter["scene_candidates"],
                "excerpt": chapter["chapter_text"][:800],
            }
            for chapter in chapters
        ],
        "draft_schema_reference": draft,
    }


def llm_generate_script(project: dict[str, Any], chapters: list[dict[str, Any]], draft: dict[str, Any]) -> dict[str, Any] | None:
    payload = build_llm_generation_payload(project, chapters, draft)
    system_prompt = (
        "你是小说改编编剧助手。请根据输入章节生成完整剧本初稿 JSON。"
        "必须保留并强化人物表、主冲突、章节到场景映射、场景节拍和版本元数据。"
        "输出必须是单个 JSON 对象，并严格符合参考草稿的字段结构。"
    )
    user_prompt = (
        "请把小说章节改编成可编辑的剧本初稿。\n"
        "硬性要求：\n"
        "1. project.source_chapter_count 必须等于输入章节数。\n"
        "2. metadata.total_scenes 必须等于 scenes 数量。\n"
        "3. 每个 scene_id 使用 SC001 递增格式，每个 chapter_id 使用输入中的 CH 编号。\n"
        "4. dialogue beat 的 character 必须存在于该场景 characters。\n"
        "5. 保留 source_summary, character_relations, scene_plan, metadata.chapter_to_scene_count。\n"
        f"输入 JSON：{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        result = request_json_object(system_prompt, user_prompt)
    except Exception:
        return None
    if not result:
        return None

    try:
        return validate_script_payload(result)
    except Exception:
        return None
