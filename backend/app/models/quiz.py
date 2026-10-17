import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Quiz(Base, IdMixin, TimestampMixin):
    __tablename__ = "quizzes"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    learning_goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    # Per-quiz scoring: {"base_points": 1000, "speed_bonus": true, "streak_step": 0.1, ...}
    scoring_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generation_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="Question.position",
        lazy="selectin",
    )
    tags: Mapped[list["QuizTag"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", lazy="selectin"
    )


class Question(Base, IdMixin, TimestampMixin):
    __tablename__ = "questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("quizzes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # mcq | true_false | multi_select
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSON, nullable=False)  # [{"id":"A","text":"..."}]
    correct_option_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    bloom_level: Mapped[str] = mapped_column(String(20), default="remember", nullable=False)
    subtopic: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    time_limit_sec: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")


class QuizTag(Base, IdMixin):
    __tablename__ = "quiz_tags"
    __table_args__ = (UniqueConstraint("quiz_id", "tag", name="uq_quiz_tags_quiz_id_tag"),)

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("quizzes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tag: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    quiz: Mapped[Quiz] = relationship(back_populates="tags")
