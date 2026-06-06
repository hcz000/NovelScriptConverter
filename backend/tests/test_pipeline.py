from app.schemas import validate_script_payload
from app.services.llm_provider import llm_enabled
from app.services.pipeline import (
    apply_rewrite_instruction,
    attach_quality_report,
    build_chapters,
    build_script,
    extract_characters,
    generate_project_script,
    matches_heading,
    split_chapters,
)


def test_matches_heading_supports_common_patterns() -> None:
    assert matches_heading("第十二章 夜访")
    assert matches_heading("Chapter 3 Reunion")
    assert matches_heading("# 第一章")
    assert matches_heading("12. 转折")
    assert not matches_heading("正文第一段")


def test_split_chapters_by_headings() -> None:
    text = (
        "第1章 开始\n林凡走进考场。\n\n"
        "第2章 转折\n苏青出现并叫住林凡。\n\n"
        "第3章 结束\n赵岩看着林凡，没有说话。"
    )
    chapters = split_chapters(text, 3)
    assert len(chapters) == 3
    assert chapters[0]["title"] == "第1章 开始"
    assert "林凡走进考场" in chapters[0]["text"]


def test_extract_characters_prefers_name_candidates() -> None:
    text = "林凡看着苏青，苏青却没有回头。林凡又喊了赵岩，赵岩仍旧沉默。"
    characters = extract_characters(text)
    assert "林凡" in characters


def test_build_script_creates_multiple_scenes_and_validates() -> None:
    raw = [
        {
            "title": "第一章 入门",
            "text": (
                "林凡走进考场，四周都在议论他。\n\n"
                "测试官冷冷看着他，气氛越来越紧。\n\n"
                "“你确定还要继续？”测试官问。\n\n"
                "林凡抬头盯着对方，没有后退。\n\n"
                "忽然，场内的石碑亮了。\n\n"
                "众人一片哗然。"
            ),
        }
    ]
    chapters = build_chapters(raw)
    script = build_script({"title": "测试项目", "language": "zh-CN"}, chapters)
    validated = validate_script_payload(script)

    assert len(validated["scenes"]) >= 2
    assert validated["metadata"]["total_scenes"] == len(validated["scenes"])
    assert validated["scenes"][0]["beats"]
    assert validated["scene_plan"]
    assert validated["metadata"]["chapter_to_scene_count"]
    assert "conflict_keywords" in validated["source_summary"]
    assert validated["quality_report"]["overall_score"] > 0
    assert validated["quality_report"]["metrics"]
    assert validated["quality_report"]["scene_notes"]


def test_build_script_includes_character_relations() -> None:
    raw = [
        {
            "title": "第一章 对峙",
            "text": "林凡看着苏青。苏青没有退让。赵岩也站在一旁看着两人。",
        },
        {
            "title": "第二章 余波",
            "text": "林凡再次遇见苏青，赵岩仍旧在场，三人之间的气氛更紧。",
        },
        {
            "title": "第三章 试探",
            "text": "林凡主动试探赵岩，苏青则继续观察局面。",
        },
    ]
    chapters = build_chapters(raw)
    script = build_script({"title": "测试项目", "language": "zh-CN"}, chapters)
    validated = validate_script_payload(script)

    assert validated["character_relations"]


def test_build_script_adds_stronger_scene_dramatics() -> None:
    raw = [
        {
            "title": "第一章 考场对峙",
            "text": (
                "林凡走进考场，苏青在旁观察。\n\n"
                "测试官宣布失败就会失去资格。\n\n"
                "林凡看着苏青，苏青没有退让。\n\n"
                "忽然，场内的石碑亮了。"
            ),
        }
    ]
    chapters = build_chapters(raw)
    script = build_script({"title": "测试项目", "language": "zh-CN"}, chapters)
    validated = validate_script_payload(script)
    first_scene = validated["scenes"][0]

    assert first_scene["slugline"].startswith("INT. 考场")
    assert "资格" in first_scene["dramatic_structure"]["stakes"]
    assert "钩子" in first_scene["adaptation_notes"]["style"]
    assert any(
        beat["type"] == "dialogue"
        for scene in validated["scenes"]
        for beat in scene["beats"]
    )
    assert any("关系" in relation["relationship"] for relation in validated["character_relations"])
    assert "可拍冲突" in validated["source_summary"]["main_conflict"]


