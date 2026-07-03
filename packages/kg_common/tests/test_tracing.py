"""W3C trace-context (``traceparent``) helper tests (§18.2 propagation).

All tests are deterministic and instant: ids come from ``trace_id_from`` /
``span_id_from`` (seeded hashing) or from an injected byte ``source`` — no real
randomness ever runs here.
"""

from __future__ import annotations

import pytest

from kg_common.tracing import (
    TraceContext,
    child_context,
    format_traceparent,
    new_span_id,
    new_trace_id,
    parse_traceparent,
    root_context,
    span_id_from,
    trace_id_from,
)


def test_format_then_parse_roundtrip() -> None:
    ctx = TraceContext(trace_id=trace_id_from("req-1"), span_id=span_id_from("span-1"))
    header = format_traceparent(ctx)
    back = parse_traceparent(header)
    assert back is not None
    assert back.trace_id == ctx.trace_id
    assert back.span_id == ctx.span_id
    assert back.version == ctx.version
    assert back.flags == ctx.flags
    # Round-trip is stable at the header level too.
    assert format_traceparent(back) == header


@pytest.mark.parametrize(
    "header",
    [
        "",  # empty
        "00-abc-def-01",  # ids far too short
        "00-" + "a" * 31 + "-" + "b" * 16 + "-01",  # trace-id 31 hex (one short)
        "00-" + "a" * 32 + "-" + "b" * 15 + "-01",  # span-id 15 hex (one short)
        "00-" + "a" * 32 + "-" + "b" * 16 + "-1",  # flags 1 hex
        "00-" + "a" * 32 + "-" + "b" * 16,  # only 3 segments
        "00-" + "a" * 32 + "-" + "b" * 16 + "-01-extra",  # 5 segments
        "ff-" + "a" * 32 + "-" + "b" * 16 + "-01",  # reserved/invalid version
        "0-" + "a" * 32 + "-" + "b" * 16 + "-01",  # version 1 hex
        "00-" + "0" * 32 + "-" + "b" * 16 + "-01",  # all-zero trace-id
        "00-" + "a" * 32 + "-" + "0" * 16 + "-01",  # all-zero span-id
    ],
)
def test_parse_rejects_malformed(header: str) -> None:
    assert parse_traceparent(header) is None


def test_empty_header_returns_none() -> None:
    assert parse_traceparent("") is None
    assert parse_traceparent(None) is None


def test_hex_validation_rejects_non_hex() -> None:
    # 'g' and 'z' are not hex; both segments are otherwise the right length.
    bad_trace = "00-" + "g" * 32 + "-" + "b" * 16 + "-01"
    bad_span = "00-" + "a" * 32 + "-" + "z" * 16 + "-01"
    assert parse_traceparent(bad_trace) is None
    assert parse_traceparent(bad_span) is None


def test_trace_id_from_is_deterministic_and_32_hex() -> None:
    a = trace_id_from("chat:42")
    b = trace_id_from("chat:42")
    assert a == b
    assert a != trace_id_from("chat:43")
    assert len(a) == 32
    assert all(ch in "0123456789abcdef" for ch in a)


def test_span_id_from_is_deterministic_and_16_hex() -> None:
    a = span_id_from("node:resolve")
    assert a == span_id_from("node:resolve")
    assert a != span_id_from("node:plan")
    assert len(a) == 16
    assert all(ch in "0123456789abcdef" for ch in a)


def test_new_ids_have_correct_length_and_injectable_source() -> None:
    # Injected byte source keeps this deterministic (no os.urandom).
    src = lambda n: bytes(range(n))  # noqa: E731 - tiny deterministic stub
    tid = new_trace_id(source=src)
    sid = new_span_id(source=src)
    assert len(tid) == 32 and tid == bytes(range(16)).hex()
    assert len(sid) == 16 and sid == bytes(range(8)).hex()
    # Seeded convenience path matches the standalone derivations.
    assert new_trace_id(seed="s") == trace_id_from("s")
    assert new_span_id(seed="s") == span_id_from("s")


def test_child_keeps_trace_id_changes_span_and_links_parent() -> None:
    parent = root_context(seed="request-9")
    kid_span = span_id_from("downstream")
    kid = child_context(parent, kid_span)
    assert kid.trace_id == parent.trace_id  # same trace («один трейс»)
    assert kid.span_id == kid_span  # new current span
    assert kid.span_id != parent.span_id
    assert kid.parent_span_id == parent.span_id  # linkage to parent
    assert kid.flags == parent.flags


def test_child_context_rejects_bad_span() -> None:
    parent = root_context(seed="request-x")
    with pytest.raises(ValueError):
        child_context(parent, "not-hex")
    with pytest.raises(ValueError):
        child_context(parent, "0" * 16)  # all-zero span is invalid


def test_version_is_00() -> None:
    ctx = root_context(seed="v")
    assert ctx.version == "00"
    header = format_traceparent(ctx)
    assert header.startswith("00-")
    parsed = parse_traceparent(header)
    assert parsed is not None and parsed.version == "00"


def test_flags_parsed_and_sampled_property() -> None:
    tid, sid = "a" * 32, "b" * 16
    sampled = parse_traceparent(f"00-{tid}-{sid}-01")
    not_sampled = parse_traceparent(f"00-{tid}-{sid}-00")
    assert sampled is not None and sampled.flags == "01" and sampled.sampled is True
    assert not_sampled is not None and not_sampled.flags == "00"
    assert not_sampled.sampled is False


def test_as_dict_is_structured_view() -> None:
    parent = root_context(seed="req")
    kid = child_context(parent, span_id_from("child"))
    d = kid.as_dict()
    assert d == {
        "version": "00",
        "trace_id": parent.trace_id,
        "span_id": span_id_from("child"),
        "flags": "01",
        "parent_span_id": parent.span_id,
        "sampled": True,
        "traceparent": format_traceparent(kid),
    }


def test_traceparent_root_is_unsampled_when_requested() -> None:
    ctx = root_context(seed="q", sampled=False)
    assert ctx.flags == "00" and ctx.sampled is False
    # Still a valid, round-trippable header.
    assert parse_traceparent(ctx.to_header()) is not None


def test_direct_construction_rejects_malformed_fields() -> None:
    with pytest.raises(ValueError):
        TraceContext(trace_id="short", span_id="b" * 16)
    with pytest.raises(ValueError):
        TraceContext(trace_id="a" * 32, span_id="b" * 16, flags="xx")
