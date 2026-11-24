"""Google Gemini provider (official `google-genai` SDK).

Same contract as groq_client.chat(): return plain text or raise
GeminiUnavailable, so callers can fall back to Groq and then to the
deterministic grounded answer. Also provides an experimental web-research
call that uses the Google Search grounding tool.
"""
import os
import re
import time

from ..config import env_int

_PLACEHOLDERS = {"", "your_gemini_api_key_here"}
DEFAULT_MODEL = "gemini-3.5-flash"  # fast, stable Flash model (verified 16 Nov 2026)
DEFAULT_FALLBACKS = "gemini-3.1-flash-lite"
DEFAULT_TIMEOUT_S = 10.0  # the Gemini API rejects deadlines below 10 s  # per call; a hanging model falls through to the next model / Groq quickly
_working_model: str | None = None
_no_thinking_config: set[str] = set()  # models that reject a thinking budget
_missing_models: set[str] = set()  # models that returned 404 (retired / not available to this key)
_cooldown_until: dict[str, float] = {}  # models still rate-limited after a retry are skipped for a while


class GeminiUnavailable(RuntimeError):
    pass


def api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return "" if key in _PLACEHOLDERS else key


def is_configured() -> bool:
    return bool(api_key())


def candidate_models() -> list[str]:
    configured = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    # Preferred order every call; only permanently missing models are skipped, so a transient
    # 503/timeout on the preferred model does not pin all later calls to the fallback.
    ordered = [configured, DEFAULT_MODEL, *os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACKS).split(",")]
    seen, out = set(), []
    for m in ordered:
        m = (m or "").strip()
        if m and m not in seen and m not in _missing_models and _cooldown_until.get(m, 0) <= time.time():
            seen.add(m)
            out.append(m)
    return out


def active_model() -> str | None:
    return _working_model


def _client(timeout_s: float):
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key(), http_options=types.HttpOptions(timeout=int(max(10.0, timeout_s) * 1000)))


def _config(model: str, system: str, max_tokens: int, temperature: float, tools=None):
    from google.genai import types

    kwargs = dict(system_instruction=system, temperature=temperature, max_output_tokens=max_tokens)
    if tools:
        kwargs["tools"] = tools
    if model not in _no_thinking_config:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)  # fast, no hidden reasoning
    return types.GenerateContentConfig(**kwargs)


def _status(exc: Exception) -> int | None:
    return getattr(exc, "code", None)


def _call(system: str, user: str, max_tokens: int, temperature: float, timeout: float, tools=None, stop_on_429: bool = False):
    """Try each candidate model; one short retry on 429 / timeout / 5xx. Returns (response, model)."""
    global _working_model
    from google.genai import errors

    if not is_configured():
        raise GeminiUnavailable("GEMINI_API_KEY is not configured")
    try:
        client = _client(timeout)
    except Exception as exc:
        raise GeminiUnavailable(f"Gemini client could not start: {type(exc).__name__}") from exc
    last = "no model available"
    for model in candidate_models():
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model, contents=user, config=_config(model, system, max_tokens, temperature, tools))
                _working_model = model
                return response, model
            except errors.APIError as exc:
                code, msg = _status(exc), str(exc).lower()
                if code == 400 and "thinking" in msg and model not in _no_thinking_config:
                    _no_thinking_config.add(model)  # model does not accept a thinking budget: retry without
                    continue
                if code == 404 or (code == 400 and "model" in msg and ("not found" in msg or "not supported" in msg)):
                    last = f"model {model} unavailable"
                    _missing_models.add(model)
                    break  # try next model
                if code == 429 and stop_on_429:  # quota is per account: other models will not help
                    raise GeminiUnavailable("Gemini returned HTTP 429 (quota exhausted)") from exc
                if code == 429 and attempt == 0:  # rate limited: one short retry on the same model
                    time.sleep(env_int("GEMINI_RETRY_SECONDS", 1))
                    continue
                if code == 429:  # still rate limited / quota used up: skip this model for a while
                    _cooldown_until[model] = time.time() + env_int("GEMINI_COOLDOWN_SECONDS", 60)
                if code in (429, 500, 502, 503, 504):  # overloaded / deadline: try the next model
                    last = f"Gemini returned HTTP {code}"
                    break
                raise GeminiUnavailable(f"Gemini returned HTTP {code}") from exc
            except Exception as exc:  # timeouts / network errors raised by the HTTP layer
                last = f"Gemini request failed: {type(exc).__name__}"
                break
    raise GeminiUnavailable(last)


def _text(response) -> str:
    try:
        text = response.text or ""
    except Exception:
        text = ""
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    if not text:
        raise GeminiUnavailable("Gemini returned an empty answer")
    return text


def chat(system: str, user: str, max_tokens: int = 500, temperature: float = 0.1, timeout: float = 25.0) -> str:
    timeout = max(10.0, min(timeout, float(os.getenv("GEMINI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_S))))
    response, _ = _call(system, user, max_tokens, temperature, timeout)
    if _truncated(response) and max_tokens < 2400:  # cut off mid-answer: one retry with more room
        response, _ = _call(system, user, min(2400, max_tokens * 2), temperature, timeout)
    from .groq_client import complete_sentences
    return complete_sentences(_text(response))


def _truncated(response) -> bool:
    try:
        return "MAX_TOKENS" in str(response.candidates[0].finish_reason)
    except (AttributeError, IndexError, TypeError):
        return False


WEB_SYSTEM = """You are CampusAtlas web research (EXPERIMENTAL). Use Google Search to answer questions about
Indian colleges. Prefer official sources: college websites (.ac.in, .edu.in), government sites (.gov.in, .nic.in)
and NIRF (nirfindia.org). Treat aggregator or review sites as unofficial and say so. Never invent cutoffs, fees,
placement figures or dates; if sources disagree or you cannot verify, say that. Answer in at most 150 words,
plain text, no markdown tables."""


def web_research(question: str, timeout: float = 30.0, system: str | None = None) -> dict:
    """Gemini + Google Search grounding.

    Returns {answer, sources:[{title, url, domain}], supports:[(end_byte, [source_pos])], model}.
    `supports` maps each grounded sentence of the answer to positions in `sources` (deduplicated)."""
    from google.genai import types

    response, model = _call(system or WEB_SYSTEM, question, 1400, 0.2, timeout,
                            tools=[types.Tool(google_search=types.GoogleSearch())], stop_on_429=True)
    answer = _text(response)
    sources, pos_by_uri, chunk_pos, supports = [], {}, {}, []
    try:
        meta = response.candidates[0].grounding_metadata
        for i, chunk in enumerate((meta.grounding_chunks or []) if meta else []):
            web = getattr(chunk, "web", None)
            if not (web and web.uri):
                continue
            if web.uri not in pos_by_uri:
                pos_by_uri[web.uri] = len(sources)
                title = (web.title or "").strip()
                domain = getattr(web, "domain", None) or (title if "." in title and " " not in title else "")
                sources.append({"title": title or web.uri, "url": web.uri, "domain": domain})
            chunk_pos[i] = pos_by_uri[web.uri]
        for sup in (meta.grounding_supports or []) if meta else []:
            seg = getattr(sup, "segment", None)
            idx = [chunk_pos[c] for c in (sup.grounding_chunk_indices or []) if c in chunk_pos]
            if seg is not None and getattr(seg, "end_index", None) and idx:
                supports.append((seg.end_index, idx))
    except (AttributeError, IndexError, TypeError):
        pass
    # supports are computed on the raw text; only strip trailing whitespace so offsets stay valid
    return {"answer": answer, "sources": sources, "supports": supports, "model": model}
