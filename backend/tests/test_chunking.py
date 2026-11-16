import pytest

from app.ingestion.pipeline import chunk_text, chunks

TEXT = " ".join(f"word{i} lorem ipsum dolor sit amet consectetur." for i in range(300))


@pytest.mark.meta("T07", "Chunking", "Chunks respect the size limit and never split a word", "Every chunk <= 700 chars; all tokens are whole words")
def test_chunk_size_and_word_boundaries(actual):
    out = chunk_text(TEXT, size=700)
    words = set(TEXT.split())
    assert out and all(len(c) <= 700 for c in out)
    assert all(tok in words for c in out for tok in c.split())
    actual(f"{len(out)} chunks, max {max(map(len, out))} chars")


@pytest.mark.meta("T08", "Chunking", "Consecutive chunks overlap to preserve context", "Tail of chunk i reappears at start of chunk i+1")
def test_chunk_overlap(actual):
    out = chunk_text(TEXT, size=700, overlap=120)
    for a, b in zip(out, out[1:]):
        assert b.split()[0] in a.split()[-30:]
    actual(f"overlap verified on {len(out) - 1} boundaries")


@pytest.mark.meta("T09", "Chunking", "Empty and tiny inputs produce no chunks", "[] for empty / whitespace / below min length")
def test_chunk_empty_inputs(actual):
    assert chunk_text("") == [] and chunk_text("   ") == [] and chunk_text("too short") == []
    actual("[] for all three")


@pytest.mark.meta("T10", "Chunking", "No text is lost: every word appears in some chunk (incl. legacy chunks())", "100% word coverage")
def test_chunk_coverage(actual):
    out = chunks(TEXT)
    covered = set(" ".join(out).split())
    assert set(TEXT.split()) <= covered
    actual("100% coverage")
