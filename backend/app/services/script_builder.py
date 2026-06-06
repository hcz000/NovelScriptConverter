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


def infer_scene_location(text: str, title: str) -> str:
    combined = f"{title} {text}"
    location_rules = (
        ("考场", ("考场", "考试", "测试官", "石碑", "资格")),
        ("走廊", ("走廊", "楼道", "门外", "楼梯")),
        ("客厅", ("客厅", "沙发", "茶几", "家里")),
        ("办公室", ("办公室", "会议室", "桌前", "文件")),
        ("街口", ("街", "巷", "路口", "人群", "车")),
        ("院落", ("院", "庭院", "门廊", "雨檐")),
        ("山林", ("山", "林", "树林", "山路")),
        ("病房", ("医院", "病房", "护士", "医生")),
        ("牢房", ("牢", "狱", "铁门", "囚")),
        ("战场", ("战场", "营地", "刀", "枪", "冲杀")),
    )
    for location, keywords in location_rules:
        if any(keyword in combined for keyword in keywords):
            return location
    return "关键场所"


def infer_scene_prefix(location: str, text: str) -> str:
    indoor_locations = ("考场", "走廊", "客厅", "办公室", "病房", "牢房")
    if location in indoor_locations:
        return "INT"
    outdoor_terms = ("街", "巷", "路口", "院", "山", "林", "战场", "营地", "码头", "桥")
    return "EXT" if any(term in location or term in text for term in outdoor_terms) else "INT"


def build_scene_slugline(chapter_title: str, scene_text: str) -> str:
    location = infer_scene_location(scene_text, chapter_title)
    return f"{infer_scene_prefix(location, scene_text)}. {location} - {infer_time_of_day(scene_text)}"


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


def infer_scene_function(paragraphs: list[str], scene_index: int, group_index: int, total_groups: int) -> str:
    joined = "".join(paragraphs)
    if scene_index == 1:
        return "开场钩子"
    if re.search(r"忽然|突然|亮|出现|发现|打断|反转|揭开", joined):
        return "反转钩子"
    if re.search(r"争|怒|逼|威胁|质问|反击|不退", joined):
        return "冲突升级"
    if re.search(r"沉默|观察|试探|看着|没有退让", joined):
        return "关系试探"
    if group_index == total_groups:
        return "章节收束"
    return "信息推进"


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

    has_dialogue = any(beat["type"] == "dialogue" for beat in beats)
    if not has_dialogue and len(characters) >= 2 and len(beats) < 12:
        beats.insert(
            min(1, len(beats)),
            {
                "type": "dialogue",
                "character": fallback_character,
                "content": build_adapted_dialogue(paragraphs, fallback_character),
            },
        )
    return beats[:12]


def build_adapted_dialogue(paragraphs: list[str], character: str) -> str:
    joined = "".join(paragraphs)
    if re.search(r"资格|淘汰|失败|考试|测试", joined):
        return "我不会在这里认输。"
    if re.search(r"沉默|观察|看着|试探", joined):
        return "你一直看着我，是想等我先露怯？"
    if re.search(r"威胁|逼|拦|退让", joined):
        return "这一步我必须走下去。"
    return f"{character}不能再被局势推着走。"


def infer_failure_cost(scene_text: str, primary_character: str) -> str:
    if re.search(r"资格|考试|测试|淘汰", scene_text):
        return f"如果这一场失败，{primary_character}会失去资格，并被迫退出当前机会。"
    if re.search(r"身份|暴露|秘密", scene_text):
        return f"如果这一场失败，{primary_character}的身份或秘密会被提前暴露。"
    if re.search(r"信任|误会|背叛|退让", scene_text):
        return f"如果这一场失败，{primary_character}会失去关键人物的信任。"
    if re.search(r"死|杀|危险|追|逃", scene_text):
        return f"如果这一场失败，{primary_character}将面对直接的人身危险。"
    return f"如果这一场失败，{primary_character}后续将失去主动权。"


def infer_obstacle(scene_text: str, primary_character: str, characters: list[str], conflict_label: str) -> str:
    secondary_character = next((character for character in characters if character != primary_character), "")
    if secondary_character and re.search(r"冷|逼|质问|拦|观察|退让|沉默|看着", scene_text):
        return f"{secondary_character}的审视或施压不断升级，叠加{conflict_label}造成阻碍。"
    return f"场景中持续存在{conflict_label}带来的阻碍与误判。"


