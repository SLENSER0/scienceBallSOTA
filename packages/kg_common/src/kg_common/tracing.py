"""W3C Trace-Context (``traceparent``) propagation helpers (§18.2).

Pure-Python, zero-dependency helpers to carry a trace across service hops
(«проброс ``traceparent`` между сервисами»: API Gateway → agent-service →
downstream). This module deliberately does **not** import ``opentelemetry`` —
the embedded profile has no collector, and the gateway/agent only need to
*parse*, *format* and *chain* the header so logs↔traces stay correlated by
``trace_id`` (§18.1/§18.2).

The header wire format is the W3C ``traceparent`` (version ``00``)::

    00-<32 hex trace-id>-<16 hex span-id>-<2 hex trace-flags>
    │   │                │                └ flags, bit 0 = sampled («сэмплирован»)
    │   │                └ parent span-id / current span («идентификатор спана»)
    │   └ trace-id, shared by every span of one request («идентификатор трейса»)
    └ version, only ``00`` is defined

Public surface:

* :class:`TraceContext`      — frozen, validated 4-tuple with :meth:`as_dict`.
* :func:`new_trace_id` / :func:`new_span_id` — random hex ids (injectable source).
* :func:`trace_id_from` / :func:`span_id_from` — deterministic ids from a seed.
* :func:`parse_traceparent`  — strict parse of an inbound header → ctx | ``None``.
* :func:`format_traceparent` — render a ctx back to the wire header.
* :func:`root_context`       — mint a fresh root trace (the gateway entrypoint).
* :func:`child_context`      — chain a downstream span onto a parent (linkage).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass

# Injectable byte source: ``n -> n random bytes`` (defaults to :func:`os.urandom`).
RandBytes = Callable[[int], bytes]

# Field widths in hex characters (bytes * 2) per the W3C spec.
_TRACE_ID_HEX = 32
_SPAN_ID_HEX = 16
_VERSION_HEX = 2
_FLAGS_HEX = 2

# The only defined version; ``ff`` is reserved/invalid («зарезервировано»).
VERSION = "00"
_INVALID_VERSION = "ff"

# trace-flags bit 0 = sampled. Default: sampled on («сэмплировать»).
FLAG_SAMPLED = 0x01
FLAGS_SAMPLED = "01"
FLAGS_NONE = "00"

_HEX_CHARS = frozenset("0123456789abcdef")


def _is_hex(value: str, length: int) -> bool:
    """True iff ``value`` is exactly ``length`` lowercase hex chars (§18.2)."""
    return len(value) == length and all(ch in _HEX_CHARS for ch in value)


def _is_nonzero_hex(value: str, length: int) -> bool:
    """Hex id that is well-formed *and* not all-zeros (W3C rejects all-zero ids)."""
    return _is_hex(value, length) and set(value) != {"0"}


@dataclass(frozen=True, slots=True)
class TraceContext:
    """A validated W3C trace-context — контекст трейса (§18.2).

    Always well-formed: the constructor rejects malformed ids/flags so any
    ``TraceContext`` in hand is safe to serialize onto the wire. ``parent_span_id``
    records upstream linkage («связь с родительским спаном») when this context was
    derived via :func:`child_context`; it is *not* part of the header.
    """

    trace_id: str
    span_id: str
    version: str = VERSION
    flags: str = FLAGS_SAMPLED
    parent_span_id: str | None = None

    def __post_init__(self) -> None:
        if not _is_hex(self.version, _VERSION_HEX) or self.version == _INVALID_VERSION:
            raise ValueError(f"invalid trace-context version: {self.version!r}")
        if not _is_nonzero_hex(self.trace_id, _TRACE_ID_HEX):
            raise ValueError("trace_id must be 32 lowercase hex chars, non-zero")
        if not _is_nonzero_hex(self.span_id, _SPAN_ID_HEX):
            raise ValueError("span_id must be 16 lowercase hex chars, non-zero")
        if not _is_hex(self.flags, _FLAGS_HEX):
            raise ValueError("flags must be 2 lowercase hex chars")
        if self.parent_span_id is not None and not _is_nonzero_hex(
            self.parent_span_id, _SPAN_ID_HEX
        ):
            raise ValueError("parent_span_id must be 16 lowercase hex chars, non-zero")

    @property
    def sampled(self) -> bool:
        """Whether the sampled flag (bit 0) is set — «сэмплирован» (§18.2)."""
        return bool(int(self.flags, 16) & FLAG_SAMPLED)

    def to_header(self) -> str:
        """Render this context as a ``traceparent`` header value."""
        return format_traceparent(self)

    def as_dict(self) -> dict[str, str | bool | None]:
        """JSON-friendly view — structured for log/trace correlation (§18.1/§18.2)."""
        return {
            "version": self.version,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "flags": self.flags,
            "parent_span_id": self.parent_span_id,
            "sampled": self.sampled,
            "traceparent": self.to_header(),
        }


def new_trace_id(*, source: RandBytes | None = None, seed: str | None = None) -> str:
    """Fresh 32-hex trace-id. Inject ``source`` or ``seed`` for determinism (§18.2)."""
    if seed is not None:
        return trace_id_from(seed)
    gen = source or os.urandom
    return gen(_TRACE_ID_HEX // 2).hex()


def new_span_id(*, source: RandBytes | None = None, seed: str | None = None) -> str:
    """Fresh 16-hex span-id. Inject ``source`` or ``seed`` for determinism (§18.2)."""
    if seed is not None:
        return span_id_from(seed)
    gen = source or os.urandom
    return gen(_SPAN_ID_HEX // 2).hex()


def trace_id_from(seed: str) -> str:
    """Deterministic 32-hex trace-id from a seed string (same seed → same id).

    Used to make traces reproducible in tests («детерминизм в тестах») and to
    derive a stable id from a natural key such as a ``request_id`` (§18.2).
    """
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:_TRACE_ID_HEX]


def span_id_from(seed: str) -> str:
    """Deterministic 16-hex span-id from a seed string (same seed → same id)."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:_SPAN_ID_HEX]


