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
