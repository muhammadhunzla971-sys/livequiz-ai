"""Seed a demo teacher and a sample quiz.  Usage: python -m app.seed"""

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import dispose_engine, get_sessionmaker
from app.models import Question, Quiz, User

DEMO_EMAIL = "demo@livequiz.ai"
DEMO_PASSWORD = "demo-password-123"

SAMPLE_QUESTIONS = [
    {
        "type": "mcq",
        "text": "Which gas do plants take in for photosynthesis?",
        "options": [
            {"id": "A", "text": "Oxygen"},
            {"id": "B", "text": "Carbon dioxide"},
            {"id": "C", "text": "Nitrogen"},
            {"id": "D", "text": "Hydrogen"},
        ],
        "correct_option_ids": ["B"],
        "explanation": "Plants absorb carbon dioxide through their stomata to build sugars.",
        "bloom_level": "remember",
        "subtopic": "Inputs",
    },
    {
        "type": "true_false",
        "text": "Photosynthesis releases oxygen as a by-product.",
        "options": [{"id": "A", "text": "True"}, {"id": "B", "text": "False"}],
        "correct_option_ids": ["A"],
        "explanation": "Water is split during the light reactions, releasing oxygen.",
        "bloom_level": "remember",
        "subtopic": "Outputs",
    },
    {
        "type": "multi_select",
        "text": "Which of these are inputs to photosynthesis? (Select all that apply)",
        "options": [
            {"id": "A", "text": "Water"},
            {"id": "B", "text": "Glucose"},
            {"id": "C", "text": "Carbon dioxide"},
            {"id": "D", "text": "Sunlight"},
        ],
        "correct_option_ids": ["A", "C", "D"],
        "explanation": "Water, CO2 and light go in; glucose and oxygen come out.",
        "bloom_level": "understand",
        "subtopic": "Inputs",
    },
    {
        "type": "mcq",
        "text": "Where in the plant cell does photosynthesis mainly happen?",
        "options": [
            {"id": "A", "text": "Mitochondria"},
            {"id": "B", "text": "Nucleus"},
            {"id": "C", "text": "Chloroplast"},
            {"id": "D", "text": "Vacuole"},
        ],
        "correct_option_ids": ["C"],
        "explanation": "Chloroplasts contain chlorophyll, which captures light energy.",
        "bloom_level": "remember",
        "subtopic": "Cell structure",
    },
    {
        "type": "mcq",
        "text": "A plant is kept in the dark for a week. What happens to its glucose production?",
        "options": [
            {"id": "A", "text": "It increases"},
            {"id": "B", "text": "It stays the same"},
            {"id": "C", "text": "It drops sharply"},
            {"id": "D", "text": "It switches to producing oxygen only"},
        ],
        "correct_option_ids": ["C"],
        "explanation": "Without light the light reactions stop, so sugar production falls.",
        "bloom_level": "apply",
        "subtopic": "Outputs",
    },
]


async def seed() -> None:
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="Demo Teacher",
            )
            db.add(user)
            await db.flush()

        existing = await db.scalar(
            select(Quiz).where(Quiz.owner_id == user.id, Quiz.title == "Photosynthesis Basics")
        )
        if existing is None:
            quiz = Quiz(
                owner_id=user.id,
                title="Photosynthesis Basics",
                topic="Photosynthesis",
                level="beginner",
                learning_goal="Understand the inputs and outputs of photosynthesis",
                status="published",
                scoring_config={
                    "base_points": 1000,
                    "speed_bonus": True,
                    "streak_step": 0.1,
                    "streak_cap": 0.5,
                },
            )
            quiz.questions = [
                Question(position=i, difficulty=1, time_limit_sec=20, points=1000, **q)
                for i, q in enumerate(SAMPLE_QUESTIONS)
            ]
            db.add(quiz)
        await db.commit()
    await dispose_engine()
    print(f"Seeded. Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
