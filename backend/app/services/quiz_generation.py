"""AI quiz generation pipeline: normalise -> plan -> generate -> validate -> review -> repair."""

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.llm.prompt_loader import PromptTemplate, load_prompt
from app.llm.provider import LLMProvider, LLMResult
from app.llm.retry import call_with_fallback
from app.models import AIGenerationLog
from app.schemas.quiz import GeneratedQuestion, GenerateRequest
from app.services.moderation import check_input, check_question, sanitize_input

log = logging.getLogger("livequiz.generation")

Progress = Callable[[dict[str, Any]], Awaitable[None]]
BATCH_SIZE = 8
MAX_FILL_ATTEMPTS = 3
CACHE_VERSION = "v1"


async def _noop(_: dict[str, Any]) -> None:
    return None


class PlanSubtopic(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    questions: int = Field(default=1, ge=0, le=30)


class Plan(BaseModel):
    subtopics: list[PlanSubtopic] = Field(default_factory=list)
    bloom_distribution: dict[str, int] = Field(default_factory=dict)


@dataclass
class GenerationResult:
    questions: list[dict[str, Any]]
    cached: bool = False
    plan: dict[str, Any] = field(default_factory=dict)


def generation_hash(req: GenerateRequest, topic: str, goal: str) -> str:
    payload = json.dumps(
        {
            "v": CACHE_VERSION,
            "topic": topic.lower(),
            "level": req.level,
            "goal": goal.lower(),
            "count": req.num_questions,
            "language": req.language,
            "types": req.question_types,
            "time": req.time_limit_sec,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _error_summary(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])


def _questions_validator(
    expected: int, allowed: set[str]
) -> Callable[[Any], list[GeneratedQuestion]]:
    def validate(data: Any) -> list[GeneratedQuestion]:
        items = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError('expected {"questions": [...]}')
        good: list[GeneratedQuestion] = []
        errors: list[str] = []
        for i, raw in enumerate(items):
            try:
                q = GeneratedQuestion.model_validate(raw)
                if q.type not in allowed:
                    raise ValueError(f"type '{q.type}' is not allowed")
                if not check_question(q):
                    raise ValueError("unsafe content")
                good.append(q)
            except ValidationError as exc:
                errors.append(f"question {i}: {_error_summary(exc)}")
            except ValueError as exc:
                errors.append(f"question {i}: {exc}")
        if len(good) < expected:
            raise ValueError(f"need {expected} valid questions, got {len(good)}. {errors[:4]}")
        return good[:expected]

    return validate


class QuizGenerator:
    def __init__(
        self,
        provider: LLMProvider,
        redis: Redis,
        db: AsyncSession,
        user_id: uuid.UUID | None,
    ) -> None:
        self._provider = provider
        self._redis = redis
        self._db = db
        self._user_id = user_id
        self._logs: list[AIGenerationLog] = []

    # -- logging -----------------------------------------------------------------------------
    def _recorder(
        self, step: str, tpl: PromptTemplate
    ) -> Callable[[LLMResult | None, str, str | None], Awaitable[None]]:
        async def record(result: LLMResult | None, model: str, error: str | None) -> None:
            self._logs.append(
                AIGenerationLog(
                    user_id=self._user_id,
                    step=step,
                    prompt_version=tpl.version,
                    model=model,
                    prompt_tokens=result.prompt_tokens if result else 0,
                    completion_tokens=result.completion_tokens if result else 0,
                    latency_ms=result.latency_ms if result else 0,
                    status="ok" if error is None else "retry",
                    error=error,
                )
            )

        return record

    async def _flush_logs(self) -> None:
        if self._logs:
            self._db.add_all(self._logs)
            await self._db.commit()
            self._logs = []

    # -- steps -------------------------------------------------------------------------------
    async def _plan(self, base: dict[str, Any]) -> Plan:
        tpl = load_prompt("plan_v1")
        system, user = tpl.render(**base)
        try:
            plan, _ = await call_with_fallback(
                self._provider,
                system=system,
                user=user,
                temperature=tpl.temperature,
                validate=lambda d: Plan.model_validate(d),
                on_attempt=self._recorder("plan", tpl),
                max_tokens=1024,
            )
            return plan  # type: ignore[no-any-return]
        except Exception as exc:  # planning is an enhancement; never block generation on it
            log.warning("planning failed, continuing without a plan: %s", exc)
            return Plan()

    async def _generate_batch(
        self,
        base: dict[str, Any],
        plan: Plan,
        start: int,
        count: int,
        total: int,
        previous: list[str],
        allowed: set[str],
    ) -> list[GeneratedQuestion]:
        tpl = load_prompt("generate_v1")
        plan_text = (
            f"{plan.model_dump_json()}\nWrite questions {start + 1} to {start + count} of {total}."
        )
        if previous:
            plan_text += "\nDo NOT repeat or paraphrase these existing questions:\n" + "\n".join(
                f"- {t}" for t in previous[-30:]
            )
        system, user = tpl.render(**{**base, "count": count, "plan": plan_text})
        questions, _ = await call_with_fallback(
            self._provider,
            system=system,
            user=user,
            temperature=tpl.temperature,
            validate=_questions_validator(count, allowed),
            on_attempt=self._recorder("generate", tpl),
        )
        return questions  # type: ignore[no-any-return]

    async def _review(self, base: dict[str, Any], questions: list[GeneratedQuestion]) -> list[int]:
        """Return indexes of questions the critic flags. Review failure is non-fatal."""
        tpl = load_prompt("review_v1")
        payload = json.dumps(
            [
                {
                    "index": i,
                    "text": q.text,
                    "options": [o.model_dump() for o in q.options],
                    "correct": q.correct_option_ids,
                }
                for i, q in enumerate(questions)
            ],
            ensure_ascii=False,
        )
        system, user = tpl.render(topic=base["topic"], goal=base["goal"], questions=payload)

        def validate(d: Any) -> list[int]:
            issues = d.get("issues") if isinstance(d, dict) else None
            if not isinstance(issues, list):
                raise ValueError('expected {"issues": [...]}')
            return sorted(
                {
                    int(i["index"])
                    for i in issues
                    if isinstance(i, dict)
                    and isinstance(i.get("index"), int)
                    and 0 <= i["index"] < len(questions)
                }
            )

        try:
            flagged, _ = await call_with_fallback(
                self._provider,
                system=system,
                user=user,
                temperature=tpl.temperature,
                validate=validate,
                on_attempt=self._recorder("review", tpl),
                max_tokens=1024,
            )
            return flagged  # type: ignore[no-any-return]
        except Exception as exc:
            log.warning("review step failed, skipping: %s", exc)
            return []

    async def regenerate_one(
        self,
        base: dict[str, Any],
        qtype: str,
        subtopic: str,
        existing: list[str],
        feedback: str = "",
    ) -> GeneratedQuestion:
        tpl = load_prompt("regenerate_v1")
        fb = f"Teacher feedback to respect: {sanitize_input(feedback, 300)}" if feedback else ""
        system, user = tpl.render(
            topic=base["topic"],
            goal=base["goal"],
            level=base["level"],
            language=base["language"],
            qtype=qtype,
            subtopic=subtopic or "general",
            feedback=fb,
            existing="\n".join(f"- {t}" for t in existing[-30:]) or "(none)",
        )
        questions, _ = await call_with_fallback(
            self._provider,
            system=system,
            user=user,
            temperature=tpl.temperature,
            validate=_questions_validator(1, {qtype}),
            on_attempt=self._recorder("generate", tpl),
            max_tokens=1024,
        )
        return questions[0]  # type: ignore[no-any-return]

    # -- public ------------------------------------------------------------------------------
    async def generate(self, req: GenerateRequest, progress: Progress = _noop) -> GenerationResult:
        s = get_settings()
        topic = sanitize_input(req.topic, 300)
        goal = sanitize_input(req.learning_goal, 1000)
        if len(topic) < 2:
            raise ValueError("topic is empty after sanitisation")
        check_input(topic, goal)

        cache_key = f"gen:{generation_hash(req, topic, goal)}"
        if not req.force_regenerate:
            cached = await self._redis.get(cache_key)
            if cached:
                await progress({"stage": "cached", "message": "Loaded from cache"})
                return GenerationResult(questions=json.loads(cached), cached=True)

        base: dict[str, Any] = {
            "topic": topic,
            "goal": goal or "(none given)",
            "level": req.level,
            "count": req.num_questions,
            "language": req.language,
            "types": ", ".join(req.question_types),
            "time_limit": req.time_limit_sec,
        }
        allowed: set[str] = set(req.question_types)

        try:
            await progress({"stage": "planning", "message": "Planning the quiz"})
            plan = await self._plan(base)

            questions: list[GeneratedQuestion] = []
            seen: set[str] = set()
            while len(questions) < req.num_questions:
                start = len(questions)
                count = min(BATCH_SIZE, req.num_questions - start)
                await progress(
                    {
                        "stage": "generating",
                        "message": f"Generating Q{start + 1}-{start + count}/{req.num_questions}",
                        "done": start,
                        "total": req.num_questions,
                    }
                )
                batch = await self._generate_batch(
                    base,
                    plan,
                    start,
                    count,
                    req.num_questions,
                    [q.text for q in questions],
                    allowed,
                )
                for q in batch:
                    if _norm(q.text) not in seen:
                        seen.add(_norm(q.text))
                        questions.append(q)
                if len(questions) == start:  # whole batch was duplicates; avoid looping forever
                    break

            await progress({"stage": "validating", "message": "Checking quality"})
            flagged = await self._review(base, questions)
            for idx in flagged:
                try:
                    questions[idx] = await self.regenerate_one(
                        base,
                        questions[idx].type,
                        questions[idx].subtopic,
                        [q.text for i, q in enumerate(questions) if i != idx],
                    )
                except Exception as exc:
                    log.warning("could not repair flagged question %s: %s", idx, exc)

            fills = 0
            while len(questions) < req.num_questions and fills < MAX_FILL_ATTEMPTS:
                fills += 1
                try:
                    q = await self.regenerate_one(
                        base, req.question_types[0], "", [x.text for x in questions]
                    )
                except Exception as exc:
                    log.warning("fill attempt failed: %s", exc)
                    continue
                if _norm(q.text) not in seen:
                    seen.add(_norm(q.text))
                    questions.append(q)
            if len(questions) < 1:
                raise ValueError("model did not produce any valid questions")
        finally:
            await self._flush_logs()

        out = [
            {
                **q.model_dump(),
                "id": str(uuid.uuid4()),
                "time_limit_sec": req.time_limit_sec,
                "points": 1000,
            }
            for q in questions[: req.num_questions]
        ]
        await self._redis.set(cache_key, json.dumps(out), ex=s.generation_cache_ttl_sec)
        await progress(
            {"stage": "done", "message": "Quiz ready", "done": len(out), "total": len(out)}
        )
        return GenerationResult(questions=out, plan=plan.model_dump())

    async def flush(self) -> None:
        await self._flush_logs()
