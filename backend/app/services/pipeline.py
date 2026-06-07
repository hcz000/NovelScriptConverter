"""兼容性门面（Facade）：将所有服务模块的函数重新导出，供路由和测试统一引用。
实际实现分散在各个小模块中，pipeline.py 仅做聚合导出。"""
from __future__ import annotations

from app.core import config
from app.services.common import (
    PROJECT_GENERATING,
    PROJECT_ARCHIVED,
    PROJECT_INIT,
    PROJECT_PARSING,
    PROJECT_READY,
    PROJECT_SCRIPT_READY,
    PROJECT_SOURCE_UPLOADED,
    TASK_FAILED,
    TASK_PENDING,
    TASK_RUNNING,
    TASK_SUCCEEDED,
    build_request_id,
    create_project_record,
    create_task_record,
    date_str,
    ensure_current_script,
    ensure_project,
    ensure_task,
    make_error_response,
    make_id,
    make_success_response,
    now_iso,
    read_source_text,
    save_upload_file,
    summarize_project,
    touch_project,
    update_task,
)
from app.services.scene_rewriter import (
    apply_rewrite_instruction,
    build_rewrite_profile,
    llm_rewrite_scene,
    rewrite_action_content,
    rewrite_dialogue_content,
)
from app.services.quality_report import (
    attach_quality_report,
    build_llm_review_payload,
    build_quality_report,
    llm_review_quality_report,
    normalize_llm_quality_report,
)
from app.services.script_builder import (
    build_beats_from_paragraphs,
    build_chapter_to_scene_count,
    build_chapters,
    build_character_profiles,
    build_character_relations,
    build_llm_generation_payload,
    build_scene_dramatic_structure,
    build_scene_from_group,
    build_scene_plan_entry,
    build_script,
    derive_scene_groups,
    extract_dialogue_fragments,
    find_scene_characters,
    infer_scene_pacing,
    infer_scene_style,
    infer_time_of_day,
    llm_extract_characters,
    llm_generate_script,
    summarize_paragraph_group,
    validate_character_names,
)
from app.services.script_ops import (
    clone_script,
    compare_scripts,
    dump_script_content,
    find_scene,
    next_version_name,
    validate_script_or_raise,
)
from app.services.tasks import (
    export_script_task,
    generate_project_script,
    parse_project_source,
    patch_scene,
    rewrite_scene_task,
)
from app.services.text_analysis import (
    CHARACTER_HINT_WORDS,
    STOP_WORDS,
    clean_character_candidate,
    extract_characters,
    extract_keywords,
    matches_heading,
    normalize_text,
    split_chapters,
    split_paragraphs,
    summarize_text,
)

UPLOADS_DIR = config.UPLOADS_DIR
EXPORTS_DIR = config.EXPORTS_DIR
