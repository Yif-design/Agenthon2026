from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0
    errors: list[str] = field(default_factory=list)
    circuit_open: bool = False
    disabled_reason: str | None = None


class LLM:
    def __init__(
        self,
        root_dir: Path | None = None,
        *,
        enabled: bool | None = None,
        deadline_monotonic: float | None = None,
    ) -> None:
        self.endpoint = (os.environ.get("MODEL_ENDPOINT") or "").rstrip("/")
        self.network_mode = (os.environ.get("QFBENCH_NETWORK") or "").lower()
        self.official_mode = self.network_mode == "restricted" or bool(os.environ.get("MODEL_TOKEN"))
        self.model = os.environ.get("MODEL_NAME") or (
            "" if self.official_mode else "qwen/qwen-2.5-7b-instruct"
        )
        self.model_token = os.environ.get("MODEL_TOKEN") or ""
        self.api_key = self.model_token or os.environ.get("MODEL_API_KEY") or self._read_local_key(root_dir) or "unused"
        self.temperature = float(os.environ.get("T4_TEMPERATURE", "0.0"))
        self.seed = int(os.environ.get("T4_SEED", "1234"))
        self.timeout = max(1.0, float(os.environ.get("T4_MODEL_TIMEOUT_S", "40")))
        self.max_calls = min(25, max(0, int(os.environ.get("T4_MODEL_MAX_CALLS", "18"))))
        self.max_retries = max(1, int(os.environ.get("T4_MODEL_RETRIES", "2")))
        self.deadline_monotonic = deadline_monotonic
        self.consecutive_failures = 0
        self.usage = Usage()
        self.enabled = bool(self.endpoint) if enabled is None else bool(enabled and self.endpoint)
        if self.official_mode and self.enabled and (not self.model or not self.model_token):
            self._open_circuit("official House environment is missing MODEL_NAME or MODEL_TOKEN")
        elif not self.enabled:
            self.usage.disabled_reason = "model disabled or MODEL_ENDPOINT absent"

    def _read_local_key(self, root_dir: Path | None) -> str | None:
        explicit = os.environ.get("MODEL_API_KEY_FILE")
        paths = []
        if explicit:
            paths.append(Path(explicit))
        if root_dir is not None:
            paths.append(root_dir / ".secrets" / "openrouter_api_key.txt")
        for path in paths:
            try:
                if path.exists():
                    return path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
        return None

    def chat_json(self, system: str, user: str, max_tokens: int = 700) -> dict | None:
        if not self._can_call():
            return None
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": min(4000, max(1, int(max_tokens))),
            "seed": self.seed,
            "stream": False,
        }
        if self.official_mode:
            # This agent extracts bounded JSON facts. Long model reasoning adds
            # latency and makes the structured response less reliable.
            body["chat_template_kwargs"] = {"enable_thinking": False}
        elif "openrouter.ai" in self.endpoint:
            body["response_format"] = {"type": "json_object"}
            body["provider"] = {
                "allow_fallbacks": False,
                "require_parameters": True,
                "data_collection": "deny",
            }
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key,
        }
        if "openrouter.ai" in self.endpoint:
            headers.update({
                "HTTP-Referer": "https://github.com/Yif-design/Agenthon2026",
                "X-Title": "Agenthon2026 t4-agent",
            })
        for attempt in range(self.max_retries):
            if not self._can_call():
                return None
            timeout = self._request_timeout()
            if timeout <= 0:
                self._open_circuit("model phase deadline reached")
                return None
            req = urllib.request.Request(
                chat_completions_url(self.endpoint),
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            # Count attempts conservatively. The House route charges an admitted
            # request before forwarding, so an upstream failure may still consume it.
            self.usage.calls += 1
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                usage = payload.get("usage") or {}
                self.usage.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.usage.completion_tokens += int(usage.get("completion_tokens") or 0)
                self.usage.total_cost += float(usage.get("cost") or 0.0)
                content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                parsed = parse_json_object(content)
                if parsed is None:
                    self._record_failure("model returned content without one JSON object")
                    if attempt + 1 < self.max_retries:
                        continue
                    break
                self.consecutive_failures = 0
                return parsed
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:240]
                self._record_failure(f"HTTP {exc.code}: {detail}")
                if exc.code in (401, 403):
                    self._open_circuit(f"House authorization/route refused with HTTP {exc.code}")
                    return None
                if 400 <= exc.code < 500 and exc.code != 429:
                    self._open_circuit(f"non-retriable model request HTTP {exc.code}")
                    return None
                if "response_format" in body and attempt + 1 < self.max_retries:
                    body.pop("response_format", None)
                    continue
            except Exception as exc:  # noqa: BLE001
                self._record_failure(f"{type(exc).__name__}: {str(exc)[:180]}")
            if attempt + 1 < self.max_retries and self._remaining_seconds() > 1.0:
                time.sleep(min(1.0, max(0.0, self._remaining_seconds())))
        if self.consecutive_failures >= self.max_retries:
            self._open_circuit("consecutive model failures reached retry limit")
        return None

    def _can_call(self) -> bool:
        if not self.enabled or self.usage.circuit_open:
            return False
        if self.usage.calls >= self.max_calls:
            self._open_circuit("model request budget exhausted")
            return False
        if self._remaining_seconds() <= 0:
            self._open_circuit("model phase deadline reached")
            return False
        return True

    def _remaining_seconds(self) -> float:
        if self.deadline_monotonic is None:
            return float("inf")
        return self.deadline_monotonic - time.monotonic()

    def _request_timeout(self) -> float:
        return max(0.0, min(self.timeout, self._remaining_seconds()))

    def _record_failure(self, message: str) -> None:
        self.consecutive_failures += 1
        self.usage.errors.append(message)

    def _open_circuit(self, reason: str) -> None:
        self.enabled = False
        self.usage.circuit_open = True
        self.usage.disabled_reason = reason
        if not self.usage.errors or self.usage.errors[-1] != reason:
            self.usage.errors.append(reason)


def chat_completions_url(model_endpoint: str) -> str:
    """Resolve both the injected House origin and local ``.../v1`` endpoints."""
    base = model_endpoint.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/chat/completions"


def parse_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
