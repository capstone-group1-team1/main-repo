"""
Tests for app.synthesis.groq_client.generate_stream() -- the streaming
counterpart to generate_text(), added for POST /chat/stream.

Non-streaming generate()/generate_text()/generate_json() already have
thorough coverage in test_llm_provider_fallback.py; this file covers only
the streaming path, which has one behavior the non-streaming path doesn't:
fallback is only attempted BEFORE the first token is yielded. Every
assertion here was verified by actually running generate_stream() against
these fake streaming clients.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.synthesis import groq_client


def _chunk(delta_text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=delta_text))])


class _TransientError(Exception):
    status_code = 429


class _AuthError(Exception):
    status_code = 401


def test_successful_xai_stream_yields_tokens_without_touching_groq(monkeypatch):
    def xai_stream(*a, **k):
        return iter([_chunk("Hello"), _chunk(" "), _chunk("world"), _chunk(None)])

    groq_calls = []
    monkeypatch.setattr(groq_client, "get_xai_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=xai_stream))))
    monkeypatch.setattr(groq_client, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda *a, **k: groq_calls.append(1)))))
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(
        xai_model="grok-4.5", groq_model="fallback-model"))

    tokens = list(groq_client.generate_stream("system", "user"))

    assert "".join(t for t in tokens if t) == "Hello world"
    assert groq_calls == []  # Groq never touched -- Chunk(None) delta is skipped, not an error


def test_transient_failure_before_first_token_falls_back_to_groq_stream(monkeypatch):
    def xai_stream_fails(*a, **k):
        raise _TransientError("rate limited")

    def groq_stream(*a, **k):
        return iter([_chunk("Fallback"), _chunk(" answer")])

    monkeypatch.setattr(groq_client, "get_xai_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=xai_stream_fails))))
    monkeypatch.setattr(groq_client, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=groq_stream))))
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(
        xai_model="grok-4.5", groq_model="fallback-model"))

    tokens = list(groq_client.generate_stream("system", "user"))

    assert "".join(tokens) == "Fallback answer"


def test_failure_mid_stream_ends_early_without_attempting_fallback(monkeypatch):
    """Once tokens have already reached the caller, switching providers
    mid-answer would produce a visibly broken response -- so a mid-stream
    failure must end the stream with whatever was already yielded, and must
    NOT fall back to Groq (which would start a fresh, disjointed answer)."""
    def xai_stream_partial(*a, **k):
        def gen():
            yield _chunk("Partial")
            raise _TransientError("connection lost mid-stream")
        return gen()

    groq_calls = []

    def groq_stream_should_never_run(*a, **k):
        groq_calls.append(1)
        return iter([_chunk("should not appear")])

    monkeypatch.setattr(groq_client, "get_xai_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=xai_stream_partial))))
    monkeypatch.setattr(groq_client, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=groq_stream_should_never_run))))
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(
        xai_model="grok-4.5", groq_model="fallback-model"))

    tokens = list(groq_client.generate_stream("system", "user"))

    assert tokens == ["Partial"]
    assert groq_calls == []


def test_non_transient_failure_before_first_token_raises_without_fallback(monkeypatch):
    def xai_stream_auth_fails(*a, **k):
        raise _AuthError("bad key")

    groq_calls = []
    monkeypatch.setattr(groq_client, "get_xai_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=xai_stream_auth_fails))))
    monkeypatch.setattr(groq_client, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda *a, **k: groq_calls.append(1)))))

    with pytest.raises(groq_client.LLMUnavailable, match="HTTP 401"):
        list(groq_client.generate_stream("system", "user"))

    assert groq_calls == []