def test_attach_quality_report_uses_valid_llm_review(monkeypatch) -> None:
    raw = [
        {
            "title": "第一章 入门",
            "text": (
                "林凡走进考场，苏青在旁观察。\n\n"
                "测试官宣布失败就会失去资格。\n\n"
                "“你确定还要继续？”测试官问。\n\n"
                "林凡没有后退，石碑忽然亮起。"
            ),
        }
    ]
    chapters = build_chapters(raw)
    script = build_script({"title": "测试项目", "language": "zh-CN"}, chapters)
    scene_id = script["scenes"][0]["scene_id"]

    def fake_request_json_object(_system_prompt, _user_prompt):
        return {
            "overall_score": 91,
            "headline": "冲突入口清楚，已经具备比赛展示的场景化卖点。",
            "pitch_highlights": ["主角选择、失败代价和尾部异象形成清晰钩子。"],
            "metrics": [
                {
                    "name": "比赛展示亮点",
                    "score": 94,
                    "rationale": "场景能快速说明系统从小说段落提炼冲突、转折和可拍动作的能力。",
                }
            ],
            "scene_notes": [
                {
                    "scene_id": scene_id,
                    "score": 92,
                    "strengths": ["测试官施压和石碑亮起构成明确转折。"],
                    "risks": ["苏青的观察还可以承载更多关系信息。"],
                    "suggestions": ["补一句苏青的反应，让人物关系更外显。"],
                },
                {
                    "scene_id": "SC999",
                    "score": 100,
                    "strengths": ["无效场景不应进入结果。"],
                    "risks": [],
                    "suggestions": [],
                },
            ],
            "revision_priorities": ["优先让旁观角色参与压力升级。"],
            "generated_by": "llm",
        }

    monkeypatch.setattr("app.services.quality_report.request_json_object", fake_request_json_object)

    reviewed = validate_script_payload(attach_quality_report(script))

    assert reviewed["quality_report"]["generated_by"] == "llm"
    assert reviewed["quality_report"]["overall_score"] == 91
    assert reviewed["quality_report"]["metrics"][0]["name"] == "比赛展示亮点"
    assert {note["scene_id"] for note in reviewed["quality_report"]["scene_notes"]} == {
        scene["scene_id"] for scene in reviewed["scenes"]
    }


def test_attach_quality_report_falls_back_when_llm_review_fails(monkeypatch) -> None:
    raw = [
        {
            "title": "第一章 入门",
            "text": "林凡走进考场，苏青在旁观察。测试官冷冷看着他，气氛越来越紧。",
        }
    ]
    chapters = build_chapters(raw)
    script = build_script({"title": "测试项目", "language": "zh-CN"}, chapters)

    def broken_request_json_object(_system_prompt, _user_prompt):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.services.quality_report.request_json_object", broken_request_json_object)

    reviewed = validate_script_payload(attach_quality_report(script))

    assert reviewed["quality_report"]["generated_by"] == "rule"
    assert reviewed["quality_report"]["overall_score"] > 0


def test_apply_rewrite_instruction_updates_scene_notes() -> None:
    raw = [
        {
            "title": "第一章 入门",
            "text": (
                "林凡走进考场，四周都在议论他。\n\n"
                "测试官冷冷看着他，气氛越来越紧。\n\n"
                "“你确定还要继续？”测试官问。"
            ),
        }
    ]
    chapters = build_chapters(raw)
    script = build_script({"title": "测试项目", "language": "zh-CN"}, chapters)
    scene = script["scenes"][0]
    apply_rewrite_instruction(scene, "增强冲突张力，压缩节奏，增加反转爆点")

    assert scene["adaptation_notes"]["rewrite_focus"]
    assert any(beat["type"] == "dialogue" for beat in scene["beats"])


def test_llm_provider_disabled_by_default() -> None:
    assert llm_enabled() is False


