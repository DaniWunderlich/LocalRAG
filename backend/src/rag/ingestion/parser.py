"""Extract local document text without OCR or external services."""

import re
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from rag.errors import AppError
from rag.models import PageContent


def normalise(text: str) -> str:
    """Standardise line endings and horizontal whitespace, retaining paragraphs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[^\S\n]+", " ", text)).strip()


def extract_text(file_path: Path, content_type: str) -> list[PageContent]:
    """Parse a validated file or return an actionable, content-free error."""
    try:
        if content_type == "application/pdf":
            reader = PdfReader(file_path)
            if reader.is_encrypted:
                raise AppError("Encrypted PDFs are not supported.", 422, "extraction_failed")
            pages = [
                PageContent(page=index, text=normalise(page.extract_text() or ""))
                for index, page in enumerate(reader.pages, 1)
            ]
        elif content_type.endswith("wordprocessingml.document"):
            with ZipFile(file_path) as archive:
                if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise AppError("The expanded DOCX is too large.", 422, "extraction_failed")
            pages = []
            section: str | None = None
            for block in Document(str(file_path)).iter_inner_content():
                if isinstance(block, Paragraph):
                    text = normalise(block.text)
                    if block.style is not None and block.style.name.startswith("Heading"):
                        section = text
                elif isinstance(block, Table):
                    text = normalise(
                        "\n".join(" | ".join(cell.text for cell in row.cells) for row in block.rows)
                    )
                else:
                    continue
                pages.append(PageContent(section=section, text=text))
        else:
            text = normalise(file_path.read_text(encoding="utf-8-sig"))
            pages = []
            section = None
            for paragraph in text.split("\n\n"):
                if content_type == "text/markdown":
                    heading = re.match(r"^#{1,6}\s+(.+)", paragraph)
                    if heading:
                        section = heading.group(1)
                pages.append(PageContent(section=section, text=paragraph))
        pages = [page for page in pages if page.text.strip()]
        if not pages:
            raise AppError(
                "No readable text was found. Scanned PDFs require OCR, which is not supported.",
                422,
                "extraction_failed",
            )
        if content_type != "application/pdf":
            merged: list[PageContent] = []
            for page in pages:
                if merged and merged[-1].section == page.section:
                    merged[-1] = merged[-1].model_copy(
                        update={"text": merged[-1].text + "\n\n" + page.text}
                    )
                else:
                    merged.append(page)
            return merged
        return pages
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "The document could not be read. Check its format and UTF-8 encoding.",
            422,
            "extraction_failed",
        ) from exc
