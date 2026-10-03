from __future__ import annotations

import json
import io
import time
import urllib.error
from email.message import Message

from t4agent.llm import LLM, chat_completions_url, parse_json_object, retry_after_seconds


class FakeResponse:
    def __init__(
        self,
        content: str = '{"signals": {}}',
        usage: object = None,
    ) -> None:
        self.content = content
        self.usage = usage if usage is not None else {"prompt_tokens": 10, "completion_tokens": 4}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": self.content}}],
            "usage": self.usage,
        }).encode()


def test_house_url_adds_v1() -> None:
    assert chat_completions_url("http://model:8443") == "http://model:8443/v1/chat/completions"
    assert chat_completions_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"


def test_json_parser_recovers_one_unambiguous_object_around_invalid_braces() -> None:
    expected = {"signals": {"x": {"level": 1, "reason": "margin {expanded}"}}}
    encoded = json.dumps(expected)

    assert parse_json_object(encoded) == expected
    assert parse_json_object(f"analysis {{not valid json}}\n{encoded}") == expected
    assert parse_json_object(f"{encoded}\nexplanation {{not json}}") == expected
    assert parse_json_object(f"```json\n{encoded}\n```") == expected


def test_json_parser_rejects_ambiguous_or_non_object_content() -> None:
    assert parse_json_object('{"draft": 1}\n{"signals": {}}') is None
    assert parse_json_object('[{"signals": {}}]') is None
    assert parse_json_object('{"signals": {') is None
    assert parse_json_object("plain text") is None


def test_llm_accepts_unambiguous_json_after_invalid_thinking_braces(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse('thinking {draft note}\n{"signals": {}}'),
    )

    llm = LLM()
    assert llm.chat_json("system", "user") == {"signals": {}}
    assert llm.usage.calls == 1
    assert llm.usage.errors == []


