"""Structured logging via structlog (§1.12).

``configure()`` sets up JSON rendering in prod and pretty console output in dev,
injecting ``service``, ``request_id`` and ``trace_id`` when bound.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def configure(
    service: str = "science-ball", *, level: str | None = None, json_logs: bool | None = None
) -> None:
    global _configured
    from kg_common.config import get_settings

    settings = get_settings()
    lvl = (level or settings.log_level).upper()
    use_json = json_logs if json_logs is not None else settings.app_env != "local"

    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, lvl, logging.INFO)
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, lvl, logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _configured:
        configure()
    return structlog.get_logger(name)  # type: ignore[return-value]
