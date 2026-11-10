"""Chunk boundaries, overlap and consistent token estimation."""

from rag.ingestion.chunker import chunk_pages, count_tokens
from rag.models import PageContent


def test_token_estimation_handles_words_punctuation_and_non_latin_text() -> None:
    assert count_tokens("release!") == 4
    assert count_tokens("alpha beta") == 4
    assert count_tokens("?????") > 0
    assert count_tokens("   ") == 0


def test_chunk_size_overlap_and_page_metadata() -> None:
    text = " ".join(f"item{index}" for index in range(100))
    chunks = chunk_pages([PageContent(page=3, section="Plan", text=text)], 24, 5)
    assert len(chunks) > 1
    for index, chunk in enumerate(chunks):
        assert chunk.chunk_index == index
        assert chunk.page == 3
        assert chunk.section == "Plan"
        assert 0 < chunk.token_count <= 24
        assert chunk.token_count == count_tokens(chunk.text)
    assert chunks[-1].text.endswith("item99")


def test_paragraph_boundary_is_preferred() -> None:
    first = "One small paragraph ends here."
    second = "Another paragraph contains additional words for testing."
    chunks = chunk_pages([PageContent(text=first + "\n\n" + second)], 16, 0)
    assert chunks[0].text == first
    assert "".join(chunk.text for chunk in chunks).endswith("testing.")


def test_pages_never_lose_their_original_location() -> None:
    chunks = chunk_pages(
        [
            PageContent(page=1, text="Page one."),
            PageContent(page=2, text="Page two."),
        ],
        32,
        4,
    )
    assert [chunk.page for chunk in chunks] == [1, 2]
