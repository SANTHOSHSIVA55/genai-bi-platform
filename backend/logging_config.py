"""Application logging configuration.

Provides a single structured log line format that includes a per-request ID so
that logs can be correlated across the auth, AI and data layers. The request ID
is set by middleware in ``main`` via the ``request_id_var`` context variable.
"""
import logging
import os
import sys
from contextvars import ContextVar

request_id_var: ContextVar = ContextVar("request_id", default="-")

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | request=%(request_id)s | %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Suppress uvicorn's own per-request access logs (we emit our own with request IDs)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
