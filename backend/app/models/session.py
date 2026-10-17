import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class GameSession(Base, IdMixin, TimestampMixin):
    """A live run of a quiz."""

    __tablename__ = "sessions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("quizzes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    pin: Mapped[str] = mapped_column(String(6), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="created", index=True, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionPlayer(Base, IdMixin, TimestampMixin):
    __tablename__ = "session_players"
    __table_args__ = (
        UniqueConstraint("session_id", "nickname", name="uq_session_players_session_id_nickname"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    nickname: Mapped[str] = mapped_column(String(30), nullable=False)
    avatar: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    final_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Answer(Base, IdMixin):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "player_id", "question_id", name="uq_answers_session_player_question"
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("session_players.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Question ids are snapshotted from the quiz; no FK so editing/deleting a quiz keeps history.
    question_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    chosen_option_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    response_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
