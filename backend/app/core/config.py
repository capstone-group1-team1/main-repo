"""
config.py — THE single configuration module.

Every connection detail (Neo4j, Weaviate, Grok/xAI, Groq, embedding model) is read here,
from environment variables (populated by the local .env file in Stage 1).
No other module in the project may read os.environ or build a connection
string.  This is what makes the future Stage 2 migration a pure
environment-variable change with zero code changes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from tenacity import retry, stop_after_attempt, wait_exponential

# Resolve the project root (the folder that contains data/, .env, etc.).
# Locally this is the repo root, three levels above this file. In the Docker
# image the app is copied to /app (so this file is /app/app/core/config.py and
# the data volume mounts at /app/data) — set PROJECT_ROOT=/app in that case.
# The env override makes both layouts work without code changes.
import os

_ENV_ROOT = os.environ.get("PROJECT_ROOT")
_PROJECT_ROOT = (
    Path(_ENV_ROOT).resolve() if _ENV_ROOT else Path(__file__).resolve().parents[3]
)
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Typed application settings.  Fails fast at startup if XAI_API_KEY or
    GROQ_API_KEY is missing; everything else has working local-stack
    defaults."""

    # --- xAI Grok (primary LLM) ---
    xai_api_key: str
    xai_model: str = "grok-4.5"
    xai_base_url: str = "https://api.x.ai/v1"

    # --- Groq (fallback LLM, used only when Grok is rate-limited/unavailable
    # in the answer-generation path). Stays a REQUIRED key (not optional,
    # unlike the old Gemini fallback) because it's also called
    # unconditionally elsewhere: the router's cheap LLM-fallback classifier
    # (llm_fallback.py) and graph-enrichment extraction (extractor.py) both
    # go straight to Groq regardless of which provider answers /chat. ---
    groq_api_key: str
    # llama-4-scout, as specified. NOTE: Groq has this on its deprecation
    # list — shutdown date 07/17/26 — with openai/gpt-oss-120b or
    # qwen/qwen3.6-27b as the recommended replacements. Set here as
    # requested; will start failing after the shutdown date.
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "smartoffice123"

    # --- Weaviate ---
    weaviate_host: str = "localhost"
    weaviate_port: int = 8080
    weaviate_grpc_port: int = 50051

    # --- Embeddings ---
    embedding_model_name: str = "BAAI/bge-large-en-v1.5"
    embed_batch_size: int = 16

    # --- Semantic chunking (tunable, was hardcoded in chunker.py) ---
    chunk_breakpoint_percentile: int = 95
    chunk_buffer_size: int = 1

    # --- Retrieval + re-ranking (tunable, was hardcoded) ---
    retrieval_top_k: int = 5  # vector candidates per device
    max_evidence: int = 10  # evidence items sent to the LLM
    rerank_enabled: bool = True
    reranker_model_name: str = "BAAI/bge-reranker-base"
    rerank_candidate_pool: int = 20  # merged items to score before trimming

    # --- Hybrid (vector + BM25) search within the RAG branch ---
    # Weaviate's hybrid search fuses dense (vector/semantic) and sparse
    # (BM25/keyword) scores in one call. alpha=1.0 is pure vector, alpha=0.0
    # is pure BM25; 0.5 weighs them equally. Keyword matching catches exact
    # model numbers / error codes that a semantic embedding can under-weight.
    hybrid_search_enabled: bool = True
    hybrid_search_alpha: float = 0.5

    # --- Query router (tunable, was hardcoded in query_router.py) ---
    router_rule_margin_threshold: float = 0.25  # rule margin below this = unsure
    router_fallback_conf_threshold: float = 0.60  # LLM fallback below this = HYBRID

    # --- Graph retrieval limits (tunable, were hardcoded in graph_retriever) ---
    graph_max_facts: int = 15  # facts returned per question
    graph_neighbor_limit: int = 10  # neighbours per device query
    graph_incident_limit: int = 10  # incidents per device query
    graph_enrichment_limit: int = 8  # enrichment facts per device query

    # --- Retrieval cache (same question+route need not re-search) ---
    retrieval_cache_enabled: bool = True
    retrieval_cache_size: int = 256

    # --- Rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_chat: str = "20/minute"  # POST /chat
    rate_limit_write: str = "10/minute"  # incident/replace writes
    rate_limit_default: str = "120/minute"  # everything else

    # --- Backend behaviour ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    hash_store_path: str = str(_PROJECT_ROOT / "data" / "ingest_manifest.sqlite")
    enable_graph_enrichment: bool = True
    extraction_char_limit: int = 6000  # chunk text sent to the enrichment LLM
    extraction_call_delay_seconds: float = 0.0  # was 1.5s pacing between
    # enrichment/eval LLM calls to protect Groq's per-minute rate limit;
    # removed by request. If Grok/Groq starts 429-ing under load, the
    # @retry(wait_exponential(...)) decorators on the call sites still back
    # off automatically — raise this back up if that's not enough.
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT


