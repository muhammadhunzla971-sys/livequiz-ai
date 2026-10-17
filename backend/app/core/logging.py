import contextvars
import logging
import re
import sys

from pythonjsonlogger.json import JsonFormatter

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


_SECRET_QS = re.compile(r"([?&](?:token|access_token|refresh_token)=)[^&\s\"]+")


class RedactSecrets(logging.Filter):
    """Keeps tokens passed in WebSocket URLs (?token=...) out of the logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "token=" in msg:
            record.msg = _SECRET_QS.sub(r"\1[redacted]", msg)
            record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addFilter(RedactSecrets())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s")
    )
    handler.addFilter(RequestIdFilter())
    handler.addFilter(RedactSecrets())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
