"""Tests for §14.9 mutation preconditions (If-Match/If-Unmodified-Since → 412)."""

from __future__ import annotations

from api_gateway.precondition import (
    PreconditionResult,
    check_preconditions,
    evaluate_if_match,
    evaluate_if_unmodified_since,
)

# RFC 7231 example date: "Sun, 06 Nov 1994 08:49:37 GMT" == epoch 784111777.
_HTTP_DATE = "Sun, 06 Nov 1994 08:49:37 GMT"
_HTTP_DATE_EPOCH = 784111777


def test_if_match_none_header_passes() -> None:
    assert evaluate_if_match(None, "abc") is True


def test_if_match_quoted_tag_matches() -> None:
    assert evaluate_if_match('"abc"', "abc") is True


def test_if_match_mismatch_fails() -> None:
    assert evaluate_if_match('"xyz"', "abc") is False


def test_if_match_star_passes_when_exists() -> None:
    assert evaluate_if_match("*", "abc") is True


def test_if_match_star_fails_when_absent() -> None:
    # "*" requires the resource to exist; a None ETag means it does not.
    assert evaluate_if_match("*", None) is False


def test_if_match_weak_prefix_normalized() -> None:
    assert evaluate_if_match('W/"abc"', "abc") is True


def test_if_match_comma_list_any_match() -> None:
    assert evaluate_if_match('"zzz", "abc"', "abc") is True


def test_if_match_empty_string_fails() -> None:
    assert evaluate_if_match("", "abc") is False


def test_if_match_no_current_etag_fails() -> None:
    assert evaluate_if_match('"abc"', None) is False


def test_if_unmodified_since_at_boundary_passes() -> None:
    assert evaluate_if_unmodified_since(_HTTP_DATE, _HTTP_DATE_EPOCH) is True


def test_if_unmodified_since_after_fails() -> None:
    assert evaluate_if_unmodified_since(_HTTP_DATE, _HTTP_DATE_EPOCH + 1) is False


def test_if_unmodified_since_before_passes() -> None:
    assert evaluate_if_unmodified_since(_HTTP_DATE, _HTTP_DATE_EPOCH - 1) is True


def test_if_unmodified_since_none_header_passes() -> None:
    assert evaluate_if_unmodified_since(None, 0) is True


def test_if_unmodified_since_unparseable_fails() -> None:
    assert evaluate_if_unmodified_since("not-a-date", 0) is False


def test_check_preconditions_if_match_mismatch_412() -> None:
    result = check_preconditions('"xyz"', None, "abc", 0)
    assert result.status == 412
    assert result.passed is False


def test_check_preconditions_if_match_match_200() -> None:
    result = check_preconditions('"abc"', None, "abc", 0)
    assert result.passed is True
    assert result.status == 200


def test_check_preconditions_unmodified_since_fail_412() -> None:
    result = check_preconditions(None, _HTTP_DATE, None, _HTTP_DATE_EPOCH + 1)
    assert result.passed is False
    assert result.status == 412


def test_check_preconditions_both_present_pass_200() -> None:
    result = check_preconditions('"abc"', _HTTP_DATE, "abc", _HTTP_DATE_EPOCH)
    assert result.passed is True
    assert result.status == 200


def test_check_preconditions_no_headers_pass_200() -> None:
    result = check_preconditions(None, None, "abc", 0)
    assert result.passed is True
    assert result.status == 200


def test_precondition_result_is_frozen() -> None:
    result = PreconditionResult(passed=True, status=200)
    assert result.as_dict() == {"passed": True, "status": 200}


def test_precondition_result_failed_as_dict() -> None:
    result = PreconditionResult(passed=False, status=412)
    assert result.as_dict() == {"passed": False, "status": 412}
