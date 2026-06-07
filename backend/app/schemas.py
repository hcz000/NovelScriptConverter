"""Pydantic 数据模型：定义所有请求/响应结构体及校验规则。"""
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ==================== 请求体模型 ====================

class CreateProjectRequest(BaseModel):
    """创建项目请求体"""
    title: str = Field(..., min_length=1, max_length=200)  # 项目名称
    language: str = Field(default="zh-CN")                   # 语言（默认中文）


class ParseProjectRequest(BaseModel):
    """章节解析请求体"""
    min_chapter_count: int = Field(default=3, ge=1, le=100)  # 最少章节数
    split_mode: str = Field(default="auto")                   # 分割模式（auto/heading/paragraph）


class GenerateScriptRequest(BaseModel):
    """剧本生成请求体"""
    target_format: str = Field(default="yaml")          # 输出格式
    scene_granularity: str = Field(default="standard")  # 场景粒度
    include_report: bool = Field(default=True)           # 是否附带质量报告


# ==================== 剧本核心结构 ====================

class BeatSchema(BaseModel):
    """节拍模型：剧本的最小单位，分为动作（action）和对白（dialogue）"""
    type: Literal["action", "dialogue"]               # 节拍类型
    content: str = Field(..., min_length=1, max_length=500)  # 内容
    character: str | None = Field(default=None, max_length=50) # 说话角色（对白时必填）

    @model_validator(mode="after")
    def validate_dialogue_character(self) -> "BeatSchema":
        """校验：对白类型的节拍必须指定角色"""
        if self.type == "dialogue" and not self.character:
            raise ValueError("dialogue beat requires character")
        return self


class SourceRefSchema(BaseModel):
    """源文引用：标注剧本内容对应的原著章节"""
    chapter_id: str = Field(..., min_length=1, max_length=20)
    excerpt_summary: str = Field(..., min_length=1, max_length=300)


class DramaticStructureSchema(BaseModel):
    """戏剧结构：描述场景的冲突四要素"""
    objective: str = Field(..., min_length=1, max_length=300)        # 角色目标
    obstacle: str = Field(..., min_length=1, max_length=300)         # 阻碍/对抗
    stakes: str = Field(..., min_length=1, max_length=300)           # 失败代价
    turning_point: str = Field(..., min_length=1, max_length=300)    # 转折点
    emotion_curve: list[str] = Field(..., min_length=3, max_length=6) # 情绪曲线


class AdaptationNotesSchema(BaseModel):
    """改编笔记：记录场景的节奏、风格和覆盖信息"""
    pacing: str = Field(..., min_length=1, max_length=50)           # 节奏（快/中/慢）
    style: str = Field(..., min_length=1, max_length=100)           # 风格
    coverage: str | None = Field(default=None, max_length=100)      # 原文覆盖
    rewrite_focus: str | None = Field(default=None, max_length=100) # 重写着重点


class SceneSchema(BaseModel):
    """场景模型：剧本的核心组成单元"""
    scene_id: str = Field(..., pattern=r"^SC\d{3}$")                # 场景编号（如 SC001）
    title: str = Field(..., min_length=1, max_length=120)           # 场景标题
    slugline: str = Field(..., min_length=1, max_length=120)        # 场景行（如 INT. 考场 - 白天）
    purpose: str = Field(..., min_length=1, max_length=300)         # 场景目的
    source_refs: list[SourceRefSchema] = Field(..., min_length=1)   # 源文引用
    characters: list[str] = Field(..., min_length=1, max_length=6)  # 出场角色列表
    dramatic_structure: DramaticStructureSchema                      # 戏剧结构
    beats: list[BeatSchema] = Field(..., min_length=1, max_length=12) # 节拍列表
    adaptation_notes: AdaptationNotesSchema                          # 改编笔记

    @model_validator(mode="after")
    def validate_dialogue_characters(self) -> "SceneSchema":
        """校验：对白节拍的角色必须存在于场景角色列表中"""
        character_set = set(self.characters)
        for beat in self.beats:
            if beat.type == "dialogue" and beat.character not in character_set:
                raise ValueError(f"dialogue character '{beat.character}' not in scene characters")
        return self


