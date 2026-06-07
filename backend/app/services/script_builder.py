"""剧本构建引擎：从章章节构建场景、生成节拍、推断戏剧结构和角色关系等核心功能。"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from copy import deepcopy
from typing import Any

from app.schemas import validate_script_payload
from app.services.common import date_str
from app.services.llm_provider import llm_enabled, request_json_object, set_last_llm_error
from app.services.quality_report import attach_quality_report
from app.services.text_analysis import (
    NARRATIVE_FRAGMENTS,
    extract_characters,
    extract_keywords,
    split_paragraphs,
    summarize_text,
)


UNKNOWN_DIALOGUE_CHARACTER = "未标明"


def _is_suspicious_character_name(name: str) -> bool:
    """判断角色名是否可疑（叙事片段而非真实人物名），使用跨小说通用的正则规则。"""
    if not name or len(name) < 2:
        return True
    if name in NARRATIVE_FRAGMENTS:
        return True
    if any(c.isdigit() for c in name):
        return True
    if re.search(r"[的得地在着过]", name):
        return True
    if len(name) >= 3 and re.search(r"[与及同跟和]", name):
        return True
    if re.search(r"(等级|级别|品阶|称号|状态|属性)$", name):
        return True
    if re.match(r"^(对|朝|看着|看向|望向|盯着|喊了|叫住|遇见|遇到|拦住)", name):
        return True
    if re.search(r"(说道|问道|喊道|叫道|地说|地道)$", name):
        return True
    if re.search(r"(在旁|一旁|身后|面前|之中|之间)$", name):
        return True
    if re.search(r"(面上|脸上|头上|手中|眼前|脚下|身上|背后)$", name):
        return True
    if re.search(r"(表情|神色|模样|样子|气息|气势|笑容)$", name):
        return True
    if re.search(r"(站着|坐着|躺着|走着|跑着|站在|坐在|躺在|走向|走到|来到|走上|走下|走进|走出|跑进|跑出|冲进|冲出)$", name):
        return True
    if len(name) >= 4 and re.search(r"[上下来去出入进退回]$", name):
        return True
    for fragment in NARRATIVE_FRAGMENTS:
        if len(fragment) >= 2 and fragment in name:
            return True
    return False


def llm_extract_characters(raw_chapters: list[dict[str, Any]]) -> list[str] | None:
    """使用 LLM 从小说文本中提取真实人物名列表。
    
    以所有章节前 600 字拼接为输入，要求 LLM 返回 JSON 数组。
    如果 LLM 不可用或调用失败，返回 None。
    """
    if not llm_enabled():
        return None
    excerpts = " ".join(c["text"][:600] for c in raw_chapters if c.get("text"))
    if not excerpts:
        return None
    excerpt = excerpts[:4000]

    system_prompt = "你是一个小说角色识别助手。"
    user_prompt = (
        '请从以下小说文本中提取所有人物姓名。\n'
        '要求：\n'
        '1. 只返回真正的人物角色名（如「林峰」「苏小小」等具体人物，不要抽象概念）\n'
        '2. 不要返回以下内容：\n'
        '   - 等级、能力、物品、地点、身份标签等概念词\n'
        '   - 叙事片段、普通动词、形容词、场所名\n'
        '3. 输出格式为 JSON 数组：["人物1", "人物2", ...]\n'
        '\n'
        f'文本：\n{excerpt}'
    )

    try:
        result = request_json_object(system_prompt, user_prompt)
    except Exception:
        return None

    if not result:
        return None

    # 兼容多种返回格式
    if isinstance(result, list):
        names = [str(n).strip() for n in result if isinstance(n, str) and len(n.strip()) >= 2]
    elif isinstance(result, dict):
        names = []
        for key in ("characters", "names", "人物", "角色", "name", "names_list"):
            if key in result and isinstance(result[key], list):
                names = [str(n).strip() for n in result[key] if isinstance(n, str) and len(n.strip()) >= 2]
                break
    else:
        return None

    return [n for n in names if not _is_suspicious_character_name(n)] or None


def build_chapters(raw_chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将原始章节数据构建为结构化章节记录。
    包括章节编号、摘要、人物提取、预计算场景候选数。
    """
    chapters: list[dict[str, Any]] = []

    # 尝试用 LLM 提取全局角色白名单
    llm_characters = llm_extract_characters(raw_chapters)

    for index, chapter in enumerate(raw_chapters, start=1):
        chapter_text = chapter["text"].strip()
        summary = summarize_text(chapter_text)

        # 先用规则引擎提取
        extracted = extract_characters(chapter_text)
        chapter_chars: list[str] = []

        if llm_characters:
            # 优先保留白名单中出现在本文的角色
            for c in extracted:
                if c in llm_characters and c not in chapter_chars:
                    chapter_chars.append(c)
            # 补充白名单中确实出现在文本中的角色
            for llm_c in llm_characters:
                if llm_c in chapter_text and llm_c not in chapter_chars:
                    chapter_chars.append(llm_c)
        else:
            # 无 LLM 白名单时：过滤可疑角色后保留
            chapter_chars = [c for c in extracted if not _is_suspicious_character_name(c)]

        chapter_chars = chapter_chars[:4] or ["主角"]

        chapter_record = {
            "chapter_id": f"CH{index:03d}",
            "title": chapter["title"][:80],
            "word_count": len(chapter_text),
            "summary": summary,
            "characters": chapter_chars,
            "scene_candidates": 1,
            "chapter_text": chapter_text,
        }
        chapter_record["scene_candidates"] = max(1, len(derive_scene_groups(chapter_record)))
        chapters.append(chapter_record)
    return chapters


