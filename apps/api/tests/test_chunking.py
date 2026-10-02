from app.services.ingestion.chunking import approx_tokens, chunk_pages
from app.services.ingestion.parsing import PageText


def paragraph(n: int, words: int = 40) -> str:
    return " ".join(f"palabra{n}_{i}" for i in range(words)) + "."


def test_chunks_never_cross_pages() -> None:
    pages = [PageText(1, paragraph(1)), PageText(2, paragraph(2))]
    chunks = chunk_pages(pages, max_tokens=500)
    assert [c.page for c in chunks] == [1, 2]
    assert "palabra2" not in chunks[0].content


def test_chunks_respect_max_tokens_and_keep_order() -> None:
    text = "\n\n".join(paragraph(i) for i in range(30))
    chunks = chunk_pages([PageText(1, text)], max_tokens=200, overlap_tokens=30)
    assert len(chunks) > 1
    assert all(approx_tokens(c.content) <= 200 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert "palabra29_0" in chunks[-1].content


def test_consecutive_chunks_overlap() -> None:
    text = "\n\n".join(paragraph(i, words=10) for i in range(40))
    chunks = chunk_pages([PageText(1, text)], max_tokens=150, overlap_tokens=40)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        last_paragraph = prev.content.split("\n\n")[-1]
        assert nxt.content.startswith(last_paragraph) or last_paragraph in nxt.content


def test_heading_is_not_left_at_end_of_chunk() -> None:
    blocks = [paragraph(1, 60), paragraph(2, 60), "Quinta: Penalización", paragraph(3, 60)]
    chunks = chunk_pages([PageText(1, "\n\n".join(blocks))], max_tokens=260, overlap_tokens=0)
    for chunk in chunks:
        assert not chunk.content.endswith("Quinta: Penalización")
    assert any(c.content.startswith("Quinta: Penalización") for c in chunks)


def test_oversized_paragraph_is_split_by_words() -> None:
    chunks = chunk_pages([PageText(1, paragraph(1, words=600))], max_tokens=100)
    assert len(chunks) > 1
    assert all(approx_tokens(c.content) <= 100 for c in chunks)
