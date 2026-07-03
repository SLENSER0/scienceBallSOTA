"""Schedule records -> iCalendar ``VEVENT`` feed — экспорт расписания в ``.ics`` (§24.16).

A pure-stdlib, dependency-free serialiser (RFC 5545) that turns experiment/notification
schedule records into an iCalendar ``.ics`` feed subscribers can import into a calendar
client — подписка на расписание экспериментов и уведомлений.

Text property values (``SUMMARY``/``DESCRIPTION``) are escaped per RFC 5545 §3.3.11 via
:func:`escape_text` — backslash, comma, semicolon and newline are backslash-escaped.
Content lines are folded to 75 octets with CRLF + a single leading space by
:func:`fold_line` (§3.1), so long values stay conformant — сворачивание длинных строк.
Each :class:`VEvent` renders a ``BEGIN:VEVENT``…``END:VEVENT`` block; :func:`to_ics`
wraps events in a ``BEGIN:VCALENDAR``/``END:VCALENDAR`` skeleton with ``VERSION:2.0``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "VEvent",
    "escape_text",
    "fold_line",
    "event_from",
    "to_ics",
]

# RFC 5545 §3.1: content lines SHOULD NOT exceed 75 octets, excluding the CRLF break.
_MAX_OCTETS = 75

# Line separator per RFC 5545 §3.1 — iCalendar uses CRLF between content lines.
_CRLF = "\r\n"


def escape_text(s: str) -> str:
    """Backslash-escape TEXT-value specials per RFC 5545 §3.3.11 — экранирование текста.

    Escapes ``\\`` -> ``\\\\``, ``,`` -> ``\\,``, ``;`` -> ``\\;`` and any newline
    (``\\r\\n``/``\\n``/``\\r``) -> ``\\n``. Backslash is escaped first so already-escaped
    output is not doubled — например, ``"a,b;c"`` -> ``"a\\,b\\;c"``.
    """
    out = s.replace("\\", "\\\\")
    out = out.replace(",", "\\,")
    out = out.replace(";", "\\;")
    out = out.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    return out


def fold_line(line: str) -> str:
    """Fold a content line to 75 octets with CRLF + leading space per §3.1 — сворачивание.

    A line whose UTF-8 length is within 75 octets is returned unchanged. Otherwise it is
    split so each physical line stays within 75 octets: the first chunk takes up to 75,
    each continuation up to 74 (the joined leading space costs one octet). Splits fall on
    character boundaries so multibyte runes are never cut — CRLF + пробел между кусками.
    """
    if len(line.encode("utf-8")) <= _MAX_OCTETS:
        return line
    chunks: list[str] = []
    current = ""
    current_octets = 0
    limit = _MAX_OCTETS  # first physical line has no leading space
    for ch in line:
        ch_octets = len(ch.encode("utf-8"))
        if current and current_octets + ch_octets > limit:
            chunks.append(current)
            current = ch
            current_octets = ch_octets
            limit = _MAX_OCTETS - 1  # continuation lines carry a single leading space
        else:
            current += ch
            current_octets += ch_octets
    chunks.append(current)
    return (_CRLF + " ").join(chunks)


@dataclass(frozen=True)
class VEvent:
    """One iCalendar ``VEVENT`` — событие расписания (§24.16).

    ``uid`` is the globally-unique event identifier, ``dtstart``/``dtend`` are iCalendar
    date-time strings (``dtend`` optional), and ``summary``/``description`` are free TEXT
    escaped on render. Frozen so an event is a value object — неизменяемое событие.
    """

    uid: str
    summary: str
    dtstart: str
    dtend: str | None
    description: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view — сериализуемое представление события."""
        return {
            "uid": self.uid,
            "summary": self.summary,
            "dtstart": self.dtstart,
            "dtend": self.dtend,
            "description": self.description,
        }

    def to_ical(self) -> str:
        """Render the ``BEGIN:VEVENT``…``END:VEVENT`` block (§24.16).

        Emits ``UID``/``DTSTART``/``SUMMARY``/``DESCRIPTION`` lines (plus ``DTEND`` only
        when ``dtend`` is not ``None``); TEXT values are :func:`escape_text`-d and every
        line is :func:`fold_line`-d. Lines are joined by CRLF — блок VEVENT.
        """
        lines = [
            "BEGIN:VEVENT",
            f"UID:{self.uid}",
            f"DTSTART:{self.dtstart}",
        ]
        if self.dtend is not None:
            lines.append(f"DTEND:{self.dtend}")
        lines.append(f"SUMMARY:{escape_text(self.summary)}")
        lines.append(f"DESCRIPTION:{escape_text(self.description)}")
        lines.append("END:VEVENT")
        return _CRLF.join(fold_line(line) for line in lines)


def event_from(record: dict[str, Any]) -> VEvent:
    """Build a :class:`VEvent` from a schedule record dict (§24.16).

    Reads ``uid``/``summary``/``dtstart``/``dtend``/``description`` keys, coercing to
    ``str`` and defaulting missing text to ``""``; a missing or ``None`` ``dtend`` stays
    ``None`` so no ``DTEND`` line is emitted — запись расписания в событие.
    """
    dtend_raw = record.get("dtend")
    return VEvent(
        uid=str(record.get("uid", "")),
        summary=str(record.get("summary", "")),
        dtstart=str(record.get("dtstart", "")),
        dtend=None if dtend_raw is None else str(dtend_raw),
        description=str(record.get("description", "")),
    )


def to_ics(events: Sequence[VEvent], prodid: str = "-//science-ball//EN") -> str:
    """Wrap events in a ``VCALENDAR`` skeleton -> a full ``.ics`` document (§24.16).

    Emits a ``BEGIN:VCALENDAR``/``VERSION:2.0``/``PRODID`` header, each event's
    :meth:`VEvent.to_ical` block, then ``END:VCALENDAR`` — all joined by CRLF. Empty
    ``events`` still yields a valid (event-less) skeleton — пустой, но валидный VCALENDAR.
    """
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{prodid}",
    ]
    parts = [_CRLF.join(fold_line(line) for line in header)]
    parts.extend(event.to_ical() for event in events)
    parts.append("END:VCALENDAR")
    return _CRLF.join(parts)
