import json

import httpx
import pytest

from app.core.config import get_settings
from app.llm.prompt_loader import load_prompt
from app.llm.provider import LLMError, OpenAICompatProvider
from app.llm.retry import call_with_fallback, parse_json_loose
from tests.fakes import FakeLLM


def test_parse_json_loose_variants() -> None:
    assert parse_json_loose('{"a": 1}') == {"a": 1}
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Sure! Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        parse_json_loose("not json at all")


def test_prompts_load_and_render() -> None:
    for name in ("plan_v1", "generate_v1", "review_v1", "regenerate_v1", "summary_v1"):
        tpl = load_prompt(name)
        assert tpl.version == name
        assert 0.0 <= tpl.temperature <= 1.0
    system, user = load_prompt("plan_v1").render(
        topic="Space", goal="Planets", level="beginner", count=5, language="en", types="mcq"
    )
    assert "Space" in user and "curriculum designer" in system


def _validate_dict(d: object) -> dict:
    if not isinstance(d, dict) or "ok" not in d:
        raise ValueError("missing 'ok'")
    return d


async def test_repair_after_malformed_json() -> None:
    fake = FakeLLM()
    fake.script["generate"] = ["this is not json", '{"ok": true}']
    value, _ = await call_with_fallback(
        fake, system="s", user="u", temperature=0.5, validate=_validate_dict
    )
    assert value == {"ok": True}
    assert fake.count("generate") == 2


async def test_falls_back_to_secondary_model() -> None:
    s = get_settings()
    fake = FakeLLM()
    fake.fail_models = {s.llm_primary_model}
    fake.script["generate"] = ['{"ok": 1}']
    _, result = await call_with_fallback(
        fake, system="s", user="u", temperature=0.5, validate=_validate_dict
    )
    assert result.model == s.llm_fallback_model


async def test_all_models_failing_raises() -> None:
    s = get_settings()
    fake = FakeLLM()
    fake.fail_models = {s.llm_primary_model, s.llm_fallback_model}
    with pytest.raises(LLMError):
        await call_with_fallback(
            fake, system="s", user="u", temperature=0.5, validate=_validate_dict
        )


async def test_provider_parses_openai_response_and_hides_key() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"x": 1}'}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider(base_url="http://llm.test/v1", api_key="k-123", client=client)
    res = await provider.complete(system="s", user="u", model="m", temperature=0.3)
    assert res.text == '{"x": 1}'
    assert (res.prompt_tokens, res.completion_tokens) == (7, 3)
    assert seen["auth"] == "Bearer k-123"
    assert seen["body"]["response_format"] == {"type": "json_object"}


async def test_provider_errors_are_wrapped() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    provider = OpenAICompatProvider(base_url="http://llm.test/v1", api_key="k", client=client)
    with pytest.raises(LLMError, match="HTTP 500"):
        await provider.complete(system="s", user="u", model="m", temperature=0.3)

    no_key = OpenAICompatProvider(base_url="http://llm.test/v1", api_key="", client=client)
    with pytest.raises(LLMError, match="not configured"):
        await no_key.complete(system="s", user="u", model="m", temperature=0.3)
