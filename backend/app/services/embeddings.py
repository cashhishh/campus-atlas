"""Semantic embeddings for chunks (Gemini `gemini-embedding-001`, 768-d) in a local numpy index.

* `sync()` embeds any chunk that has no vector yet (batched, 100 per call) and drops vectors
  of deleted chunks. It runs in a background thread after ingestion and at startup.
* `similarities(query, ids)` returns cosine similarity per chunk id, or None when embeddings
  are unavailable (no key, quota, offline) -> callers fall back to keyword/BM25 ranking.
"""
import os
import threading
import time
from collections import OrderedDict

import numpy as np

from ..config import data_dir

MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
DIM = 768
_lock = threading.Lock()
_state = {"ids": [], "index": {}, "matrix": np.zeros((0, DIM), dtype=np.float32), "loaded": False, "last_error": None}
_query_cache: OrderedDict = OrderedDict()
_sync_timer: threading.Timer | None = None
_disabled_until = 0.0


def _path():
    return data_dir() / "embeddings.npz"


def enabled() -> bool:
    if os.getenv("SEMANTIC_SEARCH", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    from ..ai import gemini_client
    return gemini_client.is_configured() and time.time() >= _disabled_until


def _load():
    if _state["loaded"]:
        return
    p = _path()
    if p.exists():
        try:
            d = np.load(p, allow_pickle=False)
            _state["ids"] = [str(x) for x in d["ids"]]
            _state["matrix"] = d["matrix"].astype(np.float32)
        except Exception:
            _state["ids"], _state["matrix"] = [], np.zeros((0, DIM), dtype=np.float32)
    _state["index"] = {cid: i for i, cid in enumerate(_state["ids"])}
    _state["loaded"] = True


def _save():
    tmp = _path().with_suffix(".tmp.npz")
    np.savez(tmp, ids=np.array(_state["ids"]), matrix=_state["matrix"])
    os.replace(tmp, _path())


def _embed(texts: list[str], task: str) -> np.ndarray:
    global _disabled_until
    from google.genai import types

    from ..ai import gemini_client

    client = gemini_client._client(15)
    try:
        r = client.models.embed_content(model=MODEL, contents=texts,
                                        config=types.EmbedContentConfig(task_type=task, output_dimensionality=DIM))
    except Exception as exc:
        if getattr(exc, "code", None) == 429:
            _disabled_until = time.time() + 60  # quota: skip semantic search for a minute
        _state["last_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        raise
    m = np.array([e.values for e in r.embeddings], dtype=np.float32)
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def sync(batch: int = 40, patient: bool = False) -> dict:
    """Embed missing chunks, drop stale ones. Safe to call repeatedly."""
    from .vector_store import all_chunks

    global _disabled_until
    if patient:
        _disabled_until = 0.0
    if not enabled():
        return {"status": "disabled"}
    with _lock:
        _load()
        chunks = {c["id"]: c for c in all_chunks()}
        keep = [i for i, cid in enumerate(_state["ids"]) if cid in chunks]
        ids = [_state["ids"][i] for i in keep]
        matrix = _state["matrix"][keep] if keep else np.zeros((0, DIM), dtype=np.float32)
        missing = [cid for cid in chunks if cid not in set(ids)]
        added = 0
        for start in range(0, len(missing), batch):
            part = missing[start:start + batch]
            texts = [(chunks[c]["metadata"].get("document_title", "") + "\n" + chunks[c]["text"])[:6000] for c in part]
            vecs = None
            for attempt in range(8 if patient else 1):
                try:
                    vecs = _embed(texts, "RETRIEVAL_DOCUMENT")
                    break
                except Exception:
                    if patient:  # free tier: tokens-per-minute limit -> wait and retry
                        time.sleep(20)
                        _disabled_until = 0.0
            if vecs is None:
                break
            if patient:
                time.sleep(1.5)
            ids += part
            matrix = np.vstack([matrix, vecs])
            added += len(part)
        _state["ids"], _state["matrix"] = ids, matrix
        _state["index"] = {cid: i for i, cid in enumerate(ids)}
        _save()
        return {"status": "ok", "vectors": len(ids), "added": added, "missing": len(chunks) - len(ids)}


def schedule_sync(delay: float = 3.0) -> None:
    """Debounced background sync after ingestion (never blocks a request)."""
    global _sync_timer
    if not enabled():
        return
    if _sync_timer is not None:
        _sync_timer.cancel()
    _sync_timer = threading.Timer(delay, lambda: _safe_sync())
    _sync_timer.daemon = True
    _sync_timer.start()


def _safe_sync():
    try:
        sync()
    except Exception as exc:
        _state["last_error"] = f"{type(exc).__name__}: {exc}"[:200]


def query_vector(text: str) -> np.ndarray | None:
    if not enabled():
        return None
    key = text.strip().lower()
    if key in _query_cache:
        _query_cache.move_to_end(key)
        return _query_cache[key]
    try:
        v = _embed([text], "RETRIEVAL_QUERY")[0]
    except Exception:
        return None
    _query_cache[key] = v
    if len(_query_cache) > 256:
        _query_cache.popitem(last=False)
    return v


def similarities(text: str, ids: list[str]) -> dict[str, float] | None:
    """Cosine similarity for each chunk id that has a vector; None if semantic search is unavailable."""
    q = query_vector(text)
    if q is None:
        return None
    with _lock:
        _load()
        rows = [(cid, _state["index"][cid]) for cid in ids if cid in _state["index"]]
        if not rows:
            return {}
        sims = _state["matrix"][[r for _, r in rows]] @ q
    return {cid: float(s) for (cid, _), s in zip(rows, sims)}


def status() -> dict:
    with _lock:
        _load()
        return {"enabled": enabled(), "model": MODEL, "vectors": len(_state["ids"]), "last_error": _state["last_error"]}
