from __future__ import annotations

import json

from t4agent.llm import LLM, chat_completions_url


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": '{"signals": {}}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        }).encode()


def test_house_url_adds_v1() -> None:
    assert chat_completions_url("http://model:8443") == "http://model:8443/v1/chat/completions"
    assert chat_completions_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"


def test_house_environment_uses_injected_token(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    llm = LLM()
    assert llm.chat_json("system", "user", max_tokens=9000) == {"signals": {}}
    assert seen["url"] == "http://model:8443/v1/chat/completions"
    assert seen["authorization"] == "Bearer test-only-token"
    assert seen["body"]["model"] == "house"
    assert seen["body"]["max_tokens"] == 4000
    assert "response_format" not in seen["body"]
    assert llm.usage.calls == 1


def test_request_budget_stops_before_network(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_MAX_CALLS", "0")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    llm = LLM()
    assert llm.chat_json("system", "user") is None
    assert llm.usage.calls == 0
