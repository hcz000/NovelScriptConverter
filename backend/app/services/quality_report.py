from __future__ import annotations

from statistics import mean
from typing import Any


def clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


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


def attach_quality_report(script: dict[str, Any]) -> dict[str, Any]:
    script["quality_report"] = build_quality_report(script)
    return script
