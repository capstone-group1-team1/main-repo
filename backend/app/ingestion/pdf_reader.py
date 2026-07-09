"""
pdf_reader.py — extracts text from the (text-based) manual PDFs.

The manuals are plain text exported as PDF, so pypdf's text layer is
sufficient — no OCR / layout framework needed.  Output preserves page
numbers so citations can point at a page.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.core.logging import get_logger

log = get_logger(__name__)


def read_pdf(path: Path) -> list[tuple[int, str]]:
    """Return [(page_number, page_text), ...] (1-based pages).

    Raises FileNotFoundError if the PDF is missing and ValueError if the
    PDF has no extractable text at all (e.g. a pure scan was uploaded)."""
    if not path.exists():
        raise FileNotFoundError(path)

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append((i, text))

    if not any(t for _, t in pages):
        raise ValueError(
            f"{path.name}: no extractable text found. "
            "Manuals must be text-based PDFs (not scans)."
        )
    log.info("Read %s: %d pages", path.name, len(pages))
    return pages