def test_valid_content_survives_malformed_optional_usage(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    responses = iter(
        (
            FakeResponse(usage="not-a-map"),
            FakeResponse(
                usage={
                    "prompt_tokens": "unknown",
                    "completion_tokens": 4,
                    "cost": "NaN",
                }
            ),
        )
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: next(responses))

    first = LLM()
    assert first.chat_json("system", "first") == {"signals": {}}
    assert first.usage.calls == 1
    assert first.usage.prompt_tokens == 0
    assert first.usage.completion_tokens == 0
    assert first.usage.total_cost == 0.0
    assert first.usage.errors == []

    second = LLM()
    assert second.chat_json("system", "second") == {"signals": {}}
    assert second.usage.calls == 1
    assert second.usage.prompt_tokens == 0
    assert second.usage.completion_tokens == 4
    assert second.usage.total_cost == 0.0
    assert second.usage.errors == []


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
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert llm.usage.calls == 1


def test_request_budget_stops_before_network(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_MAX_CALLS", "0")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    llm = LLM()
    assert llm.chat_json("system", "user") is None
    assert llm.usage.calls == 0


def test_default_request_budget_uses_official_slots_but_never_call_26(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.delenv("T4_MODEL_MAX_CALLS", raising=False)
    network_calls = 0

    def successful_response(request, timeout):
        nonlocal network_calls
        network_calls += 1
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", successful_response)
    llm = LLM()
    for _ in range(25):
        assert llm.chat_json("system", "user") == {"signals": {}}
    assert llm.chat_json("system", "user") is None
    assert llm.max_calls == 25
    assert llm.usage.calls == 25
    assert network_calls == 25
    assert llm.usage.circuit_open
    assert llm.usage.disabled_reason == "model request budget exhausted"


def test_openrouter_data_collection_is_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("MODEL_API_KEY", "test-only-token")
    monkeypatch.setenv("MODEL_NAME", "nvidia/nemotron-3-super-120b-a12b:free")
    seen = []

    def fake_urlopen(request, timeout):
        seen.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert LLM().chat_json("system", "user") == {"signals": {}}
    assert seen[-1]["provider"]["data_collection"] == "deny"
    assert seen[-1]["reasoning"] == {"enabled": False}

    monkeypatch.setenv("T4_MODEL_ALLOW_DATA_COLLECTION", "1")
    monkeypatch.setenv("T4_ENABLE_THINKING", "1")
    assert LLM().chat_json("system", "user") == {"signals": {}}
    assert seen[-1]["provider"]["data_collection"] == "allow"
    assert seen[-1]["reasoning"] == {"enabled": True}


def test_expired_deadline_stops_before_network(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    llm = LLM(deadline_monotonic=time.monotonic() - 1)
    assert llm.chat_json("system", "user") is None
    assert llm.usage.calls == 0
    assert llm.usage.circuit_open
    assert llm.usage.disabled_reason == "model phase deadline reached"


def test_authorization_failure_opens_circuit_without_retry(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "bad-token")

    def unauthorized(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"denied"))

    monkeypatch.setattr("urllib.request.urlopen", unauthorized)
    llm = LLM()
    assert llm.chat_json("system", "user") is None
    assert llm.usage.calls == 1
    assert llm.usage.circuit_open
    assert "401" in (llm.usage.disabled_reason or "")


def _http_error(
    request,
    code: int,
    body: bytes,
    headers: dict[str, str] | None = None,
) -> urllib.error.HTTPError:
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError(request.full_url, code, "error", message, io.BytesIO(body))


def test_retry_after_parser_accepts_seconds_and_http_date() -> None:
    assert retry_after_seconds("7") == 7.0
    assert retry_after_seconds("Thu, 01 Jan 1970 00:01:40 GMT", now_epoch=90.0) == 10.0
    assert retry_after_seconds("Thu, 01 Jan 1970 00:01:20 GMT", now_epoch=90.0) == 0.0
    assert retry_after_seconds("1.5") is None
    assert retry_after_seconds("not a date") is None
    assert retry_after_seconds(None) is None


def test_rate_limit_waits_for_retry_after_without_dropping_json_mode(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("MODEL_API_KEY", "test-only-token")
    monkeypatch.setenv("MODEL_NAME", "free-model")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    calls = 0
    bodies = []
    sleeps = []

    def limited_then_success(request, timeout):
        nonlocal calls
        calls += 1
        bodies.append(json.loads(request.data))
        if calls == 1:
            raise _http_error(request, 429, b'{"error":"rate limited"}', {"Retry-After": "3"})
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", limited_then_success)
    monkeypatch.setattr("time.sleep", sleeps.append)
    llm = LLM()
    assert llm.chat_json("system", "user") == {"signals": {}}
    assert calls == 2
    assert sleeps == [3.0]
    assert all(body.get("response_format") == {"type": "json_object"} for body in bodies)
    assert llm.consecutive_failures == 0


def test_rate_limit_longer_than_cap_falls_back_without_early_retry(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    monkeypatch.setenv("T4_MODEL_RETRY_AFTER_CAP_S", "5")
    sleeps = []
    calls = 0

    def long_limit(request, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(request, 429, b'limited', {"Retry-After": "60"})

    monkeypatch.setattr("urllib.request.urlopen", long_limit)
    monkeypatch.setattr("time.sleep", sleeps.append)
    llm = LLM()
    assert llm.chat_json("system", "user") is None
    assert calls == 1
    assert sleeps == []
    assert not llm.usage.circuit_open


def test_rate_limit_delay_must_fit_remaining_deadline(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    sleeps = []
    calls = 0

    def limited(request, timeout):
        nonlocal calls
        calls += 1
        raise _http_error(request, 429, b'limited', {"Retry-After": "5"})

    monkeypatch.setattr("urllib.request.urlopen", limited)
    monkeypatch.setattr("time.sleep", sleeps.append)
    llm = LLM(deadline_monotonic=time.monotonic() + 2.0)
    assert llm.chat_json("system", "user") is None
    assert calls == 1
    assert sleeps == []


def test_context_length_400_falls_back_locally_and_later_batch_recovers(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    monkeypatch.setenv("T4_MODEL_CIRCUIT_FAILURES", "4")
    calls = 0

    def context_then_success(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _http_error(
                request,
                400,
                b'{"error":{"code":"context_length_exceeded","message":"maximum context length exceeded"}}',
            )
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", context_then_success)
    llm = LLM()
    assert llm.chat_json("system", "oversized batch") is None
    assert llm.last_failure_kind == "context_length"
    assert not llm.usage.circuit_open
    assert llm.chat_json("system", "shorter batch") == {"signals": {}}
    assert llm.last_failure_kind is None
    assert calls == 2
    assert llm.consecutive_failures == 0


def test_unknown_http_400_still_opens_circuit(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")

    def invalid_request(request, timeout):
        raise _http_error(request, 400, b'{"error":{"message":"invalid request schema"}}')

    monkeypatch.setattr("urllib.request.urlopen", invalid_request)
    llm = LLM()
    assert llm.chat_json("system", "bad request") is None
    assert llm.last_failure_kind == "other"
    assert llm.usage.calls == 1
    assert llm.usage.circuit_open
    assert llm.usage.disabled_reason == "non-retriable model request HTTP 400"


def test_persistent_context_length_errors_open_shared_circuit(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    monkeypatch.setenv("T4_MODEL_CIRCUIT_FAILURES", "4")

    def context_error(request, timeout):
        raise _http_error(request, 400, b'{"error":{"message":"prompt is too long for context window"}}')

    monkeypatch.setattr("urllib.request.urlopen", context_error)
    llm = LLM()
    for _ in range(3):
        assert llm.chat_json("system", "oversized batch") is None
        assert not llm.usage.circuit_open
    assert llm.chat_json("system", "oversized batch") is None
    assert llm.usage.calls == 4
    assert llm.usage.circuit_open
    assert llm.usage.disabled_reason == "consecutive model failure circuit threshold reached"


def test_restricted_environment_requires_house_credentials(monkeypatch) -> None:
    monkeypatch.setenv("QFBENCH_NETWORK", "restricted")
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL_TOKEN", raising=False)
    llm = LLM()
    assert not llm.enabled
    assert llm.usage.circuit_open
    assert "missing MODEL_NAME or MODEL_TOKEN" in (llm.usage.disabled_reason or "")


def test_one_bad_batch_does_not_disable_later_batches(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    monkeypatch.setenv("T4_MODEL_CIRCUIT_FAILURES", "4")
    responses = iter(("not json", "still not json", '{"signals": {}}'))
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(next(responses)),
    )

    llm = LLM()
    assert llm.chat_json("system", "first batch") is None
    assert not llm.usage.circuit_open
    assert llm.chat_json("system", "second batch") == {"signals": {}}
    assert llm.usage.calls == 3
    assert llm.consecutive_failures == 0


def test_persistent_bad_batches_open_shared_circuit(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ENDPOINT", "http://model:8443")
    monkeypatch.setenv("MODEL_NAME", "house")
    monkeypatch.setenv("MODEL_TOKEN", "test-only-token")
    monkeypatch.setenv("T4_MODEL_RETRIES", "2")
    monkeypatch.setenv("T4_MODEL_CIRCUIT_FAILURES", "4")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse("not json"),
    )

    llm = LLM()
    assert llm.chat_json("system", "first batch") is None
    assert not llm.usage.circuit_open
    assert llm.chat_json("system", "second batch") is None
    assert llm.usage.circuit_open
    assert llm.usage.calls == 4
