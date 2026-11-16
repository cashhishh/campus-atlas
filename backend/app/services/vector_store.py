"""Chunk store with ChromaDB when available and a dependable local JSON fallback.

The JSON fallback ranks chunks with BM25 (keyword relevance) so it is
deterministic and works with no ML downloads. Chunks for a source are always
replaced as a set, so stale text never survives a content update.
"""
import json
import os
import math
import re
import threading
from collections import Counter

from ..config import VECTOR_DRIVER, chroma_path, data_dir

_lock = threading.Lock()
_chroma_collection = None

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "by", "from", "is", "are", "was",
    "were", "be", "been", "do", "does", "did", "what", "which", "who", "whom", "how", "when", "where", "why", "tell",
    "me", "about", "please", "can", "could", "i", "you", "it", "its", "this", "that", "these", "those", "there",
    "their", "they", "my", "your", "our", "we", "as", "if", "any", "some", "give", "show", "know", "want", "college",
    "hai", "ka", "ke", "ki", "mai", "bare", "batao", "kya",
}
SYNONYMS = {
    "ece": ["electronics", "communication"],
    "eee": ["electrical", "electronics"],
    "aiml": ["artificial", "intelligence", "machine", "learning"],
    "ai": ["artificial", "intelligence"],
    "mech": ["mechanical"],
    "fees": ["fee"],
    "hostels": ["hostel"],
    "placements": ["placement"],
    "programmes": ["programme", "program"],
    "programs": ["programme", "program"],
    "courses": ["course", "programme"],
    "btech": ["b", "tech"],
    "ranking": ["rank", "nirf"],
    "rank": ["ranking", "nirf", "band"],
    "recruit": ["recruiter", "placement", "company"],
    "recruits": ["recruiter", "placement", "company"],
    "recruiters": ["recruit", "placement", "company"],
    "companies": ["company", "recruiter", "placement"],
    "salary": ["package", "ctc", "median"],
    "package": ["salary", "ctc", "lpa"],
    "intake": ["seat", "seats"],
    "seats": ["intake"],
    "accredited": ["accreditation", "naac", "nba"],
    "hostel": ["hostel", "accommodation"],
    "cse": ["computer", "science"],
}


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith(("ches", "shes", "xes")):
        return token[:-2]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str, expand: bool = False) -> list[str]:
    tokens = []
    for raw in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if raw in STOPWORDS:
            continue
        tokens.append(_stem(raw))
        if expand:
            tokens.extend(_stem(s) for s in SYNONYMS.get(raw, []))
    return tokens


# ---------------------------------------------------------------- JSON store
def _json_path():
    return data_dir() / "chunks.json"


_cache: dict = {"key": None, "chunks": []}
# Cosine similarity mapped to 0..1 relevance (calibrated on the pilot index, gemini-embedding-001).
COS_FLOOR = float(os.getenv("COS_FLOOR", "0.60"))
COS_HIGH = float(os.getenv("COS_HIGH", "0.75"))


def _load() -> list[dict]:
    path = _json_path()
    if not path.exists():
        return []
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if _cache["key"] != key:
            _cache["chunks"] = json.loads(path.read_text(encoding="utf-8"))
            _cache["key"] = key
        return list(_cache["chunks"])
    except (json.JSONDecodeError, OSError):
        return []


def _save(chunks: list[dict]) -> None:
    path = _json_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    _cache["key"] = None


# -------------------------------------------------------------- Chroma store
def _chroma():
    global _chroma_collection
    if VECTOR_DRIVER == "json":
        return None
    if _chroma_collection is None:
        try:
            import chromadb

            _chroma_collection = chromadb.PersistentClient(path=chroma_path()).get_or_create_collection("campusatlas")
        except Exception:
            if VECTOR_DRIVER == "chroma":
                raise
            return None
    return _chroma_collection


def driver_name() -> str:
    return "ChromaDB" if _chroma() is not None else "Local JSON fallback (BM25)"