def test_generate_project_script_uses_valid_llm_draft(temp_store, monkeypatch) -> None:
    raw = [
        {
            "title": "第一章 入门",
            "text": "林凡走进考场，苏青在旁观察。测试官冷冷看着他，气氛越来越紧。",
        }
    ]
    chapters = build_chapters(raw)
    project = {
        "project_id": "proj_llm",
        "title": "测试项目",
        "source_type": "novel",
        "language": "zh-CN",
        "status": "READY",
        "source_chapter_count": len(chapters),
        "current_version_id": None,
        "created_at": "2026-06-06T00:00:00+08:00",
        "updated_at": "2026-06-06T00:00:00+08:00",
        "source_file_name": None,
        "source_file_path": None,
        "chapters": chapters,
        "versions": [],
        "scripts": {},
    }
    task = {
        "task_id": "task_llm",
        "task_type": "GENERATE_SCRIPT",
        "status": "PENDING",
        "progress": 0,
        "project_id": project["project_id"],
        "result": None,
        "error_message": None,
        "created_at": "2026-06-06T00:00:00+08:00",
        "updated_at": "2026-06-06T00:00:00+08:00",
    }
    temp_store.upsert_project(project)
    temp_store.upsert_task(task)

    def fake_llm_generate(project_payload, chapter_payload, draft):
        generated = build_script(project_payload, chapter_payload)
        generated["source_summary"]["premise"] = "LLM 生成的核心前提"
        generated["metadata"]["conflict_keywords"] = ["LLM冲突"]
        return generated

    monkeypatch.setattr("app.services.tasks.llm_generate_script", fake_llm_generate)

    generate_project_script(temp_store, project["project_id"], task["task_id"], include_report=True)

    updated_task = temp_store.get_task(task["task_id"])
    updated_project = temp_store.get_project(project["project_id"])
    assert updated_task["status"] == "SUCCEEDED"
    version_id = updated_task["result"]["current_version_id"]
    assert updated_project["scripts"][version_id]["source_summary"]["premise"] == "LLM 生成的核心前提"
    assert updated_project["scripts"][version_id]["metadata"]["conflict_keywords"] == ["LLM冲突"]


def test_generate_project_script_falls_back_when_llm_draft_is_missing(temp_store, monkeypatch) -> None:
    raw = [
        {
            "title": "第一章 入门",
            "text": "林凡走进考场，苏青在旁观察。测试官冷冷看着他，气氛越来越紧。",
        }
    ]
    chapters = build_chapters(raw)
    project = {
        "project_id": "proj_rule",
        "title": "测试项目",
        "source_type": "novel",
        "language": "zh-CN",
        "status": "READY",
        "source_chapter_count": len(chapters),
        "current_version_id": None,
        "created_at": "2026-06-06T00:00:00+08:00",
        "updated_at": "2026-06-06T00:00:00+08:00",
        "source_file_name": None,
        "source_file_path": None,
        "chapters": chapters,
        "versions": [],
        "scripts": {},
    }
    task = {
        "task_id": "task_rule",
        "task_type": "GENERATE_SCRIPT",
        "status": "PENDING",
        "progress": 0,
        "project_id": project["project_id"],
        "result": None,
        "error_message": None,
        "created_at": "2026-06-06T00:00:00+08:00",
        "updated_at": "2026-06-06T00:00:00+08:00",
    }
    temp_store.upsert_project(project)
    temp_store.upsert_task(task)
    monkeypatch.setattr("app.services.tasks.llm_generate_script", lambda *_args: None)

    generate_project_script(temp_store, project["project_id"], task["task_id"], include_report=True)

    updated_task = temp_store.get_task(task["task_id"])
    updated_project = temp_store.get_project(project["project_id"])
    version_id = updated_task["result"]["current_version_id"]
    script = updated_project["scripts"][version_id]
    assert updated_task["status"] == "SUCCEEDED"
    assert script["source_summary"]["premise"] != "LLM 生成的核心前提"
    assert script["metadata"]["total_scenes"] == len(script["scenes"])
