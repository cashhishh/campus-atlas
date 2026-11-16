"""Thin Groq chat-completions client (OpenAI-compatible HTTP API).

Used only for (1) context-only answers and (2) change summaries. Every caller
has a deterministic fallback, so the app works without a key.

Groq retires models regularly, so if the configured GROQ_MODEL no longer
exists the client tries GROQ_FALLBACK_MODELS in order and remembers the first
one that works.
"""
import os
import re
import time

import httpx

from ..config import groq_api_key, groq_model

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_FALLBACKS = "qwen/qwen3.8-27b,openai/gpt-oss-120b,openai/gpt-oss-20b"
_working_model: str | None = None


class GroqUnavailable(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(groq_api_key())


def candidate_models() -> list[str]:
    fallbacks = os.getenv("GROQ_FALLBACK_MODELS", DEFAULT_FALLBACKS).split(",")
    ordered = [_working_model, groq_model(), *fallbacks]
    seen, out = set(), []
    for m in ordered:
        m = (m or "").strip()
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def active_model() -> str | None:
    return _working_model


def _model_options(model: str) -> dict:
    if model.startswith("qwen/"):
        return {"reasoning_format": "hidden"}
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    return {}


def _clean(content: str) -> str:
    content = re.sub(r"<think>[\s\S]*?</think>", "", content or "")
    content = re.sub(r"【\s*(S\d+)[^】]*】", r"[\1]", content)  # gpt-oss citation style -> [S1]
    return content.strip()


def _post(key, model, system, user, max_tokens, temperature, timeout):
    return httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": temperature, "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
              **_model_options(model)},
        timeout=timeout,
    )


def chat(system: str, user: str, max_tokens: int = 500, temperature: float = 0.1, timeout: float = 25.0) -> str:
    global _working_model
    key = groq_api_key()
    if not key:
        raise GroqUnavailable("GROQ_API_KEY is not configured")
    last_error = "no model available"
    for model in candidate_models():
        for attempt in range(2):  # one retry on rate limiting (HTTP 429)
            try:
                response = _post(key, model, system, user, max_tokens, temperature, timeout)
            except httpx.HTTPError as exc:
                raise GroqUnavailable(f"Groq request failed: {type(exc).__name__}") from exc
            if response.status_code != 429 or attempt == 1:
                break
            try:
                wait = min(3.0, float(response.headers.get("retry-after", 1.5)))
            except ValueError:
                wait = 1.5
            time.sleep(wait)
        if response.status_code in (400, 404) and "model" in response.text.lower() and (
                "not exist" in response.text.lower() or "decommission" in response.text.lower() or "model_not_found" in response.text):
            last_error = f"model {model} unavailable"
            continue
        if response.status_code != 200:
            raise GroqUnavailable(f"Groq returned HTTP {response.status_code}")
        content = _clean((response.json().get("choices") or [{}])[0].get("message", {}).get("content") or "")
        if not content:
            raise GroqUnavailable("Groq returned an empty answer")
        _working_model = model
        return content
    raise GroqUnavailable(last_error)
