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


class LLM:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.endpoint = (os.environ.get("MODEL_ENDPOINT") or "").rstrip("/")
        self.model = os.environ.get("MODEL_NAME") or "qwen/qwen-2.5-7b-instruct"
        self.api_key = os.environ.get("MODEL_API_KEY") or self._read_local_key(root_dir) or "unused"
        self.temperature = float(os.environ.get("T4_TEMPERATURE", "0.0"))
        self.seed = int(os.environ.get("T4_SEED", "1234"))
        self.timeout = float(os.environ.get("T4_MODEL_TIMEOUT_S", "90"))
        self.usage = Usage()
        self.enabled = bool(self.endpoint)

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
        if not self.enabled:
            return None
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "seed": self.seed,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        if "openrouter.ai" in self.endpoint:
            body["provider"] = {
                "allow_fallbacks": False,
                "require_parameters": True,
                "data_collection": "deny",
            }
        req = urllib.request.Request(
            self.endpoint + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
                "HTTP-Referer": "https://github.com/Yif-design/Agenthon2026",
                "X-Title": "Agenthon2026 t4-agent",
            },
            method="POST",
        )
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.usage.calls += 1
                usage = payload.get("usage") or {}
                self.usage.prompt_tokens += int(usage.get("prompt_tokens") or 0)
                self.usage.completion_tokens += int(usage.get("completion_tokens") or 0)
                self.usage.total_cost += float(usage.get("cost") or 0.0)
                content = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                return parse_json_object(content)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:240]
                self.usage.errors.append(f"HTTP {exc.code}: {detail}")
                if "response_format" in body and attempt == 0:
                    body.pop("response_format", None)
                    req.data = json.dumps(body).encode("utf-8")
                    continue
            except Exception as exc:  # noqa: BLE001
                self.usage.errors.append(f"{type(exc).__name__}: {str(exc)[:180]}")
            time.sleep(1)
        return None


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
