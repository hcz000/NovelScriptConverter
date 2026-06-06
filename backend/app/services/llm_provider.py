from __future__ import annotations

import json
from typing import Any

from app.core.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


def llm_enabled() -> bool:
    return LLM_PROVIDER.lower() == "openai" and bool(OPENAI_API_KEY) and OpenAI is not None


def _extract_response_text(response: Any) -> str:
    output = getattr(response, "output_text", None)
    if output:
        return output

    texts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def request_json_object(system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
    if not llm_enabled():
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    text = _extract_response_text(response).strip()
    if not text:
        return None

    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    text = text.strip()
    return json.loads(text)
