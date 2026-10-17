import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class AIGenerationLog(Base, IdMixin, TimestampMixin):
    """One row per LLM call; never stores raw user prompts (privacy), only metadata."""

    __tablename__ = "ai_generation_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    quiz_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("quizzes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    step: Mapped[str] = mapped_column(String(30), nullable=False)  # plan|generate|review|summary
    prompt_version: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok|retry|failed|cached
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Report(Base, IdMixin, TimestampMixin):
    """Post-game analytics snapshot plus AI summary for one session."""

    __tablename__ = "reports"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ai_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
