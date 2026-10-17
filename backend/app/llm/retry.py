import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.llm.provider import LLMError, LLMProvider, LLMResult

log = logging.getLogger("livequiz.llm")

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_loose(text: str) -> Any:
    """Parse JSON from an LLM reply, tolerating code fences and leading/trailing prose."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost {...} or [...] block.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(open_ch), cleaned.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no valid JSON found in model output")


async def call_with_fallback(
    provider: LLMProvider,
    *,
    system: str,
    user: str,
    temperature: float,
    validate: Callable[[Any], Any],
    on_attempt: Callable[[LLMResult | None, str, str | None], Awaitable[None]] | None = None,
    max_tokens: int = 4096,
) -> tuple[Any, LLMResult]:
    """Call the primary model (with exponential backoff), then the fallback model.

    `validate` receives the parsed JSON and must return the validated value or raise
    ValueError. On a validation failure the next attempt appends the error to the prompt
    ("repair"), so the model can fix its own output.
    """
    s = get_settings()
    models = [s.llm_primary_model]
    if s.llm_fallback_model and s.llm_fallback_model != s.llm_primary_model:
        models.append(s.llm_fallback_model)

    last_error = "unknown error"
    repair_hint = ""
    for model in models:
        for attempt in range(s.llm_max_retries):
            try:
                result = await provider.complete(
                    system=system,
                    user=user + repair_hint,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMError as exc:
                last_error = str(exc)
                if on_attempt:
                    await on_attempt(None, model, last_error)
                log.warning("llm call failed", extra={"model": model, "attempt": attempt})
                await asyncio.sleep(min(0.5 * 2**attempt, 8.0))
                continue

            try:
                value = validate(parse_json_loose(result.text))
            except ValueError as exc:
                last_error = f"invalid output: {exc}"
                if on_attempt:
                    await on_attempt(result, model, last_error)
                repair_hint = (
                    "\n\nYour previous reply was rejected: "
                    f"{str(exc)[:500]}\nReturn corrected JSON only."
                )
                continue

            if on_attempt:
                await on_attempt(result, model, None)
            return value, result

    raise LLMError(f"all models failed: {last_error}")
