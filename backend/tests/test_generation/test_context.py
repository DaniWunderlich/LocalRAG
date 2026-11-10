"""Context budgets and source labels are verified independently of a model."""

from uuid import uuid4

from rag.ingestion.chunker import count_tokens
from rag.models import Source
from rag.retrieval.retriever import assemble_context


def source(text: str, index: int = 0) -> Source:
    """Create an inspectable retrieval result."""
    return Source(
        document_id=uuid4(),
        filename="test.txt",
        chunk_id=str(uuid4()),
        text=text,
        chunk_index=index,
        score=0.8,
        embedding_model="embed:test",
    )


def test_budget_includes_labels_and_metadata() -> None:
    chunks = [source("Friday release."), source("Monday meeting.", 1)]
    first_context, _ = assemble_context(chunks[:1], 1000)
    budget = count_tokens(first_context)
    context, included = assemble_context(chunks, budget)
    assert count_tokens(context) <= budget
    assert len(included) == 1
    assert included[0].source_id == 1
    assert included[0].text == chunks[0].text
    assert "Monday" not in context


def test_no_truncated_or_unsubmitted_source_is_returned() -> None:
    context, included = assemble_context([source("A very long excerpt." * 100)], 10)
    assert context == ""
    assert included == []


def test_later_small_source_can_fit_without_a_gap_in_labels() -> None:
    chunks = [source("Long text." * 200), source("Small excerpt.", 1)]
    context, included = assemble_context(chunks, 200)
    assert len(included) == 1
    assert included[0].source_id == 1
    assert included[0].chunk_index == 1
    assert "Source 1" in context