class ChapterSchema(BaseModel):
    """章节模型：小说拆分后的章节摘要"""
    chapter_id: str = Field(..., pattern=r"^CH\d{3}$")   # 章节编号（如 CH001）
    title: str = Field(..., min_length=1, max_length=120)  # 章节标题
    summary: str = Field(..., min_length=1, max_length=300) # 章节摘要


class CharacterProfileSchema(BaseModel):
    """角色画像模型"""
    name: str = Field(..., min_length=1, max_length=50)              # 角色名称
    role: str = Field(..., min_length=1, max_length=50)              # 角色定位（主角/关键配角等）
    traits: list[str] = Field(..., min_length=1, max_length=5)      # 角色特征


class SourceSummarySchema(BaseModel):
    """源文摘要模型"""
    premise: str = Field(..., min_length=1, max_length=300)           # 核心前提
    main_conflict: str = Field(..., min_length=1, max_length=300)     # 主要冲突
    main_characters: list[CharacterProfileSchema] = Field(..., min_length=1, max_length=5) # 主要角色
    conflict_keywords: list[str] = Field(default_factory=list, max_length=6)    # 冲突关键词
    chapter_highlights: list[str] = Field(default_factory=list, max_length=6)    # 章节亮点


class CharacterRelationSchema(BaseModel):
    """角色关系模型"""
    pair: str = Field(..., min_length=1, max_length=100)         # 角色对（如 林凡 / 苏青）
    relationship: str = Field(..., min_length=1, max_length=100) # 关系描述


class ScenePlanEntrySchema(BaseModel):
    """场景规划条目：章节到场景的映射记录"""
    scene_id: str = Field(..., pattern=r"^SC\d{3}$")
    chapter_id: str = Field(..., pattern=r"^CH\d{3}$")
    focus: str = Field(..., min_length=1, max_length=200)   # 场景焦点
    characters: list[str] = Field(..., min_length=1, max_length=6)


class ProjectMetaSchema(BaseModel):
    """项目元信息模型"""
    title: str = Field(..., min_length=1, max_length=200)
    source_type: Literal["novel"]                          # 源类型（固定为小说）
    source_chapter_count: int = Field(..., ge=1, le=200)   # 源文章节数
    language: str = Field(..., min_length=2, max_length=20)
    created_at: str = Field(..., min_length=8, max_length=40)
    version: str = Field(..., min_length=1, max_length=20)


class ScriptVersionEntrySchema(BaseModel):
    """脚本版本条目模型"""
    version: str = Field(..., min_length=1, max_length=20)
    created_at: str = Field(..., min_length=8, max_length=40)
    description: str = Field(..., min_length=1, max_length=200)


class ScriptMetadataSchema(BaseModel):
    """剧本元数据模型"""
    total_scenes: int = Field(..., ge=1)                  # 场景总数
    estimated_runtime_minutes: int = Field(..., ge=1)      # 预估时长（分钟）
    editable: bool                                          # 是否可编辑
    scene_density: float | None = Field(default=None, ge=0) # 场景密度
    chapter_to_scene_count: dict[str, int] = Field(default_factory=dict) # 章节→场景数映射
    conflict_keywords: list[str] = Field(default_factory=list, max_length=8)
    generation_source: Literal["rule", "llm", "unknown"] = "unknown"
    llm_status: dict[str, Any] | None = None
    llm_fallback_reason: str | None = Field(default=None, max_length=500)


# ==================== 质量审稿模型 ====================

class QualityMetricSchema(BaseModel):
    """质量维度评分模型"""
    name: str = Field(..., min_length=1, max_length=50)       # 维度名称
    score: int = Field(..., ge=0, le=100)                     # 评分（0-100）
    rationale: str = Field(..., min_length=1, max_length=200) # 评分理由


