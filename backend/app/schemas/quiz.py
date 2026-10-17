import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QuestionType = Literal["mcq", "true_false", "multi_select"]
BloomLevel = Literal["remember", "understand", "apply", "analyze"]
Level = Literal["beginner", "intermediate", "advanced"]

LAZY_OPTIONS = ("all of the above", "none of the above", "both a and b", "all of these")
OPTION_IDS = "ABCDE"
DEFAULT_TYPES: list[QuestionType] = ["mcq", "true_false"]

DEFAULT_SCORING_CONFIG: dict[str, float | int | bool] = {
    "base_points": 1000,
    "speed_bonus": True,
    "streak_step": 0.1,
    "streak_cap": 0.5,
}


class Option(BaseModel):
    id: str = Field(min_length=1, max_length=2)
    text: str = Field(min_length=1, max_length=200)


class QuestionBase(BaseModel):
    type: QuestionType
    text: str = Field(min_length=5, max_length=500)
    options: list[Option] = Field(min_length=2, max_length=5)
    correct_option_ids: list[str] = Field(min_length=1)
    explanation: str = Field(default="", max_length=600)
    difficulty: int = Field(default=1, ge=1, le=5)
    bloom_level: BloomLevel = "remember"
    subtopic: str = Field(default="", max_length=200)
    time_limit_sec: int = Field(default=20, ge=5, le=120)
    points: int = Field(default=1000, ge=0, le=10000)

    @field_validator("text", "explanation", "subtopic")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _check_structure(self) -> Self:
        ids = [o.id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("option ids must be unique")
        texts = [o.text.strip().lower() for o in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError("duplicate option text")
        for t in texts:
            if any(lazy in t for lazy in LAZY_OPTIONS):
                raise ValueError("'all/none of the above' style options are not allowed")
        correct = self.correct_option_ids
        if len(set(correct)) != len(correct):
            raise ValueError("duplicate ids in correct_option_ids")
        if any(c not in ids for c in correct):
            raise ValueError("correct_option_ids must reference existing option ids")

        if self.type == "true_false":
            if len(self.options) != 2:
                raise ValueError("true_false needs exactly 2 options")
            if len(correct) != 1:
                raise ValueError("true_false needs exactly 1 correct option")
        elif self.type == "mcq":
            if not 3 <= len(self.options) <= 5:
                raise ValueError("mcq needs 3-5 options")
            if len(correct) != 1:
                raise ValueError("mcq needs exactly 1 correct option")
        else:  # multi_select
            if len(self.options) < 4:
                raise ValueError("multi_select needs at least 4 options")
            if len(correct) < 2:
                raise ValueError("multi_select needs at least 2 correct options")
            if len(correct) == len(self.options):
                raise ValueError("multi_select cannot have every option correct")
        return self


class GeneratedQuestion(QuestionBase):
    """What the LLM returns: no id/time/points; those are filled in by the service."""


class QuestionIn(QuestionBase):
    id: uuid.UUID | None = None


class QuestionOut(QuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int


class QuizBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=300)
    level: Level = "beginner"
    learning_goal: str = Field(default="", max_length=1000)
    language: str = Field(default="en", min_length=2, max_length=10)
    scoring_config: dict[str, float | int | bool] = Field(default_factory=dict)


class QuizCreate(QuizBase):
    """Manual quiz creation (questions optional; can be added later)."""

    questions: list[QuestionIn] = Field(default_factory=list, max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=10)


class QuizUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, min_length=1, max_length=300)
    level: Level | None = None
    learning_goal: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, min_length=2, max_length=10)
    status: Literal["draft", "published"] | None = None
    scoring_config: dict[str, float | int | bool] | None = None
    tags: list[str] | None = Field(default=None, max_length=10)
    # Full replacement list, in order. Omit to leave questions untouched.
    questions: list[QuestionIn] | None = Field(default=None, max_length=60)


class QuizOut(QuizBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    tags: list[str] = Field(default_factory=list)
    questions: list[QuestionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class QuizSummary(BaseModel):
    id: uuid.UUID
    title: str
    topic: str
    level: str
    status: str
    language: str
    question_count: int
    tags: list[str]
    updated_at: datetime


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    level: Level = "beginner"
    learning_goal: str = Field(default="", max_length=1000)
    num_questions: int = Field(default=10, ge=5, le=30)
    question_types: list[QuestionType] = Field(default_factory=lambda: list(DEFAULT_TYPES))
    time_limit_sec: int = Field(default=20, ge=5, le=120)
    language: str = Field(default="en", min_length=2, max_length=10)
    force_regenerate: bool = False

    @field_validator("question_types")
    @classmethod
    def _non_empty(cls, v: list[QuestionType]) -> list[QuestionType]:
        if not v:
            raise ValueError("choose at least one question type")
        return sorted(set(v))


class RegenerateQuestionRequest(BaseModel):
    feedback: str = Field(default="", max_length=300)
