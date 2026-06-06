from __future__ import annotations

import json
from statistics import mean
from typing import Any

from app.services.llm_provider import request_json_object


QUALITY_REVIEW_SYSTEM_PROMPT = """
你是一名资深剧本审稿人，正在为小说转短剧/微短剧改编项目做比赛展示级审稿。
只返回 JSON 对象，不要 Markdown，不要解释。
评分要关注：戏剧冲突、角色动机、可拍性、对白表现、节奏钩子、原文覆盖、比赛展示亮点。
输出必须符合：
{
  "overall_score": 0-100,
  "headline": "120字以内的中文总评",
  "pitch_highlights": ["最多6条，每条说明适合比赛展示的亮点"],
  "metrics": [{"name": "50字以内", "score": 0-100, "rationale": "200字以内"}],
  "scene_notes": [{"scene_id": "SC001", "score": 0-100, "strengths": [], "risks": [], "suggestions": []}],
  "revision_priorities": ["最多6条，按收益排序"],
  "generated_by": "llm"
}
scene_notes 只能使用输入中存在的 scene_id。
""".strip()


def clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def trim_text(value: Any, max_length: int, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text[:max_length]


def normalize_string_list(value: Any, max_items: int, max_length: int, fallback: list[str]) -> list[str]:
    fallback_items = fallback if isinstance(fallback, list) else []
    if not isinstance(value, list):
        return fallback_items[:max_items]
    items = [trim_text(item, max_length) for item in value]
    items = [item for item in items if item]
    return (items or fallback_items)[:max_items]


def compact_scene_for_review(scene: dict[str, Any]) -> dict[str, Any]:
    structure = scene.get("dramatic_structure", {})
    return {
        "scene_id": scene.get("scene_id"),
        "title": trim_text(scene.get("title"), 80),
        "slugline": trim_text(scene.get("slugline"), 80),
        "purpose": trim_text(scene.get("purpose"), 180),
        "characters": scene.get("characters", [])[:6],
        "dramatic_structure": {
            "objective": trim_text(structure.get("objective"), 160),
            "obstacle": trim_text(structure.get("obstacle"), 160),
            "stakes": trim_text(structure.get("stakes"), 160),
            "turning_point": trim_text(structure.get("turning_point"), 160),
            "emotion_curve": structure.get("emotion_curve", [])[:6],
        },
        "beats": [
            {
                "type": beat.get("type"),
                "character": beat.get("character"),
                "content": trim_text(beat.get("content"), 120),
            }
            for beat in scene.get("beats", [])[:8]
        ],
        "source_refs": [
            {
                "chapter_id": ref.get("chapter_id"),
                "excerpt_summary": trim_text(ref.get("excerpt_summary"), 120),
            }
            for ref in scene.get("source_refs", [])[:3]
        ],
    }


def build_llm_review_payload(script: dict[str, Any], rule_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": script.get("project", {}),
        "source_summary": script.get("source_summary", {}),
        "metadata": script.get("metadata", {}),
        "character_relations": script.get("character_relations", [])[:12],
        "scene_plan": script.get("scene_plan", [])[:24],
        "scenes": [compact_scene_for_review(scene) for scene in script.get("scenes", [])[:24]],
        "rule_report_reference": {
            "overall_score": rule_report.get("overall_score"),
            "metrics": rule_report.get("metrics", []),
            "revision_priorities": rule_report.get("revision_priorities", []),
        },
    }


def normalize_metric(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    score = value.get("score", fallback.get("score", 0))
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = fallback.get("score", 0)
    name = trim_text(value.get("name"), 50, trim_text(fallback.get("name"), 50, "综合表现"))
    return {
        "name": name,
        "score": clamp_score(score_value),
        "rationale": trim_text(
            value.get("rationale"),
            200,
            trim_text(fallback.get("rationale"), 200, metric_rationale(name, clamp_score(score_value))),
        ),
    }


def normalize_scene_note(
    value: Any,
    fallback: dict[str, Any],
    valid_scene_ids: set[str],
) -> dict[str, Any] | None:
    value = value if isinstance(value, dict) else {}
    scene_id = trim_text(value.get("scene_id"), 20, trim_text(fallback.get("scene_id"), 20))
    if scene_id not in valid_scene_ids:
        return None

    score = value.get("score", fallback.get("score", 0))
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = fallback.get("score", 0)

    return {
        "scene_id": scene_id,
        "score": clamp_score(score_value),
        "strengths": normalize_string_list(value.get("strengths"), 4, 120, fallback.get("strengths", [])),
        "risks": normalize_string_list(value.get("risks"), 4, 120, fallback.get("risks", [])),
        "suggestions": normalize_string_list(value.get("suggestions"), 4, 120, fallback.get("suggestions", [])),
    }


def normalize_llm_quality_report(
    result: dict[str, Any],
    fallback_report: dict[str, Any],
    script: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None

    valid_scene_ids = {scene.get("scene_id") for scene in script.get("scenes", []) if scene.get("scene_id")}
    fallback_metrics = fallback_report.get("metrics", [])
    raw_metrics = result.get("metrics")
    if not isinstance(raw_metrics, list):
        raw_metrics = []
    metrics = [
        normalize_metric(metric, fallback_metrics[index] if index < len(fallback_metrics) else {})
        for index, metric in enumerate(raw_metrics[:8])
    ]
    metric_names = {metric["name"] for metric in metrics}
    for fallback_metric in fallback_metrics:
        fallback_name = trim_text(fallback_metric.get("name"), 50) if isinstance(fallback_metric, dict) else ""
        if len(metrics) >= 8:
            break
        if fallback_name and fallback_name not in metric_names:
            metrics.append(normalize_metric(fallback_metric, fallback_metric))
            metric_names.add(fallback_name)
    if not metrics:
        metrics = [normalize_metric(metric, metric) for metric in fallback_metrics[:8]]
    if not metrics:
        return None

    fallback_notes_by_id = {
        note.get("scene_id"): note
        for note in fallback_report.get("scene_notes", [])
        if note.get("scene_id")
    }
    raw_notes = result.get("scene_notes")
    if not isinstance(raw_notes, list):
        raw_notes = []
    scene_notes: list[dict[str, Any]] = []
    seen_scene_ids: set[str] = set()
    for raw_note in raw_notes:
        fallback = fallback_notes_by_id.get(raw_note.get("scene_id")) if isinstance(raw_note, dict) else None
        note = normalize_scene_note(raw_note, fallback or {}, valid_scene_ids)
        if note and note["scene_id"] not in seen_scene_ids:
            scene_notes.append(note)
            seen_scene_ids.add(note["scene_id"])

    for fallback_note in fallback_report.get("scene_notes", []):
        note = normalize_scene_note(fallback_note, fallback_note, valid_scene_ids)
        if note and note["scene_id"] not in seen_scene_ids:
            scene_notes.append(note)
            seen_scene_ids.add(note["scene_id"])

    score = result.get("overall_score", fallback_report.get("overall_score", mean(metric["score"] for metric in metrics)))
    try:
        overall_score = clamp_score(float(score))
    except (TypeError, ValueError):
        overall_score = fallback_report.get("overall_score", clamp_score(mean(metric["score"] for metric in metrics)))

    headline = trim_text(result.get("headline"), 120, trim_text(fallback_report.get("headline"), 120, "已完成剧本审稿。"))
    pitch_highlights = normalize_string_list(
        result.get("pitch_highlights"),
        6,
        120,
        fallback_report.get("pitch_highlights", []),
    )
    revision_priorities = normalize_string_list(
        result.get("revision_priorities"),
        6,
        160,
        fallback_report.get("revision_priorities", []),
    )

    return {
        "overall_score": overall_score,
        "headline": headline,
        "pitch_highlights": pitch_highlights,
        "metrics": metrics,
        "scene_notes": scene_notes,
        "revision_priorities": revision_priorities,
        "generated_by": "llm",
    }


def llm_review_quality_report(script: dict[str, Any], rule_report: dict[str, Any]) -> dict[str, Any] | None:
    payload = build_llm_review_payload(script, rule_report)
    user_prompt = (
        "请基于下面的剧本结构和规则审稿参考，生成更像专业审稿人的质量报告。"
        "重点指出比赛展示亮点、真正影响成片效果的问题，以及下一轮最值得改的事项。\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        result = request_json_object(QUALITY_REVIEW_SYSTEM_PROMPT, user_prompt)
    except Exception:
        return None
    if not result:
        return None
    return normalize_llm_quality_report(result, rule_report, script)


def score_dialogue(scene: dict[str, Any]) -> int:
    beats = scene.get("beats", [])
    if not beats:
        return 45
    dialogue_count = sum(1 for beat in beats if beat.get("type") == "dialogue")
    ratio = dialogue_count / len(beats)
    if ratio == 0:
        return 55
    if 0.25 <= ratio <= 0.65:
        return 86
    if ratio < 0.25:
        return 72
    return 68


def score_conflict(scene: dict[str, Any]) -> int:
    structure = scene.get("dramatic_structure", {})
    conflict_terms = (
        "冲突",
        "对抗",
        "阻碍",
        "失败",
        "主动权",
        "误判",
        "反转",
        "压力",
        " stakes",
    )
    text = " ".join(str(structure.get(field, "")) for field in ("obstacle", "stakes", "turning_point"))
    hits = sum(1 for term in conflict_terms if term in text)
    return clamp_score(58 + hits * 8)


def score_motivation(scene: dict[str, Any]) -> int:
    objective = scene.get("dramatic_structure", {}).get("objective", "")
    purpose = scene.get("purpose", "")
    characters = scene.get("characters", [])
    score = 58
    if objective:
        score += 18
    if purpose:
        score += 10
    if characters and characters[0] in objective:
        score += 8
    return clamp_score(score)


def score_shootability(scene: dict[str, Any]) -> int:
    score = 60
    if scene.get("slugline"):
        score += 12
    if 2 <= len(scene.get("beats", [])) <= 8:
        score += 14
    if scene.get("source_refs"):
        score += 6
    return clamp_score(score)


def score_pacing(scene: dict[str, Any]) -> int:
    notes = scene.get("adaptation_notes", {})
    beat_count = len(scene.get("beats", []))
    score = 62
    if notes.get("pacing") in {"快", "中"}:
        score += 12
    if 3 <= beat_count <= 8:
        score += 14
    if scene.get("dramatic_structure", {}).get("turning_point"):
        score += 8
    return clamp_score(score)


def build_scene_quality_note(scene: dict[str, Any]) -> dict[str, Any]:
    conflict = score_conflict(scene)
    motivation = score_motivation(scene)
    shootability = score_shootability(scene)
    dialogue = score_dialogue(scene)
    pacing = score_pacing(scene)
    scene_score = clamp_score(mean([conflict, motivation, shootability, dialogue, pacing]))

    strengths: list[str] = []
    risks: list[str] = []
    suggestions: list[str] = []

    if conflict >= 78:
        strengths.append("场景具备明确阻碍和转折，戏剧推进感较强。")
    else:
        risks.append("冲突压力还不够外显。")
        suggestions.append("强化对抗对象、失败代价或场景尾部反转。")

    if motivation >= 78:
        strengths.append("角色目标较清楚，便于演员和导演理解行动线。")
    else:
        risks.append("角色动机仍偏概括。")
        suggestions.append("把主角在本场想得到什么写得更具体。")

    if dialogue < 70:
        risks.append("对白占比偏弱，场景可能更像叙述摘要。")
        suggestions.append("补一到两句能暴露立场或关系变化的对白。")
    elif dialogue >= 80:
        strengths.append("动作和对白比例较均衡。")

    if shootability >= 80:
        strengths.append("场景行和节拍结构清晰，具备可拍性。")
    else:
        suggestions.append("补足地点、时间和可视化动作。")

    return {
        "scene_id": scene["scene_id"],
        "score": scene_score,
        "strengths": strengths[:4],
        "risks": risks[:4],
        "suggestions": suggestions[:4],
    }


def metric_rationale(name: str, score: int) -> str:
    if score >= 82:
        return f"{name}表现较稳定，已经具备展示价值。"
    if score >= 70:
        return f"{name}基本成立，但仍有提升空间。"
    return f"{name}是当前初稿的主要短板。"


def build_quality_report(script: dict[str, Any]) -> dict[str, Any]:
    scenes = script.get("scenes", [])
    if not scenes:
        return {
            "overall_score": 0,
            "headline": "暂无可评估场景。",
            "pitch_highlights": ["剧本尚未生成有效场景。"],
            "metrics": [],
            "scene_notes": [],
            "revision_priorities": ["先生成至少一个有效场景。"],
            "generated_by": "rule",
        }

    scene_notes = [build_scene_quality_note(scene) for scene in scenes]
    metric_scores = {
        "戏剧冲突": mean(score_conflict(scene) for scene in scenes),
        "角色动机": mean(score_motivation(scene) for scene in scenes),
        "可拍性": mean(score_shootability(scene) for scene in scenes),
        "对白表现": mean(score_dialogue(scene) for scene in scenes),
        "节奏与钩子": mean(score_pacing(scene) for scene in scenes),
        "原文覆盖": min(100, 58 + len(script.get("metadata", {}).get("chapter_to_scene_count", {})) * 8),
    }
    metrics = [
        {
            "name": name,
            "score": clamp_score(score),
            "rationale": metric_rationale(name, clamp_score(score)),
        }
        for name, score in metric_scores.items()
    ]
    overall_score = clamp_score(mean(metric["score"] for metric in metrics))

    weak_metrics = sorted(metrics, key=lambda item: item["score"])[:3]
    low_scenes = sorted(scene_notes, key=lambda item: item["score"])[:3]
    revision_priorities = [
        f"优先提升{metric['name']}：{metric['rationale']}"
        for metric in weak_metrics
        if metric["score"] < 78
    ]
    revision_priorities.extend(
        f"{note['scene_id']}：{note['suggestions'][0]}"
        for note in low_scenes
        if note["suggestions"]
    )

    title = script.get("project", {}).get("title", "当前项目")
    headline = (
        f"{title} 已形成可展示的场景化初稿，整体完成度 {overall_score} 分。"
        if overall_score >= 75
        else f"{title} 已具备初稿骨架，但仍需要强化戏剧张力。"
    )
    pitch_highlights = [
        f"已拆分为 {len(scenes)} 个可编辑场景，便于逐场打磨。",
        "每场包含目标、阻碍、转折和节拍，能解释改编判断。",
        "质量报告可直接定位弱场景和下一轮重写重点。",
    ]
    if script.get("scene_plan"):
        pitch_highlights.append("保留章节到场景映射，方便说明原文如何转化为剧本。")
    if script.get("character_relations"):
        pitch_highlights.append("已抽取角色关系，为人物弧光和冲突升级提供基础。")

    return {
        "overall_score": overall_score,
        "headline": headline,
        "pitch_highlights": pitch_highlights[:6],
        "metrics": metrics,
        "scene_notes": scene_notes,
        "revision_priorities": revision_priorities[:6],
        "generated_by": "rule",
    }


def attach_quality_report(script: dict[str, Any], use_llm: bool = True) -> dict[str, Any]:
    rule_report = build_quality_report(script)
    llm_report = llm_review_quality_report(script, rule_report) if use_llm else None
    script["quality_report"] = llm_report or rule_report
    return script
