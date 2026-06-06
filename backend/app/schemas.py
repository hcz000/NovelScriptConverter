from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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


class BeatSchema(BaseModel):
    type: Literal["action", "dialogue"]
    content: str = Field(..., min_length=1, max_length=500)
    character: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_dialogue_character(self) -> "BeatSchema":
        if self.type == "dialogue" and not self.character:
            raise ValueError("dialogue beat requires character")
        return self


class SourceRefSchema(BaseModel):
    chapter_id: str = Field(..., min_length=1, max_length=20)
    excerpt_summary: str = Field(..., min_length=1, max_length=300)


class DramaticStructureSchema(BaseModel):
    objective: str = Field(..., min_length=1, max_length=300)
    obstacle: str = Field(..., min_length=1, max_length=300)
    stakes: str = Field(..., min_length=1, max_length=300)
    turning_point: str = Field(..., min_length=1, max_length=300)
    emotion_curve: list[str] = Field(..., min_length=3, max_length=6)


class AdaptationNotesSchema(BaseModel):
    pacing: str = Field(..., min_length=1, max_length=50)
    style: str = Field(..., min_length=1, max_length=100)
    coverage: str | None = Field(default=None, max_length=100)
    rewrite_focus: str | None = Field(default=None, max_length=100)


class SceneSchema(BaseModel):
    scene_id: str = Field(..., pattern=r"^SC\d{3}$")
    title: str = Field(..., min_length=1, max_length=120)
    slugline: str = Field(..., min_length=1, max_length=120)
    purpose: str = Field(..., min_length=1, max_length=300)
    source_refs: list[SourceRefSchema] = Field(..., min_length=1)
    characters: list[str] = Field(..., min_length=1, max_length=6)
    dramatic_structure: DramaticStructureSchema
    beats: list[BeatSchema] = Field(..., min_length=1, max_length=12)
    adaptation_notes: AdaptationNotesSchema

    @model_validator(mode="after")
    def validate_dialogue_characters(self) -> "SceneSchema":
        character_set = set(self.characters)
        for beat in self.beats:
            if beat.type == "dialogue" and beat.character not in character_set:
                raise ValueError(f"dialogue character '{beat.character}' not in scene characters")
        return self


class ChapterSchema(BaseModel):
    chapter_id: str = Field(..., pattern=r"^CH\d{3}$")
    title: str = Field(..., min_length=1, max_length=120)
    summary: str = Field(..., min_length=1, max_length=300)


class CharacterProfileSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    role: str = Field(..., min_length=1, max_length=50)
    traits: list[str] = Field(..., min_length=1, max_length=5)


class SourceSummarySchema(BaseModel):
    premise: str = Field(..., min_length=1, max_length=300)
    main_conflict: str = Field(..., min_length=1, max_length=300)
    main_characters: list[CharacterProfileSchema] = Field(..., min_length=1, max_length=5)
    conflict_keywords: list[str] = Field(default_factory=list, max_length=6)
    chapter_highlights: list[str] = Field(default_factory=list, max_length=6)


class CharacterRelationSchema(BaseModel):
    pair: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field(..., min_length=1, max_length=100)


class ScenePlanEntrySchema(BaseModel):
    scene_id: str = Field(..., pattern=r"^SC\d{3}$")
    chapter_id: str = Field(..., pattern=r"^CH\d{3}$")
    focus: str = Field(..., min_length=1, max_length=200)
    characters: list[str] = Field(..., min_length=1, max_length=6)


class ProjectMetaSchema(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    source_type: Literal["novel"]
    source_chapter_count: int = Field(..., ge=1, le=200)
    language: str = Field(..., min_length=2, max_length=20)
    created_at: str = Field(..., min_length=8, max_length=40)
    version: str = Field(..., min_length=1, max_length=20)


class ScriptVersionEntrySchema(BaseModel):
    version: str = Field(..., min_length=1, max_length=20)
    created_at: str = Field(..., min_length=8, max_length=40)
    description: str = Field(..., min_length=1, max_length=200)


class ScriptMetadataSchema(BaseModel):
    total_scenes: int = Field(..., ge=1)
    estimated_runtime_minutes: int = Field(..., ge=1)
    editable: bool
    scene_density: float | None = Field(default=None, ge=0)
    chapter_to_scene_count: dict[str, int] = Field(default_factory=dict)
    conflict_keywords: list[str] = Field(default_factory=list, max_length=8)


class QualityMetricSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    score: int = Field(..., ge=0, le=100)
    rationale: str = Field(..., min_length=1, max_length=200)


class SceneQualityNoteSchema(BaseModel):
    scene_id: str = Field(..., pattern=r"^SC\d{3}$")
    score: int = Field(..., ge=0, le=100)
    strengths: list[str] = Field(default_factory=list, max_length=4)
    risks: list[str] = Field(default_factory=list, max_length=4)
    suggestions: list[str] = Field(default_factory=list, max_length=4)


class QualityReportSchema(BaseModel):
    overall_score: int = Field(..., ge=0, le=100)
    headline: str = Field(..., min_length=1, max_length=120)
    pitch_highlights: list[str] = Field(..., min_length=1, max_length=6)
    metrics: list[QualityMetricSchema] = Field(..., min_length=1, max_length=8)
    scene_notes: list[SceneQualityNoteSchema] = Field(default_factory=list)
    revision_priorities: list[str] = Field(default_factory=list, max_length=6)
    generated_by: Literal["rule", "llm"] = "rule"


class ScriptSchema(BaseModel):
    project: ProjectMetaSchema
    source_summary: SourceSummarySchema
    chapters: list[ChapterSchema] = Field(..., min_length=1)
    scenes: list[SceneSchema] = Field(..., min_length=1)
    metadata: ScriptMetadataSchema
    versions: list[ScriptVersionEntrySchema]
    character_relations: list[CharacterRelationSchema] = Field(default_factory=list)
    scene_plan: list[ScenePlanEntrySchema] = Field(default_factory=list)
    quality_report: QualityReportSchema

    @model_validator(mode="after")
    def validate_scene_counts(self) -> "ScriptSchema":
        if self.metadata.total_scenes != len(self.scenes):
            raise ValueError("metadata.total_scenes does not match scenes length")
        if self.project.source_chapter_count != len(self.chapters):
            raise ValueError("project.source_chapter_count does not match chapters length")
        if self.scene_plan and len(self.scene_plan) != len(self.scenes):
            raise ValueError("scene_plan length does not match scenes length")
        return self


class UpdateSceneRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    slugline: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: str | None = Field(default=None, min_length=1, max_length=300)
    beats: list[BeatSchema] | None = None
    adaptation_notes: AdaptationNotesSchema | None = None
    change_note: str | None = Field(default=None, max_length=200)


class RewriteSceneRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=200)
    preserve_core_event: bool = Field(default=True)
    create_new_version: bool = Field(default=True)


class ExportScriptRequest(BaseModel):
    version_id: str | None = None
    format: str = Field(default="yaml")
    include_report: bool = Field(default=True)


def validate_script_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return ScriptSchema.model_validate(payload).model_dump()
