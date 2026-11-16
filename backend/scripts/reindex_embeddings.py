r"""Embed every indexed chunk (Gemini gemini-embedding-001) into data/embeddings.npz.

Paced for the free tier (retries after rate limits). Usage (from backend/):
    .venv\Scripts\python -m scripts.reindex_embeddings
"""
import json
import time

from app.services import embeddings

if __name__ == "__main__":
    t = time.time()
    print(json.dumps(embeddings.sync(patient=True)), f"{time.time() - t:.0f}s")