@lru_cache
def get_settings() -> Settings:
    return Settings()  # raises a clear ValidationError if GROQ_API_KEY missing


# ---------------------------------------------------------------------------
# Client factories.  Cached: one driver / client / model per process.
# ---------------------------------------------------------------------------


@lru_cache
@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=15))
def get_neo4j_driver():
    """Neo4j Bolt driver.  The retry decorator absorbs slow store startup
    locally (and AuraDB resume-from-pause in Stage 2)."""
    from neo4j import GraphDatabase

    s = get_settings()
    driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    driver.verify_connectivity()
    return driver


@lru_cache
@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=15))
def get_weaviate_client():
    """Weaviate v4 client (local, anonymous)."""
    import weaviate

    s = get_settings()
    client = weaviate.connect_to_local(
        host=s.weaviate_host, port=s.weaviate_port, grpc_port=s.weaviate_grpc_port
    )
    return client


@lru_cache
def get_groq_client():
    """Fallback LLM client. GROQ_API_KEY is a required setting, so this
    always has a key by the time Settings validates."""
    from groq import Groq

    return Groq(api_key=get_settings().groq_api_key)


@lru_cache
def get_xai_client():
    """Primary LLM client. xAI's Grok API is OpenAI-compatible, so we reuse
    the `openai` SDK (already a project dependency) pointed at xAI's base
    URL rather than hand-rolling request/response handling. This gives
    groq_client.py's `.chat.completions.create(...)` calls (both plain and
    `stream=True`) an object with the exact same shape the Groq SDK client
    already has, so both providers can share the same call sites.
    XAI_API_KEY is a required setting, so this always has a key by the time
    Settings validates."""
    from openai import OpenAI

    s = get_settings()
    return OpenAI(api_key=s.xai_api_key, base_url=s.xai_base_url, timeout=60.0)


@lru_cache
def get_embed_model():
    """bge-large-en-v1.5 via sentence-transformers.  Loaded once (~1.3 GB,
    CPU is fine).  Shared by ingestion AND query-time retrieval so document
    and query vectors always live in the same space."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model_name)


@lru_cache
def get_reranker_model():
    """bge-reranker-base cross-encoder (~500 MB), loaded once. A cross-encoder
    scores a (query, passage) PAIR jointly, which is far more accurate at
    ordering than the bi-encoder similarity used for first-stage retrieval.
    Returns None if reranking is disabled, so the caller degrades to the
    merge order."""
    if not get_settings().rerank_enabled:
        return None
    from sentence_transformers import CrossEncoder

    return CrossEncoder(get_settings().reranker_model_name)


@lru_cache
def get_llamaindex_embed_model():
    """The SAME bge-large model, wrapped in LlamaIndex's embedding interface.
    Used only by the semantic chunker (SemanticSplitterNodeParser needs a
    LlamaIndex BaseEmbedding to measure sentence-to-sentence similarity).
    Keeping it the same underlying model means chunk-boundary vectors live in
    the same space as the document/query vectors."""
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    return HuggingFaceEmbedding(model_name=get_settings().embedding_model_name)


# bge models retrieve best when the QUERY (not the documents) is prefixed
# with this instruction.  Keep it in one place.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def close_all_clients() -> None:
    """Close the cached store clients and clear their caches.

    Call this at the end of any process that opened them: the API's lifespan
    shutdown, and every CLI entry point (seeding, eval helpers). The Weaviate
    v4 client in particular holds a gRPC channel + HTTP pool and logs resource
    warnings if it is not closed explicitly. Because the getters are
    @lru_cache singletons, we also clear the cache so a later call returns a
    fresh, open client instead of a closed one."""
    # Neo4j
    if get_neo4j_driver.cache_info().currsize:
        try:
            get_neo4j_driver().close()
        except Exception:
            pass
        get_neo4j_driver.cache_clear()
    # Weaviate
    if get_weaviate_client.cache_info().currsize:
        try:
            get_weaviate_client().close()
        except Exception:
            pass
        get_weaviate_client.cache_clear()
    # xAI (the openai.OpenAI client holds an httpx connection pool internally)
    if get_xai_client.cache_info().currsize:
        try:
            get_xai_client().close()
        except Exception:
            pass
        get_xai_client.cache_clear()
