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


def provider_order(prefer: str | None = None) -> list[str]:
    primary = (prefer or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    primary = primary if primary in PROVIDERS else "gemini"
    return [primary] + [p for p in PROVIDERS if p != primary]


def is_configured() -> bool:
    return any(PROVIDERS[p].is_configured() for p in provider_order())


def configured_providers() -> list[str]:
    return [p for p in provider_order() if PROVIDERS[p].is_configured()]


def active_model(provider: str) -> str | None:
    return PROVIDERS[provider].active_model() if provider in PROVIDERS else None


def task_provider(task: str) -> str | None:
    """Which provider a task should try first.

    Gemini's free tier is small and is best spent where only Gemini can help (Google Search grounding),
    so routine text work (understanding the question, writing the cited answer, change summaries)
    goes to Groq first by default. Override with e.g. ANSWER_PROVIDER=gemini."""
    return os.getenv(f"{task.upper()}_PROVIDER", "groq").strip().lower() or None


def generate(system: str, user: str, max_tokens: int = 500, temperature: float = 0.1, timeout: float = 25.0,
             prefer: str | None = None) -> tuple[str, str, list[str]]:
    """Return (text, provider, errors). Raises LLMUnavailable when no provider succeeds."""
    errors = []
    for name in provider_order(prefer):
        client = PROVIDERS[name]
        if not client.is_configured():
            continue
        try:
            return client.chat(system, user, max_tokens=max_tokens, temperature=temperature, timeout=timeout), name, errors
        except FAILURES as exc:
            errors.append(f"{name}: {exc}")
    raise LLMUnavailable("; ".join(errors) or "no AI provider configured")
