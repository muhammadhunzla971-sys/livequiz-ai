"""Input sanitisation, prompt-injection guarding, and a rules-based classroom-safety filter.

This is a deliberately simple first line of defence. A hosted moderation endpoint can be
plugged in behind `is_safe_text` later without changing callers (see docs/DECISIONS.md).
"""

import re
import unicodedata

from app.schemas.quiz import GeneratedQuestion


class UnsafeContentError(ValueError):
    """Raised when text is not suitable for a classroom."""


_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any |the )?(previous|prior|above|earlier)",
    r"(reveal|show|print|repeat) (your |the )?(system )?(prompt|instructions)",
    r"you are now\b",
    r"act as (a |an )?(?!teacher)",
    r"</?(system|assistant|user|topic|goal)>",
    r"\bjailbreak\b",
    r"new instructions?:",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# Small illustrative blocklist of clearly unsafe categories. Whole-word matches only.
_BLOCKED_TERMS = {
    "porn",
    "pornography",
    "nude",
    "nudes",
    "sex tape",
    "how to make a bomb",
    "build a bomb",
    "make meth",
    "kill yourself",
    "suicide method",
    "child abuse material",
}
_BLOCK_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(_BLOCKED_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def sanitize_input(text: str, max_len: int) -> str:
    """Normalise unicode, drop control chars, collapse whitespace, strip injection phrases."""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHARS.sub("", text)
    text = _INJECTION_RE.sub(" ", text)
    text = text.replace("{", "(").replace("}", ")")
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:max_len]


def is_safe_text(text: str) -> bool:
    return _BLOCK_RE.search(unicodedata.normalize("NFKC", text)) is None


def check_input(*texts: str) -> None:
    for t in texts:
        if not is_safe_text(t):
            raise UnsafeContentError("This topic isn't suitable for a classroom quiz.")


def check_question(q: GeneratedQuestion) -> bool:
    """True if a generated question is classroom-safe."""
    parts = [q.text, q.explanation, *(o.text for o in q.options)]
    return all(is_safe_text(p) for p in parts)


_NICK_BLOCKED = {
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "cunt",
    "dick",
    "porn",
    "nazi",
    "rape",
    "nigger",
    "nigga",
    "slut",
    "whore",
}
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)


def clean_nickname(raw: str) -> str:
    """Normalise a nickname for display: NFKC, no control chars, collapsed whitespace."""
    text = unicodedata.normalize("NFKC", raw)
    text = _CONTROL_CHARS.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def is_clean_nickname(nick: str) -> bool:
    """Rules-based profanity filter; catches simple leetspeak and separators (f.u.c.k)."""
    squashed = re.sub(r"[^a-z]", "", nick.lower().translate(_LEET))
    return not any(bad in squashed for bad in _NICK_BLOCKED)