def derive_scene_groups(chapter: dict[str, Any]) -> list[list[str]]:
    """将章节的段落按过渡标记和组大小规则分组为场景组。
    过渡标记如"与此同时"、"另一边"等表示场景切换。
    """
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


def extract_dialogue_fragments(paragraph: str, scene_characters: list[str] | None = None) -> list[dict[str, str]]:
    """从段落中提取对话片段。
    支持：
    - 引号对话（"…"）并推断说话人物
    - 冒号对话（角色名：对话内容）

    Args:
        paragraph: 段落文本
        scene_characters: 可选，场景角色白名单，用于校验提取的说话者是否合法

    Returns:
        对话片段列表，每项包含 character（说话者，可能为空）和 content（对话内容）
    """
    fragments: list[dict[str, str]] = []

    # 模式1：双引号对话
    quote_matches = re.findall(r"[“\"]([^”\"]{2,40})[”\"]", paragraph)
    if quote_matches:
        # 在整句中查找说话者模式：X说/问/道/喊/叫 + 冒号/逗号可选
        speaker_match = re.search(
            r"([\u4e00-\u9fff]{2,4})(说道|问道|喊道|叫道|[说问喊叫])([:：，,]?)",
            paragraph,
        )
        speaker = speaker_match.group(1) if speaker_match else ""
        # 如果说话者可疑或不在场景角色中，清空
        if speaker and scene_characters:
            if speaker not in scene_characters:
                speaker = ""
        elif speaker and _is_suspicious_character_name(speaker):
            speaker = ""

        for content in quote_matches:
            fragments.append({"character": speaker, "content": content.strip()})
        return fragments

    # 模式2：冒号对话
    colon_match = re.match(r"^\s*([\u4e00-\u9fff]{2,4})[：:]\s*(.+)$", paragraph)
    if colon_match:
        character = colon_match.group(1).strip()
        if scene_characters and character not in scene_characters:
            character = ""
        fragments.append(
            {
                "character": character,
                "content": colon_match.group(2).strip(),
            }
        )
    return fragments


def infer_time_of_day(text: str) -> str:
    """根据文本中的时间关键词推断场景发生时间（夜晚/清晨/傍晚/白天）。"""
    if re.search(r"夜|晚|月|深夜|凌晨", text):
        return "夜晚"
    if re.search(r"晨|清晨|早上|黎明", text):
        return "清晨"
    if re.search(r"黄昏|傍晚|日落", text):
        return "傍晚"
    return "白天"


