from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    temperature: float
    system: str
    user: str

    def render(self, **values: object) -> tuple[str, str]:
        """Return (system, user). Values are substituted as plain data."""
        str_values = {k: str(v) for k, v in values.items()}
        return self.system.format(**str_values).strip(), self.user.format(**str_values).strip()


@lru_cache
def load_prompt(name: str) -> PromptTemplate:
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---", 2)
    meta = dict(line.split(":", 1) for line in front.strip().splitlines())
    system_part, user_part = body.split("# USER", 1)
    system = system_part.split("# SYSTEM", 1)[1]
    return PromptTemplate(
        version=meta["version"].strip(),
        temperature=float(meta["temperature"].strip()),
        system=system,
        user=user_part,
    )
