"""Smoke import + public API surface."""

from __future__ import annotations


def test_public_api() -> None:
    import kg_common as m

    for name in (
        "get_settings",
        "GraphNode",
        "GraphEdge",
        "GraphResponse",
        "EvidenceRef",
        "canonical_key",
        "make_id",
        "uuid5_id",
        "get_logger",
        "setup_observability",
    ):
        assert hasattr(m, name), name


def test_logger_and_telemetry_noop() -> None:
    from kg_common import get_logger, setup_observability

    log = get_logger("test")
    log.info("hello", answer=42)
    setup_observability("test-service")  # must not raise without a collector
