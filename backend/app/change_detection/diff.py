"""Version diffs and human-readable change summaries."""
import difflib
import re

from ..ai import llm

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?|])\s+|\s{2,}|\s+[•·|]\s+")


def passages(text: str) -> list[str]:
    """Split extracted text into comparable passages (sentence-like units)."""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text or "")]
    return [p for p in parts if len(p) > 2]


def compute_diff(old_text: str, new_text: str, context: int = 1, max_chars: int = 20000) -> dict:
    old_p, new_p = passages(old_text), passages(new_text)
    matcher = difflib.SequenceMatcher(a=old_p, b=new_p, autojunk=False)
    added, removed = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(old_p[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(new_p[j1:j2])
    unified = "\n".join(difflib.unified_diff(old_p, new_p, fromfile="previous", tofile="current", lineterm="", n=context))
    return {
        "added": added,
        "removed": removed,
        "unified": unified[:max_chars],
        "similarity": round(matcher.ratio(), 3),
    }


def _clip(text: str, n: int = 140) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def deterministic_summary(diff: dict, source_name: str = "the source") -> str:
    added, removed = diff["added"], diff["removed"]
    if not added and not removed:
        return f"Formatting-only change detected on {source_name}; no passage-level text changed."
    pieces = [f"{len(added)} passage(s) added and {len(removed)} removed on {source_name} "
              f"(text similarity {diff['similarity'] * 100:.0f}%)."]
    if added:
        pieces.append("New: " + "; ".join(f"“{_clip(a)}”" for a in added[:2]) + ("…" if len(added) > 2 else ""))
    if removed:
        pieces.append("Removed: " + "; ".join(f"“{_clip(r)}”" for r in removed[:2]) + ("…" if len(removed) > 2 else ""))
    return " ".join(pieces)


def new_content_summary(text: str, chunk_count: int, title: str | None) -> str:
    return (f"First indexed version of “{_clip(title or 'document', 80)}”: "
            f"{len(text):,} characters extracted into {chunk_count} searchable chunk(s).")


SUMMARY_PROMPT = """You summarise changes to a college web page or PDF for students.
Use ONLY the added and removed passages provided. Do not add outside facts, numbers or dates.
Write 1-2 plain sentences (max 60 words) describing what changed. If the change looks like
navigation, dates of page rendering or other boilerplate, say it is a minor/boilerplate change."""


def summarize_change(diff: dict, source_name: str, use_llm: bool = True) -> tuple[str, str]:
    """Return (summary, mode). mode = gemini | groq | deterministic (fallback order set by LLM_PROVIDER)."""
    fallback = deterministic_summary(diff, source_name)
    if not use_llm or not llm.is_configured() or not (diff["added"] or diff["removed"]):
        return fallback, "deterministic"
    added = "\n".join(f"+ {_clip(a, 300)}" for a in diff["added"][:15])
    removed = "\n".join(f"- {_clip(r, 300)}" for r in diff["removed"][:15])
    try:
        text, provider, _ = llm.generate(SUMMARY_PROMPT, f"SOURCE: {source_name}\nADDED:\n{added or '(none)'}\nREMOVED:\n{removed or '(none)'}",
                                max_tokens=220, timeout=15, prefer=llm.task_provider("summary"))
        return text.strip(), provider
    except llm.LLMUnavailable:
        return fallback, "deterministic"