def infer_scene_location(text: str, title: str) -> str:
    """根据文本和标题中的关键词推断场景地点（考场/走廊/客厅/办公室等）。"""
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
    """推断场景语：INT.（室内）或 EXT.（室外）。"""
    indoor_locations = ("考场", "走廊", "客厅", "办公室", "病房", "牢房")
    if location in indoor_locations:
        return "INT"
    outdoor_terms = ("街", "巷", "路口", "院", "山", "林", "战场", "营地", "码头", "桥")
    return "EXT" if any(term in location or term in text for term in outdoor_terms) else "INT"


def build_scene_slugline(chapter_title: str, scene_text: str) -> str:
    location = infer_scene_location(scene_text, chapter_title)
    return f"{infer_scene_prefix(location, scene_text)}. {location} - {infer_time_of_day(scene_text)}"


def infer_scene_pacing(paragraphs: list[str]) -> str:
    """根据段落中的动作动词密度推断场景节奏（快/中/慢）。"""
    joined = "".join(paragraphs)
    action_hits = len(re.findall(r"冲|追|逃|打|杀|撞|喊|奔|闯|爆|推|拦|逼", joined))
    if action_hits >= 4 or len(paragraphs) <= 2:
        return "快"
    if action_hits >= 2:
        return "中"
    return "慢"


def infer_scene_style(paragraphs: list[str]) -> str:
    """根据段落内容推断场景风格（冲突推进/情绪沉浸/叙事铺垫）。"""
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
    # 优先匹配章节级的角色，但过滤掉可疑角色
    matched = [c for c in chapter_characters if c in group_text and not _is_suspicious_character_name(c)]
    if matched:
        return matched[:4]
    extracted = extract_characters(group_text)
    # 过滤掉可疑角色
    extracted = [c for c in extracted if not _is_suspicious_character_name(c)]
    if extracted:
        return extracted[:4]
    fallback = [c for c in chapter_characters if c != UNKNOWN_DIALOGUE_CHARACTER and not _is_suspicious_character_name(c)]
    return fallback[:1] if fallback else ["主角"]


