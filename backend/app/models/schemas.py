"""
schemas.py — the shared type vocabulary.

Two things live here:
  1. The public API contract models (must match API responses exactly).
  2. The internal "evidence" contract between retrieval and synthesis:
     RetrievedChunk (vector store) and GraphFact (Neo4j).  Their metadata
     is what makes every citation traceable to a real source.

This file must be importable with ZERO infrastructure (no DB clients).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Defines allowed user roles for authorization
Role = Literal["operator", "technician", "admin"]
# Defines how the answer retrieval pipeline was executed
# GRAPH_ONLY = Neo4j only, RAG_ONLY = Vector search only, HYBRID = both
Route = Literal["GRAPH_ONLY", "RAG_ONLY", "HYBRID"]


# ---------------------------------------------------------------------------
# Mock users
# ---------------------------------------------------------------------------

class MockUser(BaseModel):
    id: str
    name: str
    role: Role  # Used for permission checks


# ---------------------------------------------------------------------------
# Internal evidence contract (retrieval -> synthesis)
# ---------------------------------------------------------------------------

class RetrievedChunk(BaseModel):
    """One vector-search hit, carrying ALL citation metadata attached at
    ingestion time.  If a field here is dropped anywhere in the pipeline,
    citations break — hence a single typed contract."""

    chunk_id: str
    text: str
    score: float      # cosine similarity (0..1)
    
    source_type: Literal["manual", "incident"]
    source_id: str                    # "manual-name § section"  or  "I007"
    
    document_id: str
    document_name: str
    
    device_id: str
    device_name: str
    
    section_title: str
    page_number: Optional[int] = None   # Exists only for PDF-based sources


class GraphFact(BaseModel):
    """ Represents one fact retrieved from Neo4j.
        Stores graph path information for citation generation."""
    
    fact_id: str
    path_str: str                     # CP4-001 —CONTROLS→ DISP-001
    text: str                         # human-readable sentence for the LLM
    device_id: Optional[str] = None
    hop_count: int = 1                # Number of graph relationships traversed
    matched_exactly: bool = True      # Indicates if entity matching was exact or fuzzy
    source_chunk_id: Optional[str] = None   # Links graph facts back to RAG chunks if enriched


class RetrievalSignals(BaseModel):
    """Raw inputs for Retrieval Confidence (computed in synthesis/confidence)."""
    scores: list[float] = Field(default_factory=list)


class GraphSignals(BaseModel):
    """Raw inputs for Graph Confidence."""
    any_exact_entity_match: bool = False
    min_hop_count: int = 99             # Large default means no graph path was found
    fact_count: int = 0                 # Number of facts returned from graph search


# ---------------------------------------------------------------------------
# Public API contract
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class Citation(BaseModel):
    """
    Represents one evidence source supporting an answer sentence.
    """
    marker: int                        # the [n] in the answer text
    source_type: Literal["manual", "incident", "graph"]
    source_id: str
    snippet: str                       # chunk excerpt OR graph path string
    page_number: Optional[int] = None
    supports: str                      # The exact answer sentence supported by this citation


class Confidence(BaseModel):
    retrieval: Optional[float] = Field(default=None, ge=0, le=1)
    graph: Optional[float] = Field(default=None, ge=0, le=1)
    final: float = Field(ge=0, le=1)


class ChatResponse(BaseModel):
    # Final LLM answer containing citation markers, contains inline [1] [2] markers
    answer: str                        
    route: Route
    confidence: Confidence
    citations: list[Citation]
    unsourced_spans: list[str]         # answer sentences with no citation(supporting evidence)


class DeviceInfo(BaseModel):
    asset_id: str
    device_name: str
    manufacturer: str
    model: str
    serial_number: str
    room: str
    installation_date: str
    warranty_expiry: str
    status: str
    firmware_version: str
    relationships: list[str]           # human-readable edge strings


class GraphEdge(BaseModel):
    source: str
    relation: str
    target: str


class GraphNeighborhood(BaseModel):
    nodes: list[dict]
    edges: list[GraphEdge]


class IncidentIn(BaseModel):
    device_id: str
    problem: str = Field(min_length=3, max_length=300)
    resolution: str = Field(default="", max_length=300)   # empty = still open
    technician: str = Field(min_length=1, max_length=60)


class IncidentOut(BaseModel):
    incident_id: str
    device_id: str
    date: str
    problem: str
    resolution: str
    technician: str
    status: Literal["open", "resolved"]


class ReplaceDeviceRequest(BaseModel):
    old_asset_id: str
    new_asset_id: str
    new_device_name: str
    new_manufacturer: str
    new_model: str
    new_serial_number: str
    new_firmware_version: str = "1.0"
    manual_pdf_filename: Optional[str] = None   # in data/manuals_pdf/


class ReplacementSummary(BaseModel):
    old_asset_id: str
    new_asset_id: str
    edges_repointed: int
    retired_on: str
    installed_on: str
    manual_ingested: bool


class PermissionDenied(BaseModel):
    allowed: bool = False
    reason: str
