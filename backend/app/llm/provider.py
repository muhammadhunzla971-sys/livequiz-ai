import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core import metrics
from app.core.config import get_settings


class LLMError(Exception):
    """Provider call failed (network, HTTP error, or empty response)."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float,
        json_mode: bool = True,
        max_tokens: int = 4096,
    ) -> LLMResult: ...


class OpenAICompatProvider:
    """Talks to any OpenAI-compatible /chat/completions endpoint (Groq, OpenAI, vLLM host...)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        s = get_settings()
        self._base_url = (base_url or s.llm_base_url).rstrip("/")
        self._api_key = api_key if api_key is not None else s.llm_api_key
        self._timeout = timeout or s.llm_timeout_sec
        self._client = client

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float,
        json_mode: bool = True,
        max_tokens: int = 4096,
    ) -> LLMResult:
        if not self._api_key:
            raise LLMError("LLM_API_KEY is not configured")
        body: dict[str, object] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        start = time.perf_counter()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            metrics.inc("livequiz_llm_calls_total", outcome="network_error")
            raise LLMError(f"network error: {type(exc).__name__}") from exc
        finally:
            if owns_client:
                await client.aclose()

        metrics.inc("livequiz_llm_seconds_total", time.perf_counter() - start)
        if resp.status_code >= 400:
            metrics.inc("livequiz_llm_calls_total", outcome="http_error")
            raise LLMError(f"provider returned HTTP {resp.status_code}")
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed provider response") from exc
        if not text or not text.strip():
            raise LLMError("empty completion")
        metrics.inc("livequiz_llm_calls_total", outcome="ok")
        metrics.inc("livequiz_llm_tokens_total", int(usage.get("prompt_tokens", 0)), kind="prompt")
        metrics.inc(
            "livequiz_llm_tokens_total", int(usage.get("completion_tokens", 0)), kind="completion"
        )
        return LLMResult(
            text=text,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


def get_provider() -> LLMProvider:
    return OpenAICompatProvider()
