"""HTTP Range parsing for §14.9 partial document downloads (206).

Разбор заголовка ``Range`` для частичной отдачи документов (§14.9).

Nothing existing parses ``Range`` — :func:`kg_common`/:mod:`error_catalog`
only enforces *content-length* limits. This module adds the small, pure
building blocks the Documents endpoints need to answer a single-range
``bytes=`` request with an ``HTTP 206 Partial Content`` response:

* :class:`ByteRange`         — frozen, satisfiable byte span ``[start, end]``.
* :func:`parse_range`        — header → :class:`ByteRange` (or ``None`` = full).
* :func:`is_satisfiable`     — does the header name any in-bounds byte?
* :func:`content_range_header` — render the ``Content-Range`` response value.

Only the single-range forms mandated by RFC 7233 are handled — ``bytes=0-99``
(closed), ``bytes=100-`` (open-ended, to EOF) and ``bytes=-500`` (suffix, last
N bytes). Multi-range (comma-separated) requests are treated as unparseable
(``None``); callers then fall back to a full ``200`` response.
"""

from __future__ import annotations

from dataclasses import dataclass

_UNIT = "bytes="


@dataclass(frozen=True, slots=True)
class ByteRange:
    """One satisfiable byte range ``[start, end]`` over a ``total``-byte body.

    Инвариант: ``0 <= start <= end <= total - 1`` — оба конца включительны
    (RFC 7233). :attr:`length` — число отдаваемых байт, :meth:`as_dict` — вид
    для журналов/тестов.
    """

    start: int
    end: int
    total: int

    @property
    def length(self) -> int:
        """Number of bytes covered — ``end - start + 1`` (inclusive) (§14.9)."""
        return self.end - self.start + 1

    def as_dict(self) -> dict[str, int]:
        """Structured view — ``start`` / ``end`` / ``total`` / ``length`` (§14.9)."""
        return {
            "start": self.start,
            "end": self.end,
            "total": self.total,
            "length": self.length,
        }


def parse_range(header: str | None, total: int) -> ByteRange | None:
    """Parse a single-range ``Range`` header into a :class:`ByteRange` (§14.9).

    Разбирает одиночный диапазон ``bytes=`` в :class:`ByteRange`.

    Returns ``None`` when there is no header (caller serves a full ``200``) or
    when the header is malformed / multi-range / unsatisfiable. Supported forms
    over a ``total``-byte body:

    * ``bytes=0-99``   — closed range; ``end`` clamped to ``total - 1``.
    * ``bytes=100-``   — open-ended; runs to the last byte (``total - 1``).
    * ``bytes=-500``   — suffix; the final ``500`` bytes of the body.
    """
    if header is None:
        return None
    if total <= 0:
        return None
    spec = header.strip()
    if not spec.startswith(_UNIT):
        return None
    spec = spec[len(_UNIT) :].strip()
    # Multi-range or empty specs are not served as partial content.
    if not spec or "," in spec or "-" not in spec:
        return None
    raw_start, _, raw_end = spec.partition("-")
    raw_start, raw_end = raw_start.strip(), raw_end.strip()

    last = total - 1
    if raw_start == "":
        # Suffix form: last ``raw_end`` bytes (e.g. ``bytes=-500``).
        if raw_end == "" or not raw_end.isdigit():
            return None
        suffix = int(raw_end)
        if suffix <= 0:
            return None
        start = max(0, total - suffix)
        return ByteRange(start=start, end=last, total=total)

    if not raw_start.isdigit():
        return None
    start = int(raw_start)
    if start > last:
        return None  # start past EOF → unsatisfiable

    if raw_end == "":
        end = last  # Open-ended form: to EOF.
    else:
        if not raw_end.isdigit():
            return None
        end = int(raw_end)
        if end < start:
            return None
        end = min(end, last)  # Clamp an over-long end to the last byte.

    return ByteRange(start=start, end=end, total=total)


def is_satisfiable(header: str, total: int) -> bool:
    """Whether ``header`` names at least one in-bounds byte of the body (§14.9).

    Проверяет, что диапазон попадает в границы ``[0, total)`` — иначе ответ
    должен быть ``416 Range Not Satisfiable``.
    """
    return parse_range(header, total) is not None


def content_range_header(br: ByteRange) -> str:
    """Render the ``Content-Range`` response value for a 206 reply (§14.9).

    Формат RFC 7233: ``bytes <start>-<end>/<total>``.
    """
    return f"bytes {br.start}-{br.end}/{br.total}"
