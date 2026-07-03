"""Tests for §14.9 ``Accept`` content negotiation (documents/pages)."""

from __future__ import annotations

from api_gateway.content_negotiation import (
    MediaRange,
    acceptable,
    best_match,
    parse_accept,
)


def test_parse_accept_default_q_is_one() -> None:
    ranges = parse_accept("text/html,application/json;q=0.9")
    assert ranges[0].subtype == "html"
    assert ranges[0].q == 1.0


def test_parse_accept_explicit_q() -> None:
    assert parse_accept("application/json;q=0.9")[0].q == 0.9


def test_parse_accept_clamps_high_q() -> None:
    assert parse_accept("a/b;q=5")[0].q == 1.0


def test_parse_accept_clamps_negative_q() -> None:
    assert parse_accept("a/b;q=-3")[0].q == 0.0


def test_parse_accept_malformed_q_defaults_to_one() -> None:
    assert parse_accept("a/b;q=oops")[0].q == 1.0


def test_parse_accept_sorts_by_q_then_specificity() -> None:
    # Equal q=1.0: text/plain (specificity 2) beats text/* (1) beats */* (0).
    ranges = parse_accept("*/*, text/*, text/plain")
    assert [(r.type, r.subtype) for r in ranges] == [
        ("text", "plain"),
        ("text", "*"),
        ("*", "*"),
    ]


def test_parse_accept_bare_type_becomes_wildcard_subtype() -> None:
    (only,) = parse_accept("image")
    assert (only.type, only.subtype) == ("image", "*")


def test_parse_accept_skips_empty_parts() -> None:
    ranges = parse_accept("text/html, , application/json")
    assert len(ranges) == 2


def test_parse_accept_empty_is_star_star() -> None:
    (only,) = parse_accept("")
    assert (only.type, only.subtype, only.q) == ("*", "*", 1.0)


def test_best_match_prefers_higher_q() -> None:
    header = "image/*, application/json;q=0.5"
    assert best_match(header, ["application/json", "image/png"]) == "image/png"


def test_best_match_no_overlap_is_none() -> None:
    assert best_match("application/xml", ["application/json"]) is None


def test_best_match_empty_header_takes_first_available() -> None:
    assert best_match("", ["application/json"]) == "application/json"


def test_best_match_zero_q_is_not_acceptable() -> None:
    # q=0 explicitly rejects the only overlapping range.
    assert best_match("application/json;q=0", ["application/json"]) is None


def test_best_match_tie_breaks_on_available_order() -> None:
    # Both acceptable at q=1.0 via */*; the first available wins.
    header = "*/*"
    assert best_match(header, ["text/html", "application/json"]) == "text/html"


def test_acceptable_star_matches_anything() -> None:
    assert acceptable("*/*", "image/png") is True


def test_acceptable_mismatch_is_false() -> None:
    assert acceptable("text/plain", "application/json") is False


def test_acceptable_type_wildcard() -> None:
    assert acceptable("image/*", "image/png") is True


def test_acceptable_zero_q_is_false() -> None:
    assert acceptable("application/json;q=0", "application/json") is False


def test_acceptable_empty_header_is_true() -> None:
    assert acceptable("", "anything/here") is True


def test_media_range_as_dict() -> None:
    assert MediaRange("image", "*", 0.5).as_dict()["q"] == 0.5


def test_media_range_as_dict_full_shape() -> None:
    assert MediaRange("text", "html", 1.0).as_dict() == {
        "type": "text",
        "subtype": "html",
        "q": 1.0,
    }
