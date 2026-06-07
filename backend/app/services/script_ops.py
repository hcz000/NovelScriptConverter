"""剧本操作工具：提供版本管理、克隆、导出、场景查找、版本对比等操作。"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from app.schemas import validate_script_payload
from app.services.common import make_error_response

# 尝试导入 PyYAML（可选依赖），未安装时降级为 JSON 导出
try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def next_version_name(existing_versions: list[dict[str, Any]]) -> str:
    """根据已有版本数量生成下一个版本名称（v1.0, v1.1, ...）。"""
    if not existing_versions:
        return "v1.0"
    return f"v1.{len(existing_versions)}"


def clone_script(script: dict[str, Any]) -> dict[str, Any]:
    """深拷贝剧本（用于版本分支时创建独立副本）。"""
    return deepcopy(script)


def _format_beat_for_export(beat: dict[str, Any]) -> str:
    content = str(beat.get("content") or "").strip()
    if beat.get("type") == "dialogue":
        character = str(beat.get("character") or "未标明").strip()
        return f"{character}：{content}"
    return f"动作：{content}"


def build_readable_export_payload(script: dict[str, Any]) -> dict[str, Any]:
    """构建面向阅读和交付的导出视图，避免把内部编辑数据原样暴露给最终稿。"""
    source_summary = script.get("source_summary", {})
    project = script.get("project", {})
    metadata = script.get("metadata", {})
    readable_scenes = []
    for scene in script.get("scenes", []):
        dramatic_structure = scene.get("dramatic_structure", {})
        readable_scenes.append(
            {
                "scene_id": scene.get("scene_id"),
                "title": scene.get("title"),
                "heading": scene.get("slugline"),
                "purpose": scene.get("purpose"),
                "characters": scene.get("characters", []),
                "dramatic_notes": {
                    "objective": dramatic_structure.get("objective"),
                    "obstacle": dramatic_structure.get("obstacle"),
                    "turning_point": dramatic_structure.get("turning_point"),
                },
                "beats": [_format_beat_for_export(beat) for beat in scene.get("beats", [])],
            }
        )

    payload: dict[str, Any] = {
        "title": project.get("title"),
        "version": project.get("version"),
        "created_at": project.get("created_at"),
        "generation_source": metadata.get("generation_source", "unknown"),
        "premise": source_summary.get("premise"),
        "main_conflict": source_summary.get("main_conflict"),
        "main_characters": [
            f"{profile.get('name')}（{profile.get('role')}）"
            for profile in source_summary.get("main_characters", [])
        ],
        "scene_count": len(readable_scenes),
        "scenes": readable_scenes,
    }
    if metadata.get("llm_status"):
        payload["llm_status"] = metadata["llm_status"]
    if metadata.get("llm_fallback_reason"):
        payload["llm_fallback_reason"] = metadata["llm_fallback_reason"]

    quality_report = script.get("quality_report")
    if quality_report:
        payload["quality_report"] = {
            "overall_score": quality_report.get("overall_score"),
            "headline": quality_report.get("headline"),
            "revision_priorities": quality_report.get("revision_priorities", []),
        }
    return payload


def dump_script_content(script: dict[str, Any], export_format: str) -> str:
    export_format = export_format.lower()
    if export_format == "json":
        return json.dumps(script, ensure_ascii=False, indent=2)
    if yaml is None:
        return json.dumps(build_readable_export_payload(script), ensure_ascii=False, indent=2)
    return yaml.safe_dump(build_readable_export_payload(script), allow_unicode=True, sort_keys=False)


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


def _beat_signature(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": beat.get("type"),
            "character": beat.get("character"),
            "content": beat.get("content"),
        }
        for beat in beats
    ]


def _changed_fields(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    comparisons = {
        "title": (left.get("title"), right.get("title")),
        "slugline": (left.get("slugline"), right.get("slugline")),
        "purpose": (left.get("purpose"), right.get("purpose")),
        "characters": (left.get("characters", []), right.get("characters", [])),
        "dramatic_structure": (left.get("dramatic_structure", {}), right.get("dramatic_structure", {})),
        "beats": (_beat_signature(left.get("beats", [])), _beat_signature(right.get("beats", []))),
        "adaptation_notes": (left.get("adaptation_notes", {}), right.get("adaptation_notes", {})),
    }
    return [field for field, (left_value, right_value) in comparisons.items() if left_value != right_value]


def compare_scripts(left_script: dict[str, Any], right_script: dict[str, Any]) -> dict[str, Any]:
    """对比两个剧本版本的场景差异。
    返回每个场景的状态（新增/删除/修改/未变）和变更字段列表。
    """
    left_scenes = {scene["scene_id"]: scene for scene in left_script.get("scenes", [])}
    right_scenes = {scene["scene_id"]: scene for scene in right_script.get("scenes", [])}
    scene_ids = sorted(set(left_scenes) | set(right_scenes))

    scene_changes: list[dict[str, Any]] = []
    summary = {
        "added": 0,
        "removed": 0,
        "changed": 0,
        "unchanged": 0,
    }

    for scene_id in scene_ids:
        left_scene = left_scenes.get(scene_id)
        right_scene = right_scenes.get(scene_id)
        if left_scene is None and right_scene is not None:
            summary["added"] += 1
            scene_changes.append(
                {
                    "scene_id": scene_id,
                    "status": "added",
                    "title": right_scene.get("title"),
                    "changed_fields": [],
                }
            )
            continue
        if left_scene is not None and right_scene is None:
            summary["removed"] += 1
            scene_changes.append(
                {
                    "scene_id": scene_id,
                    "status": "removed",
                    "title": left_scene.get("title"),
                    "changed_fields": [],
                }
            )
            continue

        assert left_scene is not None and right_scene is not None
        changed_fields = _changed_fields(left_scene, right_scene)
        if changed_fields:
            summary["changed"] += 1
            status = "changed"
        else:
            summary["unchanged"] += 1
            status = "unchanged"
        scene_changes.append(
            {
                "scene_id": scene_id,
                "status": status,
                "title": right_scene.get("title") or left_scene.get("title"),
                "changed_fields": changed_fields,
            }
        )

    return {
        "summary": {
            **summary,
            "total": len(scene_changes),
        },
        "scenes": scene_changes,
    }