def build_beats_from_paragraphs(paragraphs: list[str], characters: list[str]) -> list[dict[str, Any]]:
    """从段落列表构建节拍（beats）列表。
    将叙述转为 action 节拍，对话转为 dialogue 节拍。
    如果没有对话则尝试生成一句适应性对白，确保场景有对白元素。
    """
    beats: list[dict[str, Any]] = []
    fallback_character = characters[0] if characters else UNKNOWN_DIALOGUE_CHARACTER
    character_set = set(characters)

    for paragraph in paragraphs:
        dialogues = extract_dialogue_fragments(paragraph, scene_characters=characters)
        narration = re.sub(r"[“\"][^”\"]{2,40}[”\"]", "", paragraph).strip()
        if narration:
            beats.append(
                {
                    "type": "action",
                    "content": summarize_text(narration, limit=80),
                }
            )
        for dialogue in dialogues:
            dialog_char = dialogue["character"]
            # 如果未提取到说话者，尝试在场景角色中找第一个出现在文本中的角色
            if not dialog_char:
                for c in characters:
                    if c in paragraph:
                        dialog_char = c
                        break
            # 没有明确证据时保持未知，避免把旁白或群众对白强行归给主角。
            if not dialog_char:
                dialog_char = UNKNOWN_DIALOGUE_CHARACTER
            # 说话者不在场景角色列表中，回退到未知标记
            if dialog_char not in character_set:
                dialog_char = UNKNOWN_DIALOGUE_CHARACTER
            beats.append(
                {
                    "type": "dialogue",
                    "character": dialog_char,
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
    """根据各章节中人物出场次数构建角色画像。
    按出场频次排序，分配角色定位（主角/关键配角/支撑角色）和预设特征。
    """
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
    """构建角色关系图谱：统计章节内人物的同场频率，推断关系类型。"""
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
    beats = build_beats_from_paragraphs(paragraphs, characters)
    for beat in beats:
        if beat.get("type") == "dialogue":
            character = beat.get("character") or UNKNOWN_DIALOGUE_CHARACTER
            if character not in characters:
                characters.append(character)
    characters = characters[:6]

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
        "beats": beats,
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


def validate_character_names(script: dict[str, Any]) -> dict[str, Any]:
    """后处理：校验剧本中所有角色名，剔除明显不是人名的项，记录警告到 metadata。"""
    suspicious_removed: list[str] = []

    def filter_names(names: list[str]) -> list[str]:
        valid = []
        for n in names:
            if _is_suspicious_character_name(n):
                suspicious_removed.append(n)
            else:
                valid.append(n)
        return valid[:4] if valid else ["主角"]

    # 校验 source_summary.main_characters
    valid_profiles = []
    for profile in script["source_summary"]["main_characters"]:
        name = profile["name"]
        if _is_suspicious_character_name(name):
            suspicious_removed.append(name)
        else:
            valid_profiles.append(profile)
    if not valid_profiles:
        valid_profiles = [{"name": "主角", "role": "主角", "traits": ["目标明确", "推动剧情"]}]
    script["source_summary"]["main_characters"] = valid_profiles

    # 校验所有场景的角色列表
    for scene in script["scenes"]:
        original = list(scene["characters"])
        filtered = filter_names(original)
        if filtered != original:
            scene["characters"] = filtered

    # 校验 scene_plan 的角色列表
    for entry in script.get("scene_plan", []):
        entry["characters"] = filter_names(entry["characters"])

    # 记录被移除的可疑角色到元数据
    if suspicious_removed:
        removed_unique = list(dict.fromkeys(suspicious_removed))[:10]
        script.setdefault("metadata", {})["suspicious_characters_removed"] = removed_unique

    return script


def build_script(project: dict[str, Any], chapters: list[dict[str, Any]]) -> dict[str, Any]:
    """核心方法：从项目和章节数据构建完整剧本（规则引擎模式）。
    包括场景构建、角色画像、关系图谱、质量报告等全部内容。
    """
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
    # 方案D：后处理校验 — 剔除可疑角色名
    script = validate_character_names(script)
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
    draft_summary = draft.get("source_summary", {})
    sample_scene = (draft.get("scenes") or [{}])[0]
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
                "excerpt": chapter["chapter_text"][:600],
            }
            for chapter in chapters
        ],
        "draft_context": {
            "premise": draft_summary.get("premise"),
            "main_conflict": draft_summary.get("main_conflict"),
            "main_characters": draft_summary.get("main_characters", []),
            "character_relations": draft.get("character_relations", [])[:8],
            "chapter_to_scene_count": draft.get("metadata", {}).get("chapter_to_scene_count", {}),
            "suggested_scene_count": min(max(5, len(chapters) * 3), 16),
        },
        "required_scene_shape": {
            "scene_id": "SC001",
            "title": sample_scene.get("title") or "场景标题",
            "slugline": sample_scene.get("slugline") or "INT. 关键场所 - 白天",
            "purpose": sample_scene.get("purpose") or "场景目的",
            "source_refs": [{"chapter_id": "CH001", "excerpt_summary": "对应原文摘要"}],
            "characters": ["角色A", "角色B"],
            "dramatic_structure": {
                "objective": "角色目标",
                "obstacle": "阻碍或对抗",
                "stakes": "失败代价",
                "turning_point": "尾部转折",
                "emotion_curve": ["铺垫", "拉紧", "转折"],
            },
            "beats": [
                {"type": "action", "content": "可拍动作"},
                {"type": "dialogue", "character": "角色A", "content": "对白"},
            ],
            "adaptation_notes": {
                "pacing": "快/中/慢",
                "style": "改编风格",
                "coverage": "覆盖的章节范围",
            },
        },
    }


