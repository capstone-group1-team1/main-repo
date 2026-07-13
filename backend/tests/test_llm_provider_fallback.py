from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.extraction import extractor
from app.router import llm_fallback
from app.synthesis import groq_client


class ProviderError(Exception):
    def __init__(self, status_code: int | None = None, message: str = "provider error"):
        self.status_code = status_code
        super().__init__(message)


class TimeoutErrorForTest(Exception):
    pass


class ConnectionErrorForTest(Exception):
    pass


def _response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_successful_xai_text_does_not_call_groq(monkeypatch):
    xai = Mock(return_value="xAI answer")
    groq = Mock(return_value="Groq answer")
    monkeypatch.setattr(groq_client, "_call_xai_text", xai)
    monkeypatch.setattr(groq_client, "_call_groq_text", groq)

    assert groq_client.generate_text("system", "user") == "xAI answer"
    groq.assert_not_called()


def test_successful_xai_json_does_not_call_groq(monkeypatch):
    xai = Mock(return_value={"ok": True})
    groq = Mock(return_value={"ok": False})
    monkeypatch.setattr(groq_client, "_call_xai_json", xai)
    monkeypatch.setattr(groq_client, "_call_groq_json", groq)

    assert groq_client.generate_json("system", "user") == {"ok": True}
    groq.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [ProviderError(429), TimeoutErrorForTest(), ConnectionErrorForTest(), ProviderError(500)],
    ids=["http_429", "timeout", "connection", "http_500"],
)
def test_transient_xai_failures_fall_back_to_groq(monkeypatch, error):
    groq = Mock(return_value="fallback answer")
    monkeypatch.setattr(groq_client, "_call_xai_text", Mock(side_effect=error))
    monkeypatch.setattr(groq_client, "_call_groq_text", groq)
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(groq_model="fallback-model"))

    assert groq_client.generate_text("system", "user") == "fallback answer"
    groq.assert_called_once_with("system", "user", 0.1)


@pytest.mark.parametrize("status", [401, 403, 400])
def test_non_transient_xai_http_errors_do_not_fall_back(monkeypatch, status):
    groq = Mock(return_value="fallback answer")
    monkeypatch.setattr(groq_client, "_call_xai_text", Mock(side_effect=ProviderError(status)))
    monkeypatch.setattr(groq_client, "_call_groq_text", groq)

    with pytest.raises(groq_client.LLMUnavailable, match=rf"HTTP {status}"):
        groq_client.generate_text("system", "user")
    groq.assert_not_called()


def test_groq_fallback_text_uses_final_content(monkeypatch):
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=Mock(return_value=_response("<think>private</think>\nFinal answer")))
        )
    )
    monkeypatch.setattr(groq_client, "get_groq_client", lambda: client)
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(groq_model="fallback-model"))

    assert groq_client._call_groq_text("system", "user", 0.1) == "Final answer"


def test_json_output_uses_load_json_content(monkeypatch):
    parsed = {"route": "HYBRID", "confidence": 0.9}
    loader = Mock(return_value=parsed)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=_response('{"ignored": true}'))))
    )
    monkeypatch.setattr(groq_client, "get_xai_client", lambda: client)
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(xai_model="grok-4.5"))
    monkeypatch.setattr(groq_client, "load_json_content", loader)

    assert groq_client._call_xai_json("system", "user", 0.0) == parsed
    loader.assert_called_once_with('{"ignored": true}')


def test_no_think_content_reaches_returned_text(monkeypatch):
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=Mock(return_value=_response("<think>private</think>\nAnswer")))
        )
    )
    monkeypatch.setattr(groq_client, "get_xai_client", lambda: client)
    monkeypatch.setattr(groq_client, "get_settings", lambda: SimpleNamespace(xai_model="grok-4.5"))

    assert groq_client.generate_text("system", "user") == "Answer"


def test_extractor_uses_shared_json_gateway(monkeypatch):
    gateway = Mock(return_value={"entities": [], "relations": []})
    monkeypatch.setattr(extractor, "generate_json", gateway)
    monkeypatch.setattr(extractor, "get_settings", lambda: SimpleNamespace(extraction_char_limit=6000))

    assert extractor._call_llm("manual text", "device") == {"entities": [], "relations": []}
    gateway.assert_called_once()


def test_router_uses_shared_json_gateway(monkeypatch):
    gateway = Mock(return_value={"route": "HYBRID", "confidence": 0.9})
    monkeypatch.setattr(llm_fallback, "generate_json", gateway)

    assert llm_fallback._call("display has no signal") == {"route": "HYBRID", "confidence": 0.9}
    gateway.assert_called_once()


def test_secrets_do_not_appear_in_logs_or_errors(monkeypatch, caplog):
    secret = "xai-secret-value"
    monkeypatch.setattr(groq_client, "_call_xai_text", Mock(side_effect=ProviderError(401, secret)))
    monkeypatch.setattr(groq_client, "_call_groq_text", Mock())

    with pytest.raises(groq_client.LLMUnavailable) as raised:
        groq_client.generate_text("system", "user")

    assert secret not in str(raised.value)
    assert secret not in caplog.text
