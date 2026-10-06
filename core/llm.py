from __future__ import annotations

import asyncio
import json
import re
from functools import lru_cache
from typing import Literal, Optional, Type, TypeVar

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import get_settings
from core.tracing import TrajectoryRecorder

T = TypeVar("T", bound=BaseModel)

_sem: Optional[asyncio.Semaphore] = None


def _get_sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(get_settings().max_concurrency)
    return _sem


@lru_cache
def get_chat(role: Literal["gen", "fast"]) -> BaseChatModel:
    settings = get_settings()
    model = settings.gen_model if role == "gen" else settings.fast_model
    max_tokens = settings.gen_max_tokens if role == "gen" else 2048

    if role == "gen" and settings.gen_provider == "openai_compat":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=settings.temperature,
            max_tokens=max_tokens,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "EMPTY",
        )

    from langchain_groq import ChatGroq

    kwargs: dict = {
        "model": model,
        "temperature": settings.temperature,
        "max_tokens": max_tokens,
        "api_key": settings.groq_api_key or None,
        "max_retries": 2,
    }
    # reasoning_effort supported on gpt-oss models
    try:
        return ChatGroq(**kwargs, reasoning_effort=settings.reasoning_effort)
    except TypeError:
        return ChatGroq(**kwargs)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


class TransientLLMError(Exception):
    pass


@retry(
    retry=retry_if_exception_type((TransientLLMError, TimeoutError, httpx.HTTPError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _ainvoke_with_retry(chat: BaseChatModel, messages: list[BaseMessage]):
    try:
        return await chat.ainvoke(messages)
    except Exception as e:
        name = type(e).__name__
        msg = str(e).lower()
        if "rate" in msg or "429" in msg or "503" in msg or "502" in msg:
            raise TransientLLMError(str(e)) from e
        if "RateLimit" in name or "APIConnection" in name:
            raise TransientLLMError(str(e)) from e
        raise


async def invoke_structured(
    role: Literal["gen", "fast"],
    schema: Type[T],
    messages: list[BaseMessage],
    recorder: Optional[TrajectoryRecorder] = None,
) -> T:
    chat = get_chat(role)
    async with _get_sem():
        # Try json_schema structured output
        for method in ("json_schema", "json_mode"):
            try:
                structured = chat.with_structured_output(schema, method=method)
                result = await _ainvoke_with_retry(structured, messages)  # type: ignore[arg-type]
                if isinstance(result, schema):
                    if recorder:
                        recorder.record(messages, result.model_dump_json())
                    return result
                if isinstance(result, dict):
                    obj = schema.model_validate(result)
                    if recorder:
                        recorder.record(messages, obj.model_dump_json())
                    return obj
            except Exception:
                continue

        # Fallback: raw text + parse
        response = await _ainvoke_with_retry(chat, messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        raw = _extract_json(content)
        obj = schema.model_validate_json(raw)
        if recorder:
            recorder.record(messages, obj.model_dump_json())
        return obj


def check_models() -> dict[str, bool]:
    """Confirm configured model IDs are active on Groq. Never raises."""
    settings = get_settings()
    result = {settings.gen_model: False, settings.fast_model: False}
    if not settings.groq_api_key:
        return result
    try:
        resp = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            return result
        data = resp.json()
        ids = {m.get("id") for m in data.get("data", [])}
        return {mid: mid in ids for mid in result}
    except Exception:
        return {}
