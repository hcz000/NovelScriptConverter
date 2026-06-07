"""文本分析引擎：实现小说文本的预处理、章节分割、人物提取、关键词提取等功能。"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

# ---------- 停用词表：这些常见词不会被识别为人物名或关键词 ----------
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

# ---------- 人物提示词：紧跟在人物名后的动词/副词，用于定位人物名 ----------
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

# ---------- 叙事片段排除表：正则易误匹配的通用中文叙事片段 ----------
# 仅包含跨小说通用的非人物词，不包含任何特定小说的专有名词
NARRATIVE_FRAGMENTS = {
    # 通用叙事连接词（任何小说都会出现）
    "一个", "一种", "不是", "可以", "因为", "所以",
    "然后", "时候", "这里", "那里", "这个", "那个",
    "他们", "我们", "自己", "已经", "什么", "怎么",
    "只是", "如果", "事情", "目光", "声音", "身体",
    "心里", "周围",
    # 高频副词/连词 — 正则极易误匹配
    "她也", "他也", "也可", "也会", "我也",
    "多少", "恐怕",
    "经过", "却未", "并未", "并非", "以及",
    "然而", "而且", "但是", "虽然",
    "便是", "也不", "就是", "还是", "却是",
    "不知", "只见", "忽然", "突然",
    "不管", "当然", "总能", "总有",
    "那位", "各位",
}


def normalize_text(text: str) -> str:
    """文本规范化：移除 BOM、统一换行符、压缩多余空行。"""
    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def clean_character_candidate(value: str) -> str:
    """清理人物名候选：去除尾部常见副词和头部"的"等修饰结构。"""
    candidate = value.strip()
    candidate = re.sub(r"(没有|仍旧|继续|已经|正在|突然|忽然|出现|退让|沉默)$", "", candidate)
    candidate = re.sub(r"(也|都|仍|还|正|却|竟|便|则)?(站|坐|躺|走|跑|看)$", "", candidate)
    candidate = re.sub(r"(又|也|都|仍|还|正|却|竟|便|则)$", "", candidate)
    candidate = re.sub(r"的[\u4e00-\u9fff]{1,4}$", "", candidate)
    candidate = re.sub(r"^的", "", candidate)
    return candidate


def matches_heading(line: str) -> bool:
    """判断一行文本是否为章节标题。
    支持多种中文和英文标题格式：
    - 第X章/节/回、序章、楔子
    - Chapter N
    - Markdown # / ## 标题
    - 数字序号标题
    """
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
    """将全文字符串按章节标题分割为章节列表。
    
    优先使用标题分割；如果标题识别的章节数不足，则按段落数均分作为降级策略。
    
    Args:
        text: 全文文本
        min_chapter_count: 最少需要的章节数
    
    Returns:
        章节列表 [{title, text}, ...]，如果无法分割则返回空列表。
    """
    normalized = normalize_text(text)
    lines = normalized.split("\n")
    chapters: list[dict[str, Any]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        """将当前收集的行打包为一个章节记录。"""
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

    # 第一轮：按标题分割
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

    # 降级策略：按段落数均分
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
    """提取文本的前两句作为摘要，按长度截断。"""
    cleaned = normalize_text(text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", cleaned) if item.strip()]
    if sentences:
        summary = "".join(sentences[:2]).strip()
    else:
        summary = cleaned.strip()
    return summary[:limit]


def extract_characters(text: str) -> list[str]:
    """从文本中提取人物名列表。

    使用多种正则模式匹配：
    1. 人物名紧跟在提示动词前（说、问、看着等）
    2. 人物名出现在动作描述前（在旁、没有、站在等）
    3. 通用的中文二到四字词频统计，排除停用词和动词短语

    返回最多6个、出现次数>=2的人物名，或默认返回 ["主角"]。
    """
    normalized = normalize_text(text)
    total_char_count = max(1, len(normalized))
    counter = Counter()
    evidence_counter = Counter()
    patterns = [
        # 模式1：人物名 + 提示词（如"林凡说"、"苏青问"）
        re.compile(rf"([\u4e00-\u9fff]{{2,4}})(?={'|'.join(CHARACTER_HINT_WORDS)})"),
        # 模式2：动词 + 人物名（如"看着苏青"、"喊了赵岩"）
        re.compile(r"(?:对|朝|看着|看向|望向|盯着|喊了|叫住|遇见|遇到|拦住)([\u4e00-\u9fff]{2,4})"),
        # 模式3：人物名 + 状态（如"林凡在旁"、"苏青没有"）
        re.compile(r"([\u4e00-\u9fff]{2,4})(?=在旁|没有|仍旧|却|站在|出现|退让|沉默)"),
    ]

    for pattern in patterns:
        for match in pattern.findall(normalized):
            match = clean_character_candidate(match)
            if not _is_valid_character_candidate(match):
                continue
            counter[match] += 2  # 模式匹配的权重更高
            evidence_counter[match] += 1

    # 通用中文词频统计（排除停用词和动词后缀）
    for match in re.findall(r"[\u4e00-\u9fff]{2,4}", normalized):
        match = clean_character_candidate(match)
        if not _is_valid_character_candidate(match):
            continue
        if match.endswith(("起来", "下去", "出来", "进去", "不是", "可以")):
            continue
        counter[match] += 1

    # 频次异常过滤：极端高频词大概率不是角色名
    for name in list(counter.keys()):
        freq_ratio = counter[name] / total_char_count
        if counter[name] >= 6 and freq_ratio > 0.08 and len(name) <= 3:
            counter[name] = max(1, counter[name] // 2)

    names = [
        name
        for name, count in counter.most_common(6)
        if count >= 2 and (evidence_counter[name] > 0 or count >= 3)
    ]
    return names or ["主角"]


def _is_valid_character_candidate(candidate: str) -> bool:
    """校验候选人物名是否合法：排除停用词、数字、叙事片段、过短词等。"""
    if not candidate or len(candidate) < 2:
        return False
    if candidate in STOP_WORDS or candidate in NARRATIVE_FRAGMENTS:
        return False
    if re.match(r"^[一二三四五六七八九十百千万两几数多]+(人|位|名|个)$", candidate):
        return False
    if candidate in {"众人", "众位", "众生", "大家", "旁人", "路人", "人群"}:
        return False
    if re.search(r"[与及同跟和]", candidate):
        return False
    if any(char.isdigit() for char in candidate):
        return False
    if re.search(r"(等级|级别|品阶|称号|状态|属性)$", candidate):
        return False
    # 排除带动词前缀的正则误匹配（如"对萧薰儿"）
    if re.match(r"^(对|朝|看着|看向|望向|盯着|喊了|叫住|遇见|遇到|拦住)", candidate):
        return False
    # 排除带动词后缀的正则误匹配（如"萧炎说道"、"薰儿说"）
    if re.search(r"(说道|问道|喊道|叫道|地说|地道)$", candidate):
        return False
    # 排除叙事定位词结尾的误匹配（如"媚在一旁"）
    if re.search(r"(在旁|一旁|身后|面前|之中|之间)$", candidate):
        return False
    # 排除通用中文常用词结尾 — 任何小说中都可能被正则误判
    if re.search(r"(面上|脸上|头上|手中|眼前|脚下|身上|背后)$", candidate):
        return False
    # 排除形容词/状态后缀 — 通用名词不是角色名
    if re.search(r"(表情|神色|模样|样子|气息|气势|笑容)$", candidate):
        return False
    # 排除动词+方位后缀 — 任何小说中都不是角色名
    if re.search(r"(站着|坐着|躺着|走着|跑着|站在|坐在|躺在|走向|走到|来到|走上|走下|走进|走出|跑进|跑出|冲进|冲出)$", candidate):
        return False
    # 长候选(>=4字)以单字动词结尾 — 常见正则过度捕获
    if len(candidate) >= 4 and re.search(r"[上下来去出入进退回]$", candidate):
        return False
    # 检查是否包含叙事片段（如"经与"在"经与薰儿"中）
    for fragment in NARRATIVE_FRAGMENTS:
        if len(fragment) >= 2 and fragment in candidate:
            return False
    return True


def split_paragraphs(text: str) -> list[str]:
    """将文本按空行分割为段落列表。
    如果只有一个段落，则按单行分割；如果仍只有一个，则返回原文本作为单个元素。
    """
    normalized = normalize_text(text)
    if not normalized:
        return []
    paragraphs = [segment.strip() for segment in re.split(r"\n{2,}", normalized) if segment.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [line.strip() for line in normalized.split("\n") if line.strip()]
    return paragraphs or [normalized]


def extract_keywords(text: str, limit: int = 5) -> list[str]:
    """从中文字符中提取高频关键词（排除停用词），按词频排序返回。"""
    counter = Counter()
    for token in re.findall(r"[\u4e00-\u9fff]{2,4}", text):
        if token in STOP_WORDS:
            continue
        counter[token] += 1
    return [token for token, _ in counter.most_common(limit)]
