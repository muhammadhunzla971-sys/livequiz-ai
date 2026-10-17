"""Tiny Prometheus-format metrics (no extra dependency).

Counters live in process memory: each API instance exposes its own numbers and Prometheus
sums them. Gauges such as active rooms are computed when /metrics is scraped.
"""

from collections import defaultdict
from threading import Lock

_lock = Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)

_HELP = {
    "livequiz_http_requests_total": "HTTP requests by status class",
    "livequiz_http_request_seconds_total": "Total seconds spent serving HTTP requests",
    "livequiz_llm_calls_total": "LLM provider calls by outcome",
    "livequiz_llm_seconds_total": "Total seconds spent waiting for the LLM provider",
    "livequiz_llm_tokens_total": "LLM tokens used, by kind (prompt or completion)",
    "livequiz_ws_messages_total": "WebSocket messages received from clients",
}


def inc(name: str, value: float = 1.0, **labels: str) -> None:
    with _lock:
        _counters[(name, tuple(sorted(labels.items())))] += value


def reset() -> None:
    with _lock:
        _counters.clear()


def render(gauges: dict[str, float]) -> str:
    """Prometheus text exposition for counters plus the supplied gauges."""
    lines: list[str] = []
    with _lock:
        items = sorted(_counters.items())
    seen: set[str] = set()
    for (name, labels), value in items:
        if name not in seen:
            seen.add(name)
            lines.append(f"# HELP {name} {_HELP.get(name, name)}")
            lines.append(f"# TYPE {name} counter")
        label_text = ",".join(f'{k}="{v}"' for k, v in labels)
        lines.append(f"{name}{{{label_text}}} {value:g}" if labels else f"{name} {value:g}")
    for name, value in sorted(gauges.items()):
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value:g}")
    return "\n".join(lines) + "\n"
