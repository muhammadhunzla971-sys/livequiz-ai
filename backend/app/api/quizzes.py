import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.rate_limit import enforce
from app.db.session import get_sessionmaker
from app.llm.provider import LLMError, LLMProvider, get_provider
from app.models import Question, Quiz, QuizTag, User
from app.schemas.quiz import (
    DEFAULT_SCORING_CONFIG,
    GenerateRequest,
    QuestionIn,
    QuestionOut,
    QuizCreate,
    QuizOut,
    QuizSummary,
    QuizUpdate,
    RegenerateQuestionRequest,
)
from app.services.moderation import UnsafeContentError, sanitize_input
from app.services.quiz_csv import parse_quiz_csv, questions_to_csv
from app.services.quiz_generation import QuizGenerator, generation_hash

log = logging.getLogger("livequiz.quizzes")
router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


def get_llm() -> LLMProvider:
    return get_provider()


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


LLM = Annotated[LLMProvider, Depends(get_llm)]
RedisDep = Annotated[Redis, Depends(get_redis)]


# -- helpers ---------------------------------------------------------------------------------
def to_out(quiz: Quiz) -> QuizOut:
    return QuizOut(
        id=quiz.id,
        title=quiz.title,
        topic=quiz.topic,
        level=quiz.level,  # type: ignore[arg-type]
        learning_goal=quiz.learning_goal,
        language=quiz.language,
        scoring_config=quiz.scoring_config,
        status=quiz.status,
        tags=sorted(t.tag for t in quiz.tags),
        questions=[QuestionOut.model_validate(q) for q in quiz.questions],
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
    )


def _clean_tags(tags: list[str]) -> list[str]:
    return sorted({t.strip().lower()[:50] for t in tags if t.strip()})


async def get_owned_quiz(db: AsyncSession, quiz_id: uuid.UUID, user: User) -> Quiz:
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None or quiz.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found")
    return quiz


def _fill_question(q: Question, data: QuestionIn, position: int) -> None:
    q.position = position
    q.type = data.type
    q.text = data.text
    q.options = [o.model_dump() for o in data.options]
    q.correct_option_ids = list(data.correct_option_ids)
    q.explanation = data.explanation
    q.difficulty = data.difficulty
    q.bloom_level = data.bloom_level
    q.subtopic = data.subtopic
    q.time_limit_sec = data.time_limit_sec
    q.points = data.points


def _replace_questions(quiz: Quiz, items: list[QuestionIn]) -> None:
    existing = {q.id: q for q in quiz.questions}
    new_list: list[Question] = []
    for pos, item in enumerate(items):
        q = existing.get(item.id) if item.id else None
        if q is None:
            q = Question()
        _fill_question(q, item, pos)
        new_list.append(q)
    quiz.questions = new_list  # removed ones are deleted via delete-orphan


def _question_dicts_to_in(items: list[dict[str, Any]]) -> list[QuestionIn]:
    return [QuestionIn.model_validate({**d, "id": None}) for d in items]


