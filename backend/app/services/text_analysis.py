from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


STOP_WORDS = {
    "他们",
    "我们",
    "自己",
    "没有",
    "一个",
    "不是",
    "已经",
    "可以",
    "因为",
    "然后",
    "时候",
    "这里",
    "那里",
    "只是",
    "如果",
    "这个",
    "那个",
    "一种",
    "什么",
    "怎么",
    "事情",
    "目光",
    "声音",
    "身体",
    "心里",
    "周围",
    "测试",
    "场景",
    "章节",
}

CHARACTER_HINT_WORDS = (
    "说",
    "问",
    "答",
    "喊",
    "叫",
    "看着",
    "看向",
    "盯着",
    "望着",
    "对",
    "朝",
    "跟",
)


def normalize_text(text: str) -> str:
    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def clean_character_candidate(value: str) -> str:
    candidate = value.strip()
    candidate = re.sub(r"(又|也|都|仍|还|正|却)$", "", candidate)
    return candidate


def matches_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    patterns = (
        r"^第[0-9一二三四五六七八九十百千]+章.*$",
        r"^第[0-9一二三四五六七八九十百千]+节.*$",
        r"^第[0-9一二三四五六七八九十百千]+回.*$",
        r"^序章.*$",
        r"^楔子.*$",
        r"^Chapter\s+\d+.*$",
        r"^#\s+.+$",
        r"^##\s+.+$",
        r"^\d+[.、]\s*.+$",
        r"^[（(]?[0-9一二三四五六七八九十]+[）)]\s*.+$",
    )
    return any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in patterns)


def split_chapters(text: str, min_chapter_count: int) -> list[dict[str, Any]]:
    normalized = normalize_text(text)
    lines = normalized.split("\n")
    chapters: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        content = "\n".join(line for line in current_lines if line.strip()).strip()
        if not content:
            current_title = None
            current_lines = []
            return
        chapters.append(
            {
                "title": current_title or f"章节 {len(chapters) + 1}",
                "text": content,
            }
        )
        current_title = None
        current_lines = []

    for line in lines:
        if matches_heading(line):
            if current_lines:
                flush()
            current_title = line.strip().lstrip("#").strip()
            continue
        current_lines.append(line)

    if current_lines:
        flush()

    if len(chapters) >= min_chapter_count:
        return chapters

    paragraphs = [segment.strip() for segment in re.split(r"\n{2,}", normalized) if segment.strip()]
    if len(paragraphs) < min_chapter_count:
        return []

    chunk_count = min(max(min_chapter_count, 3), len(paragraphs))
    chunk_size = math.ceil(len(paragraphs) / chunk_count)
    fallback_chapters: list[dict[str, Any]] = []
    for index in range(chunk_count):
        start = index * chunk_size
        end = start + chunk_size
        chunk = paragraphs[start:end]
        if not chunk:
            continue
        fallback_chapters.append(
            {
                "title": f"章节 {index + 1}",
                "text": "\n\n".join(chunk),
            }
        )
    return fallback_chapters if len(fallback_chapters) >= min_chapter_count else []


def summarize_text(text: str, limit: int = 90) -> str:
    cleaned = normalize_text(text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", cleaned) if item.strip()]
    if sentences:
        summary = "".join(sentences[:2]).strip()
    else:
        summary = cleaned.strip()
    return summary[:limit]


def extract_characters(text: str) -> list[str]:
    normalized = normalize_text(text)
    counter = Counter()
    patterns = [
        re.compile(rf"([\u4e00-\u9fff]{{2,4}})(?={'|'.join(CHARACTER_HINT_WORDS)})"),
        re.compile(r"(?:对|朝|看着|看向|望向|盯着|喊了|叫住|遇见|遇到|拦住)([\u4e00-\u9fff]{2,4})"),
        re.compile(r"([\u4e00-\u9fff]{2,4})(?=在旁|没有|仍旧|却|站在|出现|退让|沉默)"),
    ]

    for pattern in patterns:
        for match in pattern.findall(normalized):
            match = clean_character_candidate(match)
            if match in STOP_WORDS or any(char.isdigit() for char in match):
                continue
            if len(match) < 2:
                continue
            counter[match] += 2

    for match in re.findall(r"[\u4e00-\u9fff]{2,4}", normalized):
        match = clean_character_candidate(match)
        if match in STOP_WORDS:
            continue
        if any(char.isdigit() for char in match):
            continue
        if len(match) < 2:
            continue
        if match.endswith(("起来", "下去", "出来", "进去", "不是", "可以")):
            continue
        counter[match] += 1

    names = [name for name, count in counter.most_common(6) if count >= 2]
    return names or ["主角"]


def split_paragraphs(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    paragraphs = [segment.strip() for segment in re.split(r"\n{2,}", normalized) if segment.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]
    return paragraphs or [normalized]


def extract_keywords(text: str, limit: int = 5) -> list[str]:
    counter = Counter()
    for token in re.findall(r"[\u4e00-\u9fff]{2,4}", text):
        if token in STOP_WORDS:
            continue
        counter[token] += 1
    return [token for token, _ in counter.most_common(limit)]
