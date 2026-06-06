from app.schemas import validate_script_payload
from app.services.pipeline import (
    apply_rewrite_instruction,
    build_chapters,
    build_script,
    extract_characters,
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
