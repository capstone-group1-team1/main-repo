"""
routes_chat.py — POST /chat and POST /chat/stream, the system's primary
capability.

Orchestration only (no routing rules, no retrieval logic, no prompt text,
no confidence math live here — those are the owned modules it composes):

    permission -> Query Router -> branch retrieval -> LLM synthesis
    -> citation assembly -> three-signal confidence -> ChatResponse

/chat returns the ChatResponse in one shot. /chat/stream is the SAME
pipeline up to synthesis, but streams the answer text token-by-token over
Server-Sent Events as it's generated, then sends one final event with the
citations + confidence — computed only once the FULL answer text exists,
since citation assembly and confidence both require the complete text.
"""

import json
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth.permissions import require
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.core.logging import get_logger
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    GraphSignals,
    MockUser,
    RetrievalSignals,
)
from app.retrieval import (
    graph_retriever,
    hybrid_merger,
    reranker,
    retrieval_cache,
    vector_retriever,
)
from app.router.query_router import route as route_question
from app.synthesis import confidence as conf
from app.synthesis.citation_assembler import assemble
from app.synthesis.groq_client import LLMUnavailable, generate, generate_stream
from app.synthesis.prompts import SYSTEM_PROMPT, build_user_prompt

log = get_logger(__name__)
router = APIRouter()

_DECLINE = (
    "The available sources do not cover this question. "
    "Please check the device manuals or contact a technician."
)


def _get_evidence(question: str, decision):
    """Shared by /chat and /chat/stream: cache-first retrieval, branch
    retrieval on a miss, then cross-encoder rerank down to the evidence
    budget. Returns (evidence, r_sig, g_sig)."""
    settings = get_settings()

    cached = retrieval_cache.get(question, decision.route)
    if cached is not None:
        candidates, r_sig, g_sig = (
            cached["candidates"],
            cached["r_sig"],
            cached["g_sig"],
        )
    else:
        chunks, r_sig = [], RetrievalSignals()
        facts, g_sig = [], GraphSignals()
        try:
            if decision.route in ("RAG_ONLY", "HYBRID"):
                chunks, r_sig = vector_retriever.retrieve(question, decision.entities)
            if decision.route in ("GRAPH_ONLY", "HYBRID"):
                facts, g_sig = graph_retriever.retrieve(question, decision.entities)
        except Exception as exc:
            # Degrade rather than fail: whichever branch survived still answers,
            # and the missing signal drags Final Confidence down honestly.
            log.warning("Retrieval branch failed (%s) — degrading", exc)

        if decision.route == "GRAPH_ONLY":
            candidates = list(facts)
        elif decision.route == "RAG_ONLY":
            candidates = list(chunks)
        else:
            candidates = hybrid_merger.merge(chunks, facts)

        retrieval_cache.put(
            question,
            decision.route,
            {"candidates": candidates, "r_sig": r_sig, "g_sig": g_sig},
        )

    # Cross-encoder rerank the candidate pool, then trim to the evidence budget.
    # Degrades to candidates[:max_evidence] if reranking is disabled/unavailable.
    evidence = reranker.rerank(question, candidates, top_n=settings.max_evidence)
    return evidence, r_sig, g_sig


def _finalize(raw_answer: str, evidence, decision, r_sig, g_sig) -> ChatResponse:
    """Shared by /chat and /chat/stream: citation assembly + three-signal
    confidence, once the full answer text is available."""
    assembled = assemble(raw_answer, evidence)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", assembled.text) if s.strip()]

    r_conf = (
        conf.retrieval_confidence(r_sig) if decision.route != "GRAPH_ONLY" else None
    )
    g_conf = conf.graph_confidence(g_sig) if decision.route != "RAG_ONLY" else None
    final = conf.final_confidence(
        decision.route,
        r_conf,
        g_conf,
        citation_count=len(assembled.citations),
        unsourced_count=len(assembled.unsourced_spans),
        sentence_count=len(sentences),
    )

    return ChatResponse(
        answer=assembled.text,
        route=decision.route,
        confidence=final,
        citations=assembled.citations,
        unsourced_spans=assembled.unsourced_spans,
    )


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit_chat)
def chat(
    request: Request, req: ChatRequest, user: MockUser = Depends(require("ask"))
) -> ChatResponse:
    decision = route_question(req.question)
    evidence, r_sig, g_sig = _get_evidence(req.question, decision)

    if evidence:
        try:
            raw_answer = generate(
                SYSTEM_PROMPT, build_user_prompt(req.question, evidence)
            )
        except LLMUnavailable as exc:
            raise HTTPException(502, detail=f"LLM temporarily unavailable: {exc}")
    else:
        raw_answer = _DECLINE

    return _finalize(raw_answer, evidence, decision, r_sig, g_sig)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
@limiter.limit(get_settings().rate_limit_chat)
def chat_stream(
    request: Request,
    req: ChatRequest = Body(...),
    user: MockUser = Depends(require("ask")),
) -> StreamingResponse:
    decision = route_question(req.question)
    evidence, r_sig, g_sig = _get_evidence(req.question, decision)

    def event_stream():
        collected = []
        if evidence:
            try:
                for token in generate_stream(
                    SYSTEM_PROMPT, build_user_prompt(req.question, evidence)
                ):
                    collected.append(token)
                    yield _sse({"type": "token", "text": token})
            except LLMUnavailable as exc:
                yield _sse(
                    {"type": "error", "detail": f"LLM temporarily unavailable: {exc}"}
                )
                return
            raw_answer = "".join(collected) if collected else _DECLINE
        else:
            raw_answer = _DECLINE

        response = _finalize(raw_answer, evidence, decision, r_sig, g_sig)
        yield _sse(
            {
                "type": "final",
                "answer": response.answer,
                "route": response.route,
                "confidence": response.confidence.model_dump(),
                "citations": [c.model_dump() for c in response.citations],
                "unsourced_spans": response.unsourced_spans,
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
