import json
import re

from app.llm.provider import LLMError, LLMResult


def make_q(n: int, qtype: str = "mcq") -> dict:
    if qtype == "true_false":
        return {
            "type": "true_false",
            "text": f"Statement number {n} is correct, true or false?",
            "options": [{"id": "A", "text": "True"}, {"id": "B", "text": "False"}],
            "correct_option_ids": ["A"],
            "explanation": "Because it is.",
            "difficulty": 1,
            "bloom_level": "remember",
            "subtopic": "Basics",
        }
    return {
        "type": "mcq",
        "text": f"Sample question number {n} about the topic?",
        "options": [
            {"id": "A", "text": f"Wrong answer {n}-a"},
            {"id": "B", "text": f"Right answer {n}"},
            {"id": "C", "text": f"Wrong answer {n}-c"},
            {"id": "D", "text": f"Wrong answer {n}-d"},
        ],
        "correct_option_ids": ["B"],
        "explanation": "Because B is right.",
        "difficulty": 2,
        "bloom_level": "understand",
        "subtopic": "Basics",
    }


class FakeLLM:
    """Scriptable stand-in for an LLM provider. No network."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (step, model)
        self.counter = 0
        self.fail_models: set[str] = set()
        self.script: dict[str, list[str]] = {}
        self.flag_indices: list[int] = []

    @staticmethod
    def step_of(system: str, user: str) -> str:
        if "curriculum designer" in system:
            return "plan"
        if "fact-checker" in system:
            return "review"
        if "Write exactly 1 replacement question" in user:
            return "regenerate"
        return "generate"

    def count(self, step: str) -> int:
        return sum(1 for s, _ in self.calls if s == step)

    def _default(self, step: str, user: str) -> str:
        if step == "plan":
            return json.dumps(
                {
                    "subtopics": [{"name": "Basics", "questions": 5}],
                    "bloom_distribution": {"remember": 3, "understand": 2},
                }
            )
        if step == "review":
            return json.dumps(
                {"issues": [{"index": i, "problem": "ambiguous"} for i in self.flag_indices]}
            )
        if step == "regenerate":
            qtype = re.search(r"Question type: (\w+)", user)
            self.counter += 1
            return json.dumps(
                {"questions": [make_q(1000 + self.counter, qtype.group(1) if qtype else "mcq")]}
            )
        n = int(re.search(r"Write (\d+) questions", user).group(1))  # type: ignore[union-attr]
        qs = []
        for _ in range(n):
            self.counter += 1
            qs.append(make_q(self.counter))
        return json.dumps({"questions": qs})

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
        step = self.step_of(system, user)
        self.calls.append((step, model))
        if model in self.fail_models:
            raise LLMError("simulated outage")
        queue = self.script.get(step)
        text = queue.pop(0) if queue else self._default(step, user)
        return LLMResult(
            text=text, model=model, prompt_tokens=10, completion_tokens=20, latency_ms=5
        )
