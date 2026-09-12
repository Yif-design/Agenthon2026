"""Minimal OpenAI-compatible chat client (stdlib only, so the image stays small).

Contract with the competition sandbox:
* endpoint and model come from the environment — `MODEL_ENDPOINT` (e.g. http://model:8000/v1)
  and `MODEL_NAME`; never hardcode a host;
* `HTTP_PROXY`/`HTTPS_PROXY` are honoured automatically by urllib;
* no vendor-side tools are ever requested (no `tools`, no `web_search`);
* temperature and seed are pinned for reproducibility;
* every call is logged with its token usage so the per-unit budget can be enforced.

Locally, point it at Ollama: MODEL_ENDPOINT=http://localhost:11434/v1 MODEL_NAME=qwen2.5:7b
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class LLM:
    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        seed: int = 0,
        timeout: float = 120.0,
        max_prompt_tokens: int = 900_000,      # stay under the 1M input budget per unit
        max_completion_tokens: int = 90_000,   # stay under the 100k output budget per unit
    ):
        self.endpoint = (endpoint or os.environ.get("MODEL_ENDPOINT") or "http://localhost:11434/v1").rstrip("/")
        self.model = model or os.environ.get("MODEL_NAME") or "qwen2.5:7b"
        self.api_key = api_key or os.environ.get("MODEL_API_KEY") or os.environ.get("OPENAI_API_KEY") or "none"
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout
        self.max_prompt_tokens = max_prompt_tokens
        self.max_completion_tokens = max_completion_tokens
        self.usage = Usage()
        self.dead = False   # set after a connection-level failure: stop wasting the time budget

    # ---------------------------------------------------------------------------------------
    def budget_left(self) -> bool:
        return (
            self.usage.prompt_tokens < self.max_prompt_tokens
            and self.usage.completion_tokens < self.max_completion_tokens
        )

    def chat(self, system: str, user: str, max_tokens: int = 1200, json_mode: bool = True, retries: int = 2) -> str:
        """One chat completion; returns the assistant text ('' on failure — never raises)."""
        if self.dead:
            return ""
        if not self.budget_left():
            self.usage.errors.append("token budget exhausted; call skipped")
            return ""
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint + "/chat/completions",
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.usage.seconds += time.time() - t0
                self.usage.calls += 1
                u = payload.get("usage") or {}
                self.usage.prompt_tokens += int(u.get("prompt_tokens", 0) or 0)
                self.usage.completion_tokens += int(u.get("completion_tokens", 0) or 0)
                return (payload["choices"][0]["message"].get("content") or "").strip()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                self.usage.errors.append(f"HTTP {exc.code}: {detail}")
                # some servers reject response_format — retry once without it
                if json_mode and attempt == 0 and exc.code in (400, 422):
                    body.pop("response_format", None)
                    req.data = json.dumps(body).encode("utf-8")
                    continue
            except urllib.error.URLError as exc:
                self.usage.seconds += time.time() - t0
                reason = str(exc.reason)
                if "timed out" in reason.lower():          # slow, not dead: retry
                    self.usage.errors.append(f"timeout after {self.timeout}s")
                else:                                       # unreachable: give up for this unit
                    self.usage.errors.append(f"endpoint unreachable ({self.endpoint}): {reason[:120]}")
                    self.dead = True
                    return ""
            except Exception as exc:  # noqa: BLE001 — timeout / parse
                self.usage.seconds += time.time() - t0
                self.usage.errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            time.sleep(1.0 + attempt)
        return ""


def parse_json(text: str) -> dict | None:
    """Tolerant JSON extraction: strips code fences and trailing chatter."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        out = json.loads(t[start:end + 1])
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None
