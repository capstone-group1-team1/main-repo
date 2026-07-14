"""Shared xAI / Groq LLM gateway.

Every LLM operation uses xAI / Grok 4.5 first. Only transient xAI provider
failures use the Groq / Llama 4 Scout fallback. The filename is retained for
compatibility with existing imports.
"""

from __future__ import annotations

from app.core.config import get_groq_client, get_settings, get_xai_client
from app.core.logging import get_logger
from app.synthesis.output_guard import final_content, load_json_content

log = get_logger(__name__)


class LLMUnavailable(Exception):
    pass


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return status if isinstance(status, int) else None


def _is_transient_xai_error(exc: Exception) -> bool:
    """Return true only for failures eligible for the Groq fallback."""
    status = _status_code(exc)
    if status == 429 or (status is not None and 500 <= status <= 599):
        return True
    name = exc.__class__.__name__.lower()
    return "timeout" in name or "connection" in name


def _error_label(exc: Exception) -> str:
    status = _status_code(exc)
    return f"HTTP {status}" if status is not None else exc.__class__.__name__


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_xai_text(system: str, user: str, temperature: float) -> str:
    resp = get_xai_client().chat.completions.create(
        model=get_settings().xai_model,
        messages=_messages(system, user),
        temperature=temperature,
        max_tokens=800,
    )
    return final_content(resp.choices[0].message.content)


def _call_xai_json(system: str, user: str, temperature: float) -> dict:
    resp = get_xai_client().chat.completions.create(
        model=get_settings().xai_model,
        messages=_messages(system, user),
        temperature=temperature,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return load_json_content(resp.choices[0].message.content)


def _call_groq_text(system: str, user: str, temperature: float) -> str:
    resp = get_groq_client().chat.completions.create(
        model=get_settings().groq_model,
        messages=_messages(system, user),
        temperature=temperature,
        max_tokens=800,
    )
    return final_content(resp.choices[0].message.content)


def _call_groq_json(system: str, user: str, temperature: float) -> dict:
    resp = get_groq_client().chat.completions.create(
        model=get_settings().groq_model,
        messages=_messages(system, user),
        temperature=temperature,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return load_json_content(resp.choices[0].message.content)


def _generate(system: str, user: str, temperature: float, primary_call, fallback_call):
    try:
        return primary_call(system, user, temperature)
    except Exception as primary_exc:
        if not _is_transient_xai_error(primary_exc):
            raise LLMUnavailable(
                f"xAI request failed ({_error_label(primary_exc)})"
            ) from primary_exc
        log.warning(
            "LLM fallback: primary=xAI error=%s fallback=Groq model=%s",
            _error_label(primary_exc),
            get_settings().groq_model,
        )
        try:
            return fallback_call(system, user, temperature)
        except Exception as fallback_exc:
            raise LLMUnavailable(
                f"xAI request failed ({_error_label(primary_exc)}); "
                f"Groq fallback failed ({_error_label(fallback_exc)})"
            ) from fallback_exc


def generate_text(system: str, user: str, temperature: float = 0.1) -> str:
    """Generate final answer text through xAI, then transient-only Groq fallback."""
    return _generate(system, user, temperature, _call_xai_text, _call_groq_text)


def generate_json(system: str, user: str, temperature: float = 0.0) -> dict:
    """Generate a JSON object through xAI, then transient-only Groq fallback."""
    return _generate(system, user, temperature, _call_xai_json, _call_groq_json)


def generate(system: str, user: str, temperature: float = 0.1) -> str:
    """Compatibility wrapper for existing answer-path callers."""
    return generate_text(system, user, temperature)


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------
#
# Same xAI-primary/Groq-fallback contract as generate(), with one honest
# limitation: the fallback only applies BEFORE the first token is yielded
# (the case that covers the vast majority of failures — they happen on the
# initial request, before any streaming has started). If xAI's stream fails
# PARTWAY through an answer, switching providers mid-sentence would produce
# a visibly broken answer, so we log the error and end the stream there
# instead — the caller still has whatever text streamed successfully.
#
# NOTE: unlike generate_text()/generate_json(), streamed deltas are NOT
# passed through output_guard.final_content(). Stripping a <think>...</think>
# block requires seeing the whole block at once, which defeats token-by-token
# streaming. This mirrors the existing assumption that reasoning is kept out
# of visible output at the provider level; if a provider ever regresses on
# that, it would currently surface in a streamed answer where it wouldn't in
# a non-streamed one.


def _stream_xai(system: str, user: str, temperature: float):
    stream = get_xai_client().chat.completions.create(
        model=get_settings().xai_model,
        messages=_messages(system, user),
        temperature=temperature,
        max_tokens=800,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _stream_groq(system: str, user: str, temperature: float):
    stream = get_groq_client().chat.completions.create(
        model=get_settings().groq_model,
        messages=_messages(system, user),
        temperature=temperature,
        max_tokens=800,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def generate_stream(system: str, user: str, temperature: float = 0.1):
    """Streaming counterpart of generate_text(): yields text chunks as they
    arrive instead of returning the full string at once."""
    started = False
    try:
        for token in _stream_xai(system, user, temperature):
            started = True
            yield token
    except Exception as xai_exc:
        if started:
            log.error(
                "xAI stream failed mid-answer (%s) — ending stream early", xai_exc
            )
            return
        if not _is_transient_xai_error(xai_exc):
            raise LLMUnavailable(
                f"xAI request failed ({_error_label(xai_exc)})"
            ) from xai_exc
        log.warning(
            "LLM stream fallback: primary=xAI error=%s fallback=Groq model=%s",
            _error_label(xai_exc),
            get_settings().groq_model,
        )
        try:
            yield from _stream_groq(system, user, temperature)
        except Exception as groq_exc:
            raise LLMUnavailable(
                f"xAI request failed ({_error_label(xai_exc)}); "
                f"Groq fallback failed ({_error_label(groq_exc)})"
            ) from groq_exc
