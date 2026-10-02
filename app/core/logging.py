"""Structured (JSON) logging plus a request-id context variable."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED = frozenset(
    set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys())
    | {"message", "asctime", "taskName"}
)


def log_fields(**fields: Any) -> dict[str, Any]:
    """Build a logging `extra` dict that cannot collide with LogRecord.

    `logging` raises `KeyError` if an `extra` key shadows a built-in record
    attribute - `filename` and `module` are easy names to reach for in this
    domain. Colliding keys are prefixed instead of exploding at runtime.
    """
    return {(key if key not in _RESERVED else f"ctx_{key}"): value for key, value in fields.items()}


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record, merging in any `extra=` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", as_json: bool = True) -> None:
    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    if as_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s | %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn installs its own handlers; route its records through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
