import io
import json

import pytest

from lazylabel.adapters.outbound.models.gateway import GATEWAY_URL, GatewayTextGenerationBackend


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        return io.BytesIO(json.dumps(self.payload).encode("utf-8"))


def test_sends_openai_style_request_and_returns_content():
    opener = FakeOpener({"choices": [{"message": {"content": " {\"plan\": 1} "}}]})
    backend = GatewayTextGenerationBackend("gateway:anthropic/claude-haiku-4.5", api_key="k", opener=opener)
    assert backend.generate("plan this", max_new_tokens=64) == '{"plan": 1}'
    request = opener.requests[0]
    assert request.full_url == GATEWAY_URL
    assert request.get_header("Authorization") == "Bearer k"
    body = json.loads(request.data)
    assert body["model"] == "anthropic/claude-haiku-4.5" and body["max_tokens"] == 64 and body["temperature"] == 0
    assert backend.model_ref == backend.model_id == "gateway:anthropic/claude-haiku-4.5"
    backend.generate("x", max_new_tokens=8, system="rules")
    assert json.loads(opener.requests[1].data)["messages"][0] == {"role": "system", "content": "rules"}


def test_missing_key_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    opener = FakeOpener({})
    with pytest.raises(RuntimeError, match="AI_GATEWAY_API_KEY"):
        GatewayTextGenerationBackend("gateway:openai/gpt-5", opener=opener).generate("x", max_new_tokens=8)
    assert opener.requests == []


def test_rejects_empty_model_and_malformed_reply():
    with pytest.raises(ValueError):
        GatewayTextGenerationBackend("gateway:")
    backend = GatewayTextGenerationBackend("gateway:a/b", api_key="k", opener=FakeOpener({"choices": []}))
    with pytest.raises(ValueError, match="no message content"):
        backend.generate("x", max_new_tokens=8)
