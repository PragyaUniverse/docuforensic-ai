"""Structured JSON logs. Secrets are scrubbed from every record; document values aren't logged."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from llm.redact import scrub_secrets


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname, "logger": record.name, "msg": scrub_secrets(record.getMessage()),
        }
        if record.exc_info and record.exc_info[0]:
            # The exception type only: messages and tracebacks can quote document values.
            entry["exc_type"] = record.exc_info[0].__name__
        return json.dumps(entry)


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger("docuforensic")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
