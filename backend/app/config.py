"""Central configuration for the CampusAtlas backend.

Values come from environment variables. `.env` files are merged so that the
root `.env` (shared with the Vite app) and `backend/.env` both work; a
non-empty value wins and real environment variables always take precedence.
"""
import os
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

_PLACEHOLDERS = {"", "your_groq_api_key_here"}


def _load_env_files() -> None:
    merged: dict[str, str] = {}
    for path in (ROOT_DIR / ".env", BACKEND_DIR / ".env"):
        if path.exists():
            for key, value in dotenv_values(path).items():
                if value not in (None, "") or key not in merged:
                    merged[key] = value or ""
    for key, value in merged.items():
        os.environ.setdefault(key, value)


_load_env_files()


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def resolve_db_url(url: str) -> str:
    """Anchor relative SQLite paths to the backend folder so cwd does not matter."""
    prefix = "sqlite:///./"
    if url.startswith(prefix):
        return "sqlite:///" + (BACKEND_DIR / url[len(prefix):]).as_posix()
    return url


def data_dir() -> Path:
    path = Path(os.getenv("CAMPUSATLAS_DATA_DIR", BACKEND_DIR / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def chroma_path() -> str:
    raw = os.getenv("CHROMA_PATH", "./chroma")
    return str(BACKEND_DIR / raw[2:]) if raw.startswith("./") else raw


def groq_api_key() -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    return "" if key in _PLACEHOLDERS else key


def groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


DATABASE_URL = resolve_db_url(os.getenv("DATABASE_URL", "sqlite:///./campusatlas.db"))
FRONTEND_ORIGINS = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",") if o.strip()]

# Phase 5 — monitoring and freshness
MONITOR_ENABLED = env_bool("MONITOR_ENABLED", True)
MONITOR_INTERVAL_MINUTES = env_int("MONITOR_INTERVAL_MINUTES", 360)
MONITOR_MAX_WORKERS = env_int("MONITOR_MAX_WORKERS", 6)
STALE_AFTER_HOURS = env_int("STALE_AFTER_HOURS", 72)

# Retrieval
# Minimum share of the question's content terms a chunk must contain to count as evidence.
MIN_RELEVANCE = float(os.getenv("MIN_RELEVANCE", "0.2"))
VECTOR_DRIVER = os.getenv("VECTOR_DRIVER", "auto").lower()  # auto | json | chroma

USER_AGENT = "Mozilla/5.0 (compatible; CampusAtlas/1.0; B.Tech academic research project)"