def format_traceparent(ctx: TraceContext) -> str:
    """Render a :class:`TraceContext` as a W3C ``traceparent`` header (§18.2)."""
    return f"{ctx.version}-{ctx.trace_id}-{ctx.span_id}-{ctx.flags}"


def parse_traceparent(header: str | None) -> TraceContext | None:
    """Parse an inbound ``traceparent`` header, or ``None`` if malformed (§18.2).

    Strictly validates the ``00-<32hex>-<16hex>-<2hex>`` shape: exactly four
    ``-``-separated segments, lowercase hex of the right widths, a known version
    (not ``ff``), and non-all-zero trace-/span-ids. Any deviation → ``None`` so a
    bad upstream header cannot corrupt the trace («обрезанные трейсы», §18.2).
    """
    if not header:
        return None
    parts = header.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, flags = parts
    if not _is_hex(version, _VERSION_HEX) or version == _INVALID_VERSION:
        return None
    if not _is_nonzero_hex(trace_id, _TRACE_ID_HEX):
        return None
    if not _is_nonzero_hex(span_id, _SPAN_ID_HEX):
        return None
    if not _is_hex(flags, _FLAGS_HEX):
        return None
    return TraceContext(trace_id=trace_id, span_id=span_id, version=version, flags=flags)


def root_context(
    *,
    seed: str | None = None,
    source: RandBytes | None = None,
    sampled: bool = True,
) -> TraceContext:
    """Mint a fresh root trace — the entrypoint span (API Gateway, §18.2).

    Both ids are minted from ``seed``/``source`` so a whole trace is reproducible
    in tests. ``parent_span_id`` is ``None`` because a root has no upstream span.
    """
    trace_id = new_trace_id(source=source, seed=None if seed is None else f"{seed}/trace")
    span_id = new_span_id(source=source, seed=None if seed is None else f"{seed}/span")
    return TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        flags=FLAGS_SAMPLED if sampled else FLAGS_NONE,
    )


def child_context(parent: TraceContext, new_span_id: str) -> TraceContext:
    """Chain a downstream span onto ``parent`` — child span (§18.2).

    Keeps the parent's ``trace_id`` and ``flags`` (the trace is one unit), assigns
    the caller-supplied ``new_span_id`` as the current span, and records the
    parent's span as ``parent_span_id`` (linkage, «родительский спан»). Raises
    ``ValueError`` if ``new_span_id`` is not a valid 16-hex span-id.
    """
    if not _is_nonzero_hex(new_span_id, _SPAN_ID_HEX):
        raise ValueError("new_span_id must be 16 lowercase hex chars, non-zero")
    return TraceContext(
        trace_id=parent.trace_id,
        span_id=new_span_id,
        version=parent.version,
        flags=parent.flags,
        parent_span_id=parent.span_id,
    )