class SceneQualityNoteSchema(BaseModel):
    """场景质量笔记模型"""
    scene_id: str = Field(..., pattern=r"^SC\d{3}$")
    score: int = Field(..., ge=0, le=100)
    strengths: list[str] = Field(default_factory=list, max_length=4)   # 优点
    risks: list[str] = Field(default_factory=list, max_length=4)       # 风险
    suggestions: list[str] = Field(default_factory=list, max_length=4) # 建议


class QualityReportSchema(BaseModel):
    """质量审稿报告模型"""
    overall_score: int = Field(..., ge=0, le=100)                      # 综合评分
    headline: str = Field(..., min_length=1, max_length=120)           # 总评标题
    pitch_highlights: list[str] = Field(..., min_length=1, max_length=6) # 比赛展示亮点
    metrics: list[QualityMetricSchema] = Field(..., min_length=1, max_length=8) # 分项评分
    scene_notes: list[SceneQualityNoteSchema] = Field(default_factory=list)     # 场景级笔记
    revision_priorities: list[str] = Field(default_factory=list, max_length=6)  # 修订优先级
    generated_by: Literal["rule", "llm"] = "rule"                      # 生成方式


# ==================== 剧本根模型 ====================

class ScriptSchema(BaseModel):
    """剧本根模型：包含完整剧本的所有数据"""
    project: ProjectMetaSchema                              # 项目元信息
    source_summary: SourceSummarySchema                     # 源文摘要
    chapters: list[ChapterSchema] = Field(..., min_length=1) # 章节列表
    scenes: list[SceneSchema] = Field(..., min_length=1)    # 场景列表
    metadata: ScriptMetadataSchema                          # 剧本元数据
    versions: list[ScriptVersionEntrySchema]                # 版本记录
    character_relations: list[CharacterRelationSchema] = Field(default_factory=list) # 角色关系
    scene_plan: list[ScenePlanEntrySchema] = Field(default_factory=list)             # 场景规划
    quality_report: QualityReportSchema                     # 质量报告

    @model_validator(mode="after")
    def validate_scene_counts(self) -> "ScriptSchema":
        """校验：各计数字段需与实际列表长度一致"""
        if self.metadata.total_scenes != len(self.scenes):
            raise ValueError("metadata.total_scenes does not match scenes length")
        if self.project.source_chapter_count != len(self.chapters):
            raise ValueError("project.source_chapter_count does not match chapters length")
        if self.scene_plan and len(self.scene_plan) != len(self.scenes):
            raise ValueError("scene_plan length does not match scenes length")
        return self


# ==================== 编辑/操作请求模型 ====================

class UpdateSceneRequest(BaseModel):
    """场景更新请求体"""
    title: str | None = Field(default=None, min_length=1, max_length=120)
    slugline: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: str | None = Field(default=None, min_length=1, max_length=300)
    beats: list[BeatSchema] | None = None
    adaptation_notes: AdaptationNotesSchema | None = None
    change_note: str | None = Field(default=None, max_length=200)  # 变更说明


class RewriteSceneRequest(BaseModel):
    """场景重写请求体"""
    instruction: str = Field(..., min_length=1, max_length=200)   # 重写指令
    preserve_core_event: bool = Field(default=True)                # 是否保留核心事件
    create_new_version: bool = Field(default=True)                 # 是否创建新版本


class ExportScriptRequest(BaseModel):
    """剧本导出请求体"""
    version_id: str | None = None                  # 导出版本 ID
    format: str = Field(default="yaml")             # 导出格式（yaml/json）
    include_report: bool = Field(default=True)      # 是否包含质量报告


def validate_script_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """校验并清洗剧本数据，通过后返回规范化的 dict。"""
    return ScriptSchema.model_validate(payload).model_dump()
