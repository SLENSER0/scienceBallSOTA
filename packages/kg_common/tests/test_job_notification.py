"""Tests for job notifications — тесты уведомлений (§9.10)."""

from __future__ import annotations

import pytest

from kg_common.job_notification import (
    JobNotification,
    for_status,
    should_notify,
)


def test_failed_level_is_error_and_message_embeds_error() -> None:
    """failed -> error level with the error text in the message."""
    note = for_status("j1", "failed", error="boom")
    assert note.level == "error"
    assert note.event == "failed"
    assert "boom" in note.message


def test_succeeded_level_is_info() -> None:
    """succeeded -> info level."""
    note = for_status("j2", "succeeded")
    assert note.level == "info"
    assert note.event == "succeeded"


def test_canceled_level_is_warning() -> None:
    """canceled -> warning level."""
    note = for_status("j3", "canceled")
    assert note.level == "warning"
    assert note.event == "canceled"


def test_running_status_raises() -> None:
    """A non-terminal status is rejected by for_status."""
    with pytest.raises(ValueError):
        for_status("j", "running")


def test_unknown_status_raises() -> None:
    """An unknown status is rejected by for_status."""
    with pytest.raises(ValueError):
        for_status("j", "exploded")


def test_should_notify_running_false() -> None:
    """running is not terminal."""
    assert should_notify("running") is False
    assert should_notify("queued") is False


def test_should_notify_terminal_true() -> None:
    """All terminal statuses notify."""
    assert should_notify("succeeded") is True
    assert should_notify("failed") is True
    assert should_notify("canceled") is True


def test_doc_id_flows_into_as_dict() -> None:
    """doc_id round-trips through as_dict and appears in the message."""
    note = for_status("j4", "failed", doc_id="doc:x", error="io")
    payload = note.as_dict()
    assert payload["doc_id"] == "doc:x"
    assert "doc:x" in note.message


def test_as_dict_shape_for_success() -> None:
    """as_dict exposes the full payload with a None doc_id when absent."""
    payload = for_status("j5", "succeeded").as_dict()
    assert payload == {
        "job_id": "j5",
        "event": "succeeded",
        "level": "info",
        "message": payload["message"],
        "doc_id": None,
    }
    assert "j5" in payload["message"]


def test_failed_without_error_text_still_valid() -> None:
    """A failure with no error text still builds a valid error notification."""
    note = for_status("j6", "failed")
    assert note.level == "error"
    assert "failed" in note.message


def test_direct_construction_rejects_mismatched_level() -> None:
    """The dataclass guards that level matches the event."""
    with pytest.raises(ValueError):
        JobNotification(job_id="j", event="failed", level="info", message="x")


def test_empty_job_id_rejected() -> None:
    """A blank job_id is rejected."""
    with pytest.raises(ValueError):
        for_status("  ", "succeeded")
