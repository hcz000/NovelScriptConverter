from typing import Any

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    language: str = Field(default="zh-CN")


class ParseProjectRequest(BaseModel):
    min_chapter_count: int = Field(default=3, ge=1, le=100)
    split_mode: str = Field(default="auto")


class GenerateScriptRequest(BaseModel):
    target_format: str = Field(default="yaml")
    scene_granularity: str = Field(default="standard")
    include_report: bool = Field(default=True)


class UpdateSceneRequest(BaseModel):
    title: str | None = None
    slugline: str | None = None
    purpose: str | None = None
    beats: list[dict[str, Any]] | None = None
    adaptation_notes: dict[str, Any] | None = None
    change_note: str | None = None


class RewriteSceneRequest(BaseModel):
    instruction: str = Field(..., min_length=1)
    preserve_core_event: bool = Field(default=True)
    create_new_version: bool = Field(default=True)


class ExportScriptRequest(BaseModel):
    version_id: str | None = None
    format: str = Field(default="yaml")
    include_report: bool = Field(default=True)

