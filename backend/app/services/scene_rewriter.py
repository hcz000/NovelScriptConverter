"""场景重写服务：根据用户的改写指令对场景内容进行规则化或 LLM 驱动的改写。"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.services.llm_provider import request_json_object
from app.services.text_analysis import summarize_text


def build_rewrite_profile(instruction: str) -> dict[str, bool]:
    """解析重写指令字符串，生成改写配置概要。
    识别四种核心改写维度：压缩节奏、增强冲突、扩展情绪、突出反转。
    """
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
    """应用改写指令到场景（规则引擎模式）。
    原地修改场景的 beats、purpose、dramatic_structure 和 adaptation_notes。
    """
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


def llm_rewrite_scene(scene: dict[str, Any], instruction: str) -> dict[str, Any] | None:
    """使用 LLM 重写场景（大模型模式）。
    返回包含 purpose、dramatic_structure、beats、adaptation_notes 的 dict，
    如果 LLM 不可用或失败返回 None。
    """
    payload = {
        "title": scene["title"],
        "purpose": scene["purpose"],
        "characters": scene["characters"],
        "dramatic_structure": scene["dramatic_structure"],
        "beats": scene["beats"],
        "adaptation_notes": scene["adaptation_notes"],
    }
    system_prompt = (
        "你是小说改编编剧助手。"
        "请只重写输入场景的 beats、purpose、dramatic_structure、adaptation_notes，"
        "保持 scene_id、title、slugline、source_refs、characters 不变。"
        "输出必须是单个 JSON 对象。"
    )
    user_prompt = (
        f"重写指令：{instruction}\n"
        f"原场景 JSON：{json.dumps(payload, ensure_ascii=False)}\n"
        "请返回字段：purpose, dramatic_structure, beats, adaptation_notes。"
    )
    result = request_json_object(system_prompt, user_prompt)
    if not result:
        return None
    return result