def infer_turning_point(paragraphs: list[str], chapter_title: str) -> str:
    tail = paragraphs[-1] if paragraphs else chapter_title
    tail_summary = summarize_text(tail, limit=70)
    if re.search(r"忽然|突然|亮|出现|发现|打断|冲进|反转", tail):
        return f"尾部“{tail_summary}”打断原有判断，形成下一场钩子。"
    return f"场景后段围绕“{tail_summary or chapter_title}”出现新的态度或信息变化。"


def build_scene_dramatic_structure(
    chapter: dict[str, Any],
    paragraphs: list[str],
    scene_summary: str,
    characters: list[str],
    scene_function: str,
) -> dict[str, Any]:
    primary_character = characters[0] if characters else "主角"
    scene_text = "".join(paragraphs)
    conflict_keywords = extract_keywords(scene_text, limit=3)
    conflict_label = "、".join(conflict_keywords[:2]) if conflict_keywords else "外部压力"
    return {
        "objective": f"{primary_character}要在“{scene_summary[:24] or chapter['title']}”中夺回主动权，完成本场的{scene_function}。",
        "obstacle": infer_obstacle(scene_text, primary_character, characters, conflict_label),
        "stakes": infer_failure_cost(scene_text, primary_character),
        "turning_point": infer_turning_point(paragraphs, chapter["title"]),
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
    pair_context: dict[tuple[str, str], list[str]] = {}
    for chapter in chapters:
        characters = chapter["characters"][:4]
        for index, left in enumerate(characters):
            for right in characters[index + 1 :]:
                pair = tuple(sorted((left, right)))
                pair_counter[pair] += 1
                pair_context.setdefault(pair, []).append(chapter["chapter_text"][:400])

    relations: list[dict[str, Any]] = []
    for (left, right), count in pair_counter.most_common(5):
        relationship = infer_relationship_label(pair_context.get((left, right), []), count)
        relations.append(
            {
                "pair": f"{left} / {right}",
                "relationship": relationship,
            }
        )
    return relations


def infer_relationship_label(contexts: list[str], count: int) -> str:
    joined = "".join(contexts)
    if re.search(r"对峙|没有退让|质问|威胁|反击|气氛更紧", joined):
        return "持续对峙关系，适合转化为场景冲突线"
    if re.search(r"观察|看着|试探|沉默", joined):
        return "互相观察和试探的关系张力"
    if count >= 2:
        return "高频同场关系，可承接人物弧光"
    return "同章关联角色，可作为场景变量"


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
    scene_function = infer_scene_function(paragraphs, scene_index, group_index, total_groups)
    scene_title = chapter["title"][:48]
    if total_groups > 1:
        scene_title = f"{scene_title} - {scene_function}"

    return {
        "scene_id": f"SC{scene_index:03d}",
        "title": scene_title,
        "slugline": build_scene_slugline(chapter["title"], scene_text),
        "purpose": scene_summary,
        "source_refs": [
            {
                "chapter_id": chapter["chapter_id"],
                "excerpt_summary": scene_summary,
            }
        ],
        "characters": characters,
        "dramatic_structure": build_scene_dramatic_structure(
            chapter,
            paragraphs,
            scene_summary,
            characters,
            scene_function,
        ),
        "beats": build_beats_from_paragraphs(paragraphs, characters),
        "adaptation_notes": {
            "pacing": infer_scene_pacing(paragraphs),
            "style": f"{infer_scene_style(paragraphs)} / {scene_function}",
            "coverage": f"{chapter['chapter_id']} 第 {group_index}/{total_groups} 段场景",
        },
    }


def build_scene_plan_entry(scene: dict[str, Any]) -> dict[str, Any]:
    source_ref = scene["source_refs"][0]
    return {
        "scene_id": scene["scene_id"],
        "chapter_id": source_ref["chapter_id"],
        "focus": f"{scene['adaptation_notes']['style']}：{scene['purpose']}"[:120],
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
    character_profiles = build_character_profiles(chapters)
    main_conflict = build_main_conflict(chapters, character_profiles, conflict_seed)
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
            "main_characters": character_profiles,
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


def build_main_conflict(
    chapters: list[dict[str, Any]],
    character_profiles: list[dict[str, Any]],
    conflict_seed: list[str],
) -> str:
    protagonist = character_profiles[0]["name"] if character_profiles else "主角"
    opposing_force = "、".join(conflict_seed[:2]) if conflict_seed else "外部压力"
    chapter_count = len(chapters)
    return (
        f"{protagonist}在{chapter_count}个章节事件中不断遭遇{opposing_force}，"
        "必须通过一次次场景选择夺回主动权；人物关系会持续把外部事件转化为可拍冲突。"
    )


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
