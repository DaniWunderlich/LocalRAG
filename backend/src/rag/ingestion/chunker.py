"""Deterministic lexical token estimation and boundary-aware overlapping chunks.

The offline estimate counts Unicode word runs in groups of at most three
characters and each punctuation mark separately. It is deliberately more
conservative than the common four-characters-per-token rule for Latin prose.
It is an estimate, not the exact tokeniser of an arbitrary Ollama model.
Both chunking and context assembly use this same method.
"""

import re

from rag.models import Chunk, PageContent

TOKEN_PATTERN = re.compile(r"\w{1,3}|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    """Estimate lexical tokens without downloading a tokeniser at runtime."""
    return sum(1 for _ in TOKEN_PATTERN.finditer(text))


def chunk_pages(pages: list[PageContent], chunk_size: int, overlap: int) -> list[Chunk]:
    """Retain page boundaries and prefer paragraph, sentence and word endings."""
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Chunk size must be positive and exceed the overlap.")
    chunks: list[Chunk] = []
    for page in pages:
        spans = list(TOKEN_PATTERN.finditer(page.text))
        start = 0
        while start < len(spans):
            end = min(start + chunk_size, len(spans))
            if end < len(spans):
                lower = start + max(overlap + 1, chunk_size // 2)
                for boundary in (r"\n\s*\n", r"[.!?]\s+", r"\s+"):
                    candidates = [
                        i
                        for i in range(lower, end + 1)
                        if re.search(boundary, page.text[spans[i - 1].start() : spans[i].start()])
                    ]
                    if candidates:
                        end = candidates[-1]
                        break
            text = page.text[spans[start].start() : spans[end - 1].end()].strip()
            chunks.append(
                Chunk(
                    text=text,
                    page=page.page,
                    section=page.section,
                    chunk_index=len(chunks),
                    token_count=count_tokens(text),
                )
            )
            if end == len(spans):
                break
            start = max(start + 1, end - overlap)
    return chunks
