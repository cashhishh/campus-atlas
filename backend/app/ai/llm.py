"""Provider-independent LLM entry point.

Order is set by LLM_PROVIDER (default "gemini"): the primary provider first,
the other one as fallback. If every configured provider fails, LLMUnavailable
is raised and callers use their deterministic (grounded demo) path.
"""
import os

from . import gemini_client, groq_client

PROVIDERS = {"gemini": gemini_client, "groq": groq_client}
FAILURES = (gemini_client.GeminiUnavailable, groq_client.GroqUnavailable)


class LLMUnavailable(RuntimeError):
    pass


def provider_order() -> list[str]:
    primary = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    primary = primary if primary in PROVIDERS else "gemini"
    return [primary] + [p for p in PROVIDERS if p != primary]


def is_configured() -> bool:
    return any(PROVIDERS[p].is_configured() for p in provider_order())


def configured_providers() -> list[str]:
    return [p for p in provider_order() if PROVIDERS[p].is_configured()]


def active_model(provider: str) -> str | None:
    return PROVIDERS[provider].active_model() if provider in PROVIDERS else None


def generate(system: str, user: str, max_tokens: int = 500, temperature: float = 0.1, timeout: float = 25.0) -> tuple[str, str, list[str]]:
    """Return (text, provider, errors). Raises LLMUnavailable when no provider succeeds."""
    errors = []
    for name in provider_order():
        client = PROVIDERS[name]
        if not client.is_configured():
            continue
        try:
            return client.chat(system, user, max_tokens=max_tokens, temperature=temperature, timeout=timeout), name, errors
        except FAILURES as exc:
            errors.append(f"{name}: {exc}")
    raise LLMUnavailable("; ".join(errors) or "no AI provider configured")
