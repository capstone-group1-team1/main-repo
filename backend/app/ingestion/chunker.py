"""
chunker.py — pure SEMANTIC chunking via LlamaIndex.

Instead of splitting on the manual's layout (headings/paragraphs) or on a
fixed token window, we split on MEANING: LlamaIndex's
`SemanticSplitterNodeParser` embeds each sentence with bge-large and starts a
new chunk wherever the similarity between consecutive sentences drops past a
threshold (a "semantic breakpoint"). So each chunk is a block of sentences
that talk about the same thing, and a boundary falls exactly where the topic
shifts.

Why semantic: retrieval quality is bounded by chunk quality. A semantically
coherent chunk produces a sharper embedding, so the right chunk wins top-1
with a clearer score gap (which in turn feeds Retrieval Confidence), and the
citation snippet a technician sees is a self-contained thought rather than an
arbitrary slice.


"""

from __future__ import annotations

import re
from dataclasses import dataclass

from llama_index.core import Document
from llama_index.core.node_parser import SemanticSplitterNodeParser

from app.core.config import get_llamaindex_embed_model, get_settings

# A very light guard so a stray heading line still labels its chunk.
_NUMBERED = re.compile(r"^\d+(\.\d+)*\.?\s+\S")
_ALLCAPS = re.compile(r"^[A-Z][A-Z0-9 \-/&(),.]{2,60}$")


@dataclass
class Chunk:
    text: str
    section_title: str
    page_number: int
    ordinal: int  # position within the document (part of the chunk id)


def _page_for_offset(offset: int, page_spans: list[tuple[int, int, int]]) -> int:
    """Map a character offset in the concatenated document back to its page."""
    for start, end, page_no in page_spans:
        if start <= offset < end:
            return page_no
    return page_spans[-1][2] if page_spans else 1


def _title_for(text: str) -> str:
    """Best-effort label: the first heading-like line in the chunk, else the
    first few words. Used only for display / the citation reference string."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _NUMBERED.match(line) or _ALLCAPS.match(line):
            return line[:80]
        return " ".join(line.split()[:8])[:80]
    return "Section"


def chunk_document(pages: list[tuple[int, str]]) -> list[Chunk]:
    """Concatenate the page texts, remember page boundaries, run the semantic
    splitter, then map each resulting node back to the page it started on."""
    # Build one document string and a char-offset -> page map.
    full_parts: list[str] = []
    page_spans: list[tuple[int, int, int]] = []
    cursor = 0
    for page_no, text in pages:
        text = text or ""
        start = cursor
        full_parts.append(text)
        cursor += len(text) + 2  # +2 for the "\n\n" join
        page_spans.append((start, cursor, page_no))
    full_text = "\n\n".join(full_parts).strip()
    if not full_text:
        return []

    settings = get_settings()
    splitter = SemanticSplitterNodeParser.from_defaults(
        embed_model=get_llamaindex_embed_model(),
        buffer_size=settings.chunk_buffer_size,
        breakpoint_percentile_threshold=settings.chunk_breakpoint_percentile,
    )
    nodes = splitter.get_nodes_from_documents([Document(text=full_text)])

    chunks: list[Chunk] = []
    for ordinal, node in enumerate(nodes):
        node_text = node.get_content().strip()
        if not node_text:
            continue
        # Locate the node in the full text to recover its page number.
        offset = full_text.find(node_text[:60])
        page_no = _page_for_offset(offset if offset >= 0 else 0, page_spans)
        chunks.append(
            Chunk(
                text=node_text,
                section_title=_title_for(node_text),
                page_number=page_no,
                ordinal=ordinal,
            )
        )
    return chunks
