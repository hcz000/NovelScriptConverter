"""LLM（大语言模型）调用封装：支持多种模型供应商，统一 JSON 结构化响应解析。

支持的供应商：
- openai：  OpenAI API（api.openai.com）
- bailian：  阿里云百炼 DashScope（兼容 OpenAI API）
- 自定义：  通过 LLM_BASE_URL 指向任意 OpenAI 兼容服务
"""
from __future__ import annotations

import json
from typing import Any

from app.core.config import LLM_PROVIDER, PROVIDER_CONFIG

# 尝试导入 OpenAI SDK，如果未安装则设为 None（降级到规则引擎模式）
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

# ---------- 供应商配置缓存 ----------
_CACHED_PROVIDER: dict[str, Any] | None = None
_LAST_ERROR: str | None = None


def set_last_llm_error(message: str | None) -> None:
    global _LAST_ERROR
    _LAST_ERROR = message


def last_llm_error() -> str | None:
    return _LAST_ERROR


def _get_provider_config() -> dict[str, Any] | None:
    """获取当前供应商的配置，并在首次调用时校验。"""
    global _CACHED_PROVIDER

    if _CACHED_PROVIDER is not None:
        return _CACHED_PROVIDER

    provider = LLM_PROVIDER.lower()
    if provider == "rule":
        set_last_llm_error("LLM_PROVIDER is rule")
        _CACHED_PROVIDER = None
        return None

    config = PROVIDER_CONFIG.get(provider)
    if config is None:
        # 不认识的 provider 名称，降级规则引擎
        set_last_llm_error(f"unsupported LLM_PROVIDER: {provider}")
        _CACHED_PROVIDER = None
        return None

    if not config["api_key"]:
        set_last_llm_error(f"missing API key for provider: {provider}")
        _CACHED_PROVIDER = None
        return None

    set_last_llm_error(None)
    _CACHED_PROVIDER = config
    return config


def llm_enabled() -> bool:
    """判断 LLM 是否可用：供应商已配置、API Key 已设置、SDK 已安装。"""
    if OpenAI is None:
        set_last_llm_error("openai SDK is not installed")
        return False
    return _get_provider_config() is not None


def llm_status() -> dict[str, Any]:
    provider = LLM_PROVIDER.lower()
    config = PROVIDER_CONFIG.get(provider)
    enabled = llm_enabled()
    return {
        "enabled": enabled,
        "provider": provider,
        "model": config.get("model") if config else None,
        "base_url": config.get("base_url") if config else None,
        "reason": None if enabled else last_llm_error(),
    }


def _extract_response_text(response: Any) -> str:
    """从 OpenAI SDK 响应对象中提取纯文本内容。
    兼容多种响应格式：
    1. 直接读取 output_text 属性（Responses API）
    2. 遍历 output.content.text 列表（备用格式）
    3. choices[0].message.content（Chat Completions API 兼容）
    """
    # 方式1：Responses API
    output = getattr(response, "output_text", None)
    if output:
        return output

    # 方式2：遍历 output 列表
    texts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                texts.append(text)
    if texts:
        return "\n".join(texts).strip()

    # 方式3：Chat Completions API 兼容（大部分 OpenAI 兼容服务使用此格式）
    choices = getattr(response, "choices", None)
    if choices and len(choices) > 0:
        message = getattr(choices[0], "message", None)
        if message:
            content = getattr(message, "content", None)
            if content:
                return content.strip()

    return ""


def _extract_json(text: str) -> str:
    """从文本中提取 JSON 内容，自动清理 Markdown 代码块标记。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # 去掉可能的 json 标记行
        if "\n" in text:
            text = text.split("\n", 1)[1]
    return text.strip()


def request_json_object(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    """调用 LLM API，请求返回 JSON 对象。

    根据 LLM_PROVIDER 自动选择供应商：
    - openai → api.openai.com
    - bailian → dashscope.aliyuncs.com（兼容 OpenAI API）
    - LLM_BASE_URL 可覆盖任意供应商地址

    Args:
        system_prompt: 系统级提示词（定义角色和规则）
        user_prompt: 用户提示词（具体任务和输入数据）

    Returns:
        解析后的 JSON dict，如果 LLM 未启用或调用失败则返回 None。
    """
    config = _get_provider_config()
    if config is None:
        return None

    # 使用统一 client，通过 base_url 适配不同供应商
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
    model = config["model"]

    try:
        # 优先使用 Chat Completions API（兼容性最广，百炼等均支持）
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except Exception as error:
        set_last_llm_error(f"chat.completions json_object failed: {error}")
        # Chat Completions 不支持 json_object 时，降级为普通请求 + 自行解析 JSON
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
        except Exception as fallback_error:
            set_last_llm_error(f"chat.completions fallback failed: {fallback_error}")
            return None

    text = _extract_response_text(response)
    if not text:
        set_last_llm_error("empty LLM response")
        return None

    try:
        result = json.loads(_extract_json(text))
        set_last_llm_error(None)
        return result
    except json.JSONDecodeError as error:
        set_last_llm_error(f"invalid JSON response: {error}")
        return None
