from pathlib import Path

from app.rag.chunking import load_all_chunks

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT.parent / "output"


def test_load_chunks_from_output():
    if not OUTPUT.is_dir() or not list(OUTPUT.glob("*.md")):
        import pytest

        pytest.skip("no output/*.md")
    chunks = load_all_chunks(OUTPUT, max_tokens=900, overlap_tokens=120)
    assert len(chunks) > 50
    assert all(c.source.endswith(".md") for c in chunks)
    assert all(len(c.text) >= 80 for c in chunks)
