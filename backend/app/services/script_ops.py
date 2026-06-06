from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from app.schemas import validate_script_payload
from app.services.common import make_error_response

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


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