# ------------------------------------------------------------------- API
def replace_source_chunks(source_id: int, chunks: list[dict]) -> str:
    """Atomically replace every chunk belonging to `source_id`."""
    with _lock:
        col = _chroma()
        if col is not None:
            col.delete(where={"source_id": source_id})
            if chunks:
                col.upsert(ids=[c["id"] for c in chunks], documents=[c["text"] for c in chunks],
                           metadatas=[c["metadata"] for c in chunks])
            return "chromadb"
        kept = [c for c in _load() if c["metadata"].get("source_id") != source_id]
        _save(kept + chunks)
    try:
        from . import embeddings
        embeddings.schedule_sync()  # embed new chunks in the background
    except Exception:
        pass
    return "local fallback"


def upsert(chunks: list[dict]) -> str:
    """Backward-compatible entry point (first-defence API)."""
    if not chunks:
        return "noop"
    return replace_source_chunks(chunks[0]["metadata"]["source_id"], chunks)


def delete_source(source_id: int) -> None:
    replace_source_chunks(source_id, [])


def _bm25(query_terms: list[str], docs: list[dict], k1: float = 1.4, b: float = 0.75) -> list[float]:
    tokenized = [tokenize(d["text"] + " " + d["metadata"].get("document_title", "")) for d in docs]
    n = len(tokenized) or 1
    avgdl = sum(len(t) for t in tokenized) / n or 1
    df = Counter(term for toks in tokenized for term in set(toks))
    unique_terms = set(query_terms)
    scores = []
    for toks in tokenized:
        tf = Counter(toks)
        dl = len(toks) or 1
        s = 0.0
        for term in unique_terms:
            if tf[term]:
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def query(text: str, college_ids=None, n: int = 8, semantic: bool = True) -> list[dict]:
    """Return up to `n` relevant chunks as {'text','metadata','score'}; score is 0..1."""
    col = _chroma()
    if col is not None:
        where = {"college_id": {"$in": list(college_ids)}} if college_ids else None
        r = col.query(query_texts=[text], n_results=n, where=where, include=["documents", "metadatas", "distances"])
        return [{"text": d, "metadata": m, "score": max(0.0, 1 - (dist or 0))}
                for d, m, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]
    docs = [c for c in _load() if not college_ids or c["metadata"].get("college_id") in college_ids]
    terms = tokenize(text, expand=True)
    if not docs or not terms:
        return []
    raw = _bm25(terms, docs)
    sims = None
    if semantic:
        from . import embeddings
        sims = embeddings.similarities(text, [d["id"] for d in docs])
    # Normalise against the best possible score for this query so the threshold is meaningful.
    ceiling = max(raw) if raw else 0
    coverage = []
    unique = set(terms)
    for d in docs:
        toks = set(tokenize(d["text"] + " " + d["metadata"].get("document_title", "")))
        coverage.append(len(unique & toks) / len(unique))
    ranked = []
    for d, s, cov in zip(docs, raw, coverage):
        bm = s / ceiling if ceiling else 0
        if sims:  # hybrid: semantic similarity + BM25 + term coverage
            cos = sims.get(d["id"])
            sem = 0.0 if cos is None else min(1.0, max(0.0, (cos - COS_FLOOR) / (COS_HIGH - COS_FLOOR)))
            if s <= 0 and sem <= 0:
                continue
            score = 0.5 * sem + 0.25 * bm + 0.25 * cov
            ranked.append({**d, "score": round(score, 4), "bm25": round(s, 3), "coverage": round(max(cov, sem), 3),
                           "cosine": None if cos is None else round(cos, 4)})
            continue
        if s <= 0:
            continue
        score = 0.5 * bm + 0.5 * cov
        ranked.append({**d, "score": round(score, 4), "bm25": round(s, 3), "coverage": round(cov, 3)})
    return sorted(ranked, key=lambda x: x["score"], reverse=True)[:n]


def all_chunks() -> list[dict]:
    col = _chroma()
    if col is not None:
        r = col.get(include=["documents", "metadatas"])
        return [{"id": i, "text": d, "metadata": m} for i, d, m in zip(r["ids"], r["documents"], r["metadatas"])]
    return _load()


def count():
    col = _chroma()
    if col is not None:
        return col.count(), "ChromaDB"
    return len(_load()), "Local JSON fallback (BM25)"


def count_by_source() -> Counter:
    return Counter(c["metadata"].get("source_id") for c in all_chunks())