# -- CRUD ------------------------------------------------------------------------------------
@router.get("", response_model=list[QuizSummary])
async def list_quizzes(
    db: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    tag: Annotated[str | None, Query(max_length=50)] = None,
    quiz_status: Annotated[str | None, Query(alias="status", pattern="^(draft|published)$")] = None,
) -> list[QuizSummary]:
    stmt = select(Quiz).where(Quiz.owner_id == user.id).order_by(Quiz.updated_at.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Quiz.title.ilike(like), Quiz.topic.ilike(like)))
    if tag:
        stmt = stmt.where(Quiz.tags.any(QuizTag.tag == tag.strip().lower()))
    if quiz_status:
        stmt = stmt.where(Quiz.status == quiz_status)
    rows = (await db.scalars(stmt)).all()
    return [
        QuizSummary(
            id=r.id,
            title=r.title,
            topic=r.topic,
            level=r.level,
            status=r.status,
            language=r.language,
            question_count=len(r.questions),
            tags=sorted(t.tag for t in r.tags),
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def create_quiz(body: QuizCreate, db: DbSession, user: CurrentUser) -> QuizOut:
    quiz = Quiz(
        owner_id=user.id,
        title=body.title.strip(),
        topic=body.topic.strip(),
        level=body.level,
        learning_goal=body.learning_goal,
        language=body.language,
        scoring_config={**DEFAULT_SCORING_CONFIG, **body.scoring_config},
    )
    _replace_questions(quiz, body.questions)
    quiz.tags = [QuizTag(tag=t) for t in _clean_tags(body.tags)]
    db.add(quiz)
    await db.commit()
    return to_out(quiz)


class QuizImport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(default="", max_length=300)
    language: str = Field(default="en", min_length=2, max_length=10)
    csv: str = Field(min_length=1, max_length=500_000)


@router.post("/import", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def import_quiz(body: QuizImport, db: DbSession, user: CurrentUser) -> QuizOut:
    """Create a draft quiz from CSV text. All-or-nothing: any bad row rejects the whole file."""
    questions, errors = parse_quiz_csv(body.csv)
    if errors:
        raise HTTPException(422, errors[:20])
    quiz = Quiz(
        owner_id=user.id,
        title=body.title.strip(),
        topic=(body.topic or body.title).strip(),
        level="beginner",
        language=body.language,
        scoring_config=dict(DEFAULT_SCORING_CONFIG),
    )
    _replace_questions(quiz, questions)
    quiz.tags = []
    db.add(quiz)
    await db.commit()
    return to_out(quiz)


@router.get("/{quiz_id}/export.csv")
async def export_quiz_csv(quiz_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    quiz = await get_owned_quiz(db, quiz_id, user)
    return Response(
        questions_to_csv(list(quiz.questions)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="quiz-{quiz.id}.csv"'},
    )


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(quiz_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuizOut:
    return to_out(await get_owned_quiz(db, quiz_id, user))


@router.patch("/{quiz_id}", response_model=QuizOut)
async def update_quiz(
    quiz_id: uuid.UUID, body: QuizUpdate, db: DbSession, user: CurrentUser
) -> QuizOut:
    quiz = await get_owned_quiz(db, quiz_id, user)
    data = body.model_dump(exclude_unset=True, exclude={"questions", "tags"})
    for field, value in data.items():
        if value is not None:
            setattr(quiz, field, value)
    if body.scoring_config is not None:
        quiz.scoring_config = {**DEFAULT_SCORING_CONFIG, **body.scoring_config}
    if body.tags is not None:
        quiz.tags = [QuizTag(tag=t) for t in _clean_tags(body.tags)]
    if body.questions is not None:
        _replace_questions(quiz, body.questions)
    if quiz.status == "published" and not quiz.questions:
        raise HTTPException(422, "Cannot publish an empty quiz")
    await db.commit()
    await db.refresh(quiz)
    return to_out(quiz)


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(quiz_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    quiz = await get_owned_quiz(db, quiz_id, user)
    await db.delete(quiz)
    await db.commit()


@router.post("/{quiz_id}/duplicate", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def duplicate_quiz(quiz_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuizOut:
    src = await get_owned_quiz(db, quiz_id, user)
    copy = Quiz(
        owner_id=user.id,
        title=f"{src.title} (copy)"[:200],
        topic=src.topic,
        level=src.level,
        learning_goal=src.learning_goal,
        language=src.language,
        scoring_config=dict(src.scoring_config),
        status="draft",
    )
    copy.questions = [
        Question(
            position=q.position,
            type=q.type,
            text=q.text,
            options=list(q.options),
            correct_option_ids=list(q.correct_option_ids),
            explanation=q.explanation,
            difficulty=q.difficulty,
            bloom_level=q.bloom_level,
            subtopic=q.subtopic,
            time_limit_sec=q.time_limit_sec,
            points=q.points,
        )
        for q in src.questions
    ]
    copy.tags = [QuizTag(tag=t.tag) for t in src.tags]
    db.add(copy)
    await db.commit()
    return to_out(copy)


# -- AI generation ---------------------------------------------------------------------------
def _map_generation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, UnsafeContentError):
        return HTTPException(422, str(exc))
    if isinstance(exc, LLMError):
        log.error("llm unavailable: %s", exc)
        return HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI generation is unavailable right now. You can create the quiz manually instead.",
        )
    return HTTPException(422, str(exc))


async def _generate_and_save(
    *,
    db: AsyncSession,
    redis: Redis,
    provider: LLMProvider,
    user: User,
    req: GenerateRequest,
    progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> QuizOut:
    gen = QuizGenerator(provider, redis, db, user.id)
    result = await gen.generate(req, progress) if progress else await gen.generate(req)
    topic = sanitize_input(req.topic, 300)
    quiz = Quiz(
        owner_id=user.id,
        title=topic[:200],
        topic=topic,
        level=req.level,
        learning_goal=sanitize_input(req.learning_goal, 1000),
        language=req.language,
        scoring_config=dict(DEFAULT_SCORING_CONFIG),
        generation_hash=generation_hash(req, topic, sanitize_input(req.learning_goal, 1000)),
    )
    _replace_questions(quiz, _question_dicts_to_in(result.questions))
    quiz.tags = []  # initialise so serialising after commit doesn't lazy-load
    db.add(quiz)
    await db.commit()
    return to_out(quiz)


@router.post("/generate", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def generate_quiz(
    body: GenerateRequest,
    db: DbSession,
    user: CurrentUser,
    redis: RedisDep,
    provider: LLM,
) -> QuizOut:
    s = get_settings()
    await enforce(redis, f"gen:{user.id}", s.generation_rate_per_hour, 3600)
    try:
        return await _generate_and_save(db=db, redis=redis, provider=provider, user=user, req=body)
    except (UnsafeContentError, LLMError, ValueError) as exc:
        raise _map_generation_error(exc) from exc


@router.post("/generate/stream")
async def generate_quiz_stream(
    body: GenerateRequest,
    user: CurrentUser,
    redis: RedisDep,
    provider: LLM,
) -> StreamingResponse:
    """Server-Sent Events: `progress` events, then one `done` (the quiz) or `error` event.

    Use fetch() with an Authorization header and read the stream (EventSource can't set headers).
    """
    s = get_settings()
    await enforce(redis, f"gen:{user.id}", s.generation_rate_per_hour, 3600)
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def progress(event: dict[str, Any]) -> None:
        await queue.put(("progress", event))

    async def runner() -> None:
        # Own DB session: the request-scoped one may be closed before the stream finishes.
        try:
            async with get_sessionmaker()() as db:
                quiz = await _generate_and_save(
                    db=db,
                    redis=redis,
                    provider=provider,
                    user=user,
                    req=body,
                    progress=progress,
                )
            await queue.put(("done", json.loads(quiz.model_dump_json())))
        except Exception as exc:
            http_exc = _map_generation_error(exc)
            await queue.put(("error", {"status": http_exc.status_code, "detail": http_exc.detail}))

    task = asyncio.create_task(runner())

    async def event_stream() -> AsyncIterator[str]:
        try:
            while True:
                kind, data = await queue.get()
                yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"
                if kind in ("done", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{quiz_id}/questions/{question_id}/regenerate", response_model=QuizOut)
async def regenerate_question(
    quiz_id: uuid.UUID,
    question_id: uuid.UUID,
    body: RegenerateQuestionRequest,
    db: DbSession,
    user: CurrentUser,
    redis: RedisDep,
    provider: LLM,
) -> QuizOut:
    s = get_settings()
    quiz = await get_owned_quiz(db, quiz_id, user)
    target = next((q for q in quiz.questions if q.id == question_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    await enforce(redis, f"gen:{user.id}", s.generation_rate_per_hour, 3600)

    base = {
        "topic": quiz.topic,
        "goal": quiz.learning_goal or "(none given)",
        "level": quiz.level,
        "language": quiz.language,
    }
    gen = QuizGenerator(provider, redis, db, user.id)
    try:
        new_q = await gen.regenerate_one(
            base,
            target.type,
            target.subtopic,
            [q.text for q in quiz.questions if q.id != question_id],
            body.feedback,
        )
    except (LLMError, ValueError) as exc:
        raise _map_generation_error(exc) from exc
    finally:
        await gen.flush()

    keep = {"time_limit_sec": target.time_limit_sec, "points": target.points}
    _fill_question(
        target, QuestionIn.model_validate({**new_q.model_dump(), **keep}), target.position
    )
    await db.commit()
    await db.refresh(quiz)
    return to_out(quiz)