def _trim_text(value: Any, max_length: int, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    return text[:max_length]


def _normalize_string_list(
    value: Any,
    *,
    max_items: int,
    max_length: int,
    fallback: list[str] | None = None,
) -> list[str]:
    items: list[str] = []
    if isinstance(value, list):
        for item in value:
            text = str(item or "").strip()[:max_length]
            if text and text not in items:
                items.append(text)
    if not items and fallback:
        for item in fallback:
            text = str(item or "").strip()[:max_length]
            if text and text not in items:
                items.append(text)
    return items[:max_items]


def _normalize_character_list(value: Any, fallback: list[str]) -> list[str]:
    names: list[str] = []
    raw_names = value if isinstance(value, list) else []
    for item in raw_names:
        name = str(item or "").strip()[:50]
        if not name or name in names:
            continue
        if name != UNKNOWN_DIALOGUE_CHARACTER and _is_suspicious_character_name(name):
            continue
        names.append(name)
    if not names:
        for item in fallback:
            name = str(item or "").strip()[:50]
            if not name or name in names:
                continue
            if name != UNKNOWN_DIALOGUE_CHARACTER and _is_suspicious_character_name(name):
                continue
            names.append(name)
    return names[:6] or [UNKNOWN_DIALOGUE_CHARACTER]


def _normalize_source_refs(
    value: Any,
    fallback: list[dict[str, Any]],
    chapter_ids: set[str],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    raw_refs = value if isinstance(value, list) else []
    fallback_ref = fallback[0] if fallback else {}
    fallback_chapter_id = str(fallback_ref.get("chapter_id") or next(iter(chapter_ids), "CH001"))
    fallback_summary = str(fallback_ref.get("excerpt_summary") or "对应原文章节")

    for item in raw_refs:
        if not isinstance(item, dict):
            continue
        chapter_id = str(item.get("chapter_id") or "").strip()
        if chapter_id not in chapter_ids:
            chapter_id = fallback_chapter_id
        refs.append(
            {
                "chapter_id": chapter_id,
                "excerpt_summary": _trim_text(item.get("excerpt_summary"), 300, fallback_summary),
            }
        )
    if not refs:
        refs.append(
            {
                "chapter_id": fallback_chapter_id,
                "excerpt_summary": _trim_text(fallback_summary, 300, "对应原文章节"),
            }
        )
    return refs


def _normalize_dramatic_structure(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    default_curve = ["铺垫", "推进", "转折"]
    emotion_curve = _normalize_string_list(
        raw.get("emotion_curve"),
        max_items=6,
        max_length=30,
        fallback=fallback.get("emotion_curve") or default_curve,
    )
    for item in default_curve:
        if len(emotion_curve) >= 3:
            break
        if item not in emotion_curve:
            emotion_curve.append(item)
    return {
        "objective": _trim_text(raw.get("objective"), 300, str(fallback.get("objective") or "推动本场目标")),
        "obstacle": _trim_text(raw.get("obstacle"), 300, str(fallback.get("obstacle") or "外部压力持续升级")),
        "stakes": _trim_text(raw.get("stakes"), 300, str(fallback.get("stakes") or "失去后续主动权")),
        "turning_point": _trim_text(raw.get("turning_point"), 300, str(fallback.get("turning_point") or "场景尾部出现新变化")),
        "emotion_curve": emotion_curve[:6],
    }


def _normalize_beats(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_beats = value if isinstance(value, list) and value else fallback
    beats: list[dict[str, Any]] = []
    for item in raw_beats[:12]:
        if not isinstance(item, dict):
            continue
        beat_type = "dialogue" if item.get("type") == "dialogue" else "action"
        beat = {
            "type": beat_type,
            "content": _trim_text(item.get("content"), 500, "场景动作继续推进。"),
        }
        if beat_type == "dialogue":
            character = _trim_text(item.get("character"), 50, UNKNOWN_DIALOGUE_CHARACTER)
            if character != UNKNOWN_DIALOGUE_CHARACTER and _is_suspicious_character_name(character):
                character = UNKNOWN_DIALOGUE_CHARACTER
            beat["character"] = character
        beats.append(beat)
    return beats or [{"type": "action", "content": "场景动作继续推进。"}]


def _repair_dialogue_characters(
    characters: list[str],
    beats: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    repaired_characters = list(dict.fromkeys(characters))[:6] or [UNKNOWN_DIALOGUE_CHARACTER]
    dialogue_characters: list[str] = []
    for beat in beats:
        if beat.get("type") != "dialogue":
            continue
        character = _trim_text(beat.get("character"), 50, UNKNOWN_DIALOGUE_CHARACTER)
        if character != UNKNOWN_DIALOGUE_CHARACTER and _is_suspicious_character_name(character):
            character = UNKNOWN_DIALOGUE_CHARACTER
        beat["character"] = character
        if character != UNKNOWN_DIALOGUE_CHARACTER and character not in dialogue_characters:
            dialogue_characters.append(character)

    for character in dialogue_characters:
        if character not in repaired_characters and len(repaired_characters) < 6:
            repaired_characters.append(character)

    needs_unknown = False
    allowed = set(repaired_characters)
    for beat in beats:
        if beat.get("type") == "dialogue" and beat.get("character") not in allowed:
            beat["character"] = UNKNOWN_DIALOGUE_CHARACTER
            needs_unknown = True

    if needs_unknown and UNKNOWN_DIALOGUE_CHARACTER not in repaired_characters:
        if len(repaired_characters) < 6:
            repaired_characters.append(UNKNOWN_DIALOGUE_CHARACTER)
        else:
            protected = {
                beat.get("character")
                for beat in beats
                if beat.get("type") == "dialogue" and beat.get("character") != UNKNOWN_DIALOGUE_CHARACTER
            }
            replace_index = next(
                (index for index, character in enumerate(repaired_characters) if character not in protected),
                len(repaired_characters) - 1,
            )
            repaired_characters[replace_index] = UNKNOWN_DIALOGUE_CHARACTER

    allowed = set(repaired_characters)
    for beat in beats:
        if beat.get("type") == "dialogue" and beat.get("character") not in allowed:
            beat["character"] = UNKNOWN_DIALOGUE_CHARACTER
    return repaired_characters[:6], beats


def _normalize_adaptation_notes(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    notes = {
        "pacing": _trim_text(raw.get("pacing"), 50, str(fallback.get("pacing") or "中")),
        "style": _trim_text(raw.get("style"), 100, str(fallback.get("style") or "剧情推进")),
        "coverage": None,
        "rewrite_focus": None,
    }
    coverage = raw.get("coverage", fallback.get("coverage"))
    rewrite_focus = raw.get("rewrite_focus", fallback.get("rewrite_focus"))
    if coverage:
        notes["coverage"] = _trim_text(coverage, 100, "")
    if rewrite_focus:
        notes["rewrite_focus"] = _trim_text(rewrite_focus, 100, "")
    return notes


def _normalize_llm_scene(
    value: Any,
    fallback: dict[str, Any],
    scene_index: int,
    chapter_ids: set[str],
) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    fallback = fallback or {}
    characters = _normalize_character_list(raw.get("characters"), fallback.get("characters", []))
    beats = _normalize_beats(raw.get("beats"), fallback.get("beats", []))
    characters, beats = _repair_dialogue_characters(characters, beats)
    scene = {
        "scene_id": f"SC{scene_index:03d}",
        "title": _trim_text(raw.get("title"), 120, str(fallback.get("title") or f"场景 {scene_index}")),
        "slugline": _trim_text(raw.get("slugline"), 120, str(fallback.get("slugline") or "INT. 关键场所 - 白天")),
        "purpose": _trim_text(raw.get("purpose"), 300, str(fallback.get("purpose") or "推动剧情冲突。")),
        "source_refs": _normalize_source_refs(raw.get("source_refs"), fallback.get("source_refs", []), chapter_ids),
        "characters": characters,
        "dramatic_structure": _normalize_dramatic_structure(
            raw.get("dramatic_structure"),
            fallback.get("dramatic_structure", {}),
        ),
        "beats": beats,
        "adaptation_notes": _normalize_adaptation_notes(
            raw.get("adaptation_notes"),
            fallback.get("adaptation_notes", {}),
        ),
    }
    return scene


def _normalize_source_summary(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    summary = {
        "premise": _trim_text(raw.get("premise"), 300, str(fallback.get("premise") or "核心情节待展开")),
        "main_conflict": _trim_text(raw.get("main_conflict"), 300, str(fallback.get("main_conflict") or "主角面对外部压力并争取主动")),
        "main_characters": deepcopy(fallback.get("main_characters") or [{"name": "主角", "role": "主角", "traits": ["推动剧情"]}]),
        "conflict_keywords": _normalize_string_list(
            raw.get("conflict_keywords"),
            max_items=6,
            max_length=30,
            fallback=fallback.get("conflict_keywords", []),
        ),
        "chapter_highlights": _normalize_string_list(
            raw.get("chapter_highlights"),
            max_items=6,
            max_length=120,
            fallback=fallback.get("chapter_highlights", []),
        ),
    }
    raw_profiles = raw.get("main_characters")
    profiles: list[dict[str, Any]] = []
    if isinstance(raw_profiles, list):
        for item in raw_profiles:
            if isinstance(item, dict):
                name = _trim_text(item.get("name"), 50, "")
                if not name or _is_suspicious_character_name(name):
                    continue
                profiles.append(
                    {
                        "name": name,
                        "role": _trim_text(item.get("role"), 50, "主要角色"),
                        "traits": _normalize_string_list(
                            item.get("traits"),
                            max_items=5,
                            max_length=30,
                            fallback=["推动剧情"],
                        ),
                    }
                )
            elif isinstance(item, str) and not _is_suspicious_character_name(item):
                profiles.append({"name": item[:50], "role": "主要角色", "traits": ["推动剧情"]})
    if profiles:
        summary["main_characters"] = profiles[:5]
    return summary


def _normalize_character_relations(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, str]]:
    raw_relations = value if isinstance(value, list) else []
    relations: list[dict[str, str]] = []
    for item in raw_relations:
        if not isinstance(item, dict):
            continue
        pair = _trim_text(item.get("pair"), 100, "")
        relationship = _trim_text(item.get("relationship"), 100, "")
        if pair and relationship:
            relations.append({"pair": pair, "relationship": relationship})
    if relations:
        return relations
    return [
        {
            "pair": _trim_text(item.get("pair"), 100, "人物关系"),
            "relationship": _trim_text(item.get("relationship"), 100, "同场关联"),
        }
        for item in fallback
        if isinstance(item, dict)
    ]


def normalize_llm_script_payload(result: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """Repair common LLM schema drift before strict Pydantic validation."""
    normalized = deepcopy(draft)
    raw = result if isinstance(result, dict) else {}
    draft_chapters = deepcopy(draft.get("chapters", []))
    chapter_ids = {chapter.get("chapter_id") for chapter in draft_chapters if chapter.get("chapter_id")}
    if not chapter_ids:
        chapter_ids = {"CH001"}

    raw_project = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    draft_project = draft.get("project", {})
    normalized["project"] = {
        "title": _trim_text(raw_project.get("title"), 200, str(draft_project.get("title") or "剧本初稿")),
        "source_type": "novel",
        "source_chapter_count": len(draft_chapters),
        "language": _trim_text(raw_project.get("language"), 20, str(draft_project.get("language") or "zh-CN")),
        "created_at": _trim_text(raw_project.get("created_at"), 40, str(draft_project.get("created_at") or date_str())),
        "version": _trim_text(raw_project.get("version"), 20, str(draft_project.get("version") or "1.0")),
    }
    normalized["chapters"] = draft_chapters
    normalized["source_summary"] = _normalize_source_summary(raw.get("source_summary"), draft.get("source_summary", {}))

    draft_scenes = draft.get("scenes", [])
    raw_scenes = raw.get("scenes") if isinstance(raw.get("scenes"), list) and raw.get("scenes") else draft_scenes
    scenes: list[dict[str, Any]] = []
    for index, raw_scene in enumerate(raw_scenes, start=1):
        fallback = draft_scenes[min(index - 1, len(draft_scenes) - 1)] if draft_scenes else {}
        scenes.append(_normalize_llm_scene(raw_scene, fallback, index, chapter_ids))
    normalized["scenes"] = scenes

    raw_metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    draft_metadata = draft.get("metadata", {})
    estimated_runtime = raw_metadata.get("estimated_runtime_minutes")
    if not isinstance(estimated_runtime, (int, float)) or estimated_runtime < 1:
        estimated_runtime = draft_metadata.get("estimated_runtime_minutes") or max(5, len(scenes) * 4)
    conflict_keywords = _normalize_string_list(
        raw_metadata.get("conflict_keywords"),
        max_items=8,
        max_length=30,
        fallback=normalized["source_summary"].get("conflict_keywords", []),
    )
    normalized["metadata"] = {
        "total_scenes": len(scenes),
        "estimated_runtime_minutes": int(estimated_runtime),
        "editable": raw_metadata.get("editable") if isinstance(raw_metadata.get("editable"), bool) else True,
        "scene_density": round(len(scenes) / max(1, len(draft_chapters)), 2),
        "chapter_to_scene_count": build_chapter_to_scene_count(scenes),
        "conflict_keywords": conflict_keywords,
        "generation_source": "llm",
        "llm_status": None,
        "llm_fallback_reason": None,
    }
    normalized["versions"] = []
    normalized["character_relations"] = _normalize_character_relations(
        raw.get("character_relations"),
        draft.get("character_relations", []),
    )
    normalized["scene_plan"] = [build_scene_plan_entry(scene) for scene in scenes]
    normalized["quality_report"] = deepcopy(draft.get("quality_report", normalized.get("quality_report")))
    return normalized


def llm_generate_script(project: dict[str, Any], chapters: list[dict[str, Any]], draft: dict[str, Any]) -> dict[str, Any] | None:
    """使用 LLM 生成剧本（大模型模式）。
    以规则引擎生成的草稿为参考，通过 OpenAI API 生成更高质量的剧本。
    如果 LLM 未启用或调用失败，返回 None，调用方应降级使用规则引擎结果。
    """
    payload = build_llm_generation_payload(project, chapters, draft)
    system_prompt = (
        "你是小说改编编剧助手。请根据输入章节生成完整剧本初稿 JSON。"
        "你要做的是改编，不是摘抄：需要识别真实人物，剔除能力、等级、物品、地点、称谓等非人物项；"
        "把叙事转成可拍动作，把内心和背景压缩成场景目标、转折和必要对白。"
        "每个场景要有明确开端、冲突推进和尾部钩子，最后一个场景要有阶段性收束。"
        "必须保留并强化人物表、主冲突、章节到场景映射和场景节拍。"
        "不要自造后端运行状态、API 状态、质量报告或版本记录。"
        "输出必须是单个 JSON 对象，重点包含 source_summary、scenes、character_relations。"
    )
    user_prompt = (
        "请把小说章节改编成可编辑的剧本初稿。\n"
        "硬性要求：\n"
        "1. project.source_chapter_count 必须等于输入章节数。\n"
        "2. metadata.total_scenes 必须等于 scenes 数量。\n"
        "3. 每个 scene_id 使用 SC001 递增格式，每个 chapter_id 使用输入中的 CH 编号。\n"
        "4. dialogue beat 的 character 必须存在于该场景 characters。\n"
        "5. 不要把能力、等级、物品、地点、身份标签、旁白片段当成角色名。\n"
        "6. 场景数量要服务剧情节奏，不要按段落机械拆分；首轮优先 5-16 场，每章 2-5 场，相邻同地点同冲突的内容可以合并。\n"
        "7. 每场 beats 控制在 3-6 条；最后一个场景的 turning_point 和 beats 要有阶段性结束感，而不是简单截断原文。\n"
        "8. 可以只输出 source_summary、scenes、character_relations；project、chapters、metadata、scene_plan、versions、quality_report 由后端补齐。\n"
        "9. 如果输出 metadata，generation_source 固定为 \"llm\"，llm_status 使用 null，versions 使用 []。\n"
        f"输入 JSON：{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        result = request_json_object(system_prompt, user_prompt)
    except Exception as error:
        set_last_llm_error(f"LLM generation request failed: {error}")
        return None
    if not result:
        return None

    try:
        normalized = normalize_llm_script_payload(result, draft)
        return validate_script_payload(normalized)
    except Exception as error:
        set_last_llm_error(f"LLM script validation failed: {error}")
        return None
