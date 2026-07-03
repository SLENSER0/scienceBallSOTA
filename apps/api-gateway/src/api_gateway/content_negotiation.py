"""HTTP ``Accept`` content negotiation for documents/pages (§14.9).

Разбор заголовка ``Accept`` и выбор media type для эндпойнтов
``documents/pages/{page}``: клиент присылает ``Accept: text/html,
application/json;q=0.9``, сервер отдаёт HTML или JSON в зависимости от
предпочтений. Чистый stdlib, без FastAPI/Starlette.

Parses the ``Accept`` header and negotiates a media type for the
``documents/pages/{page}`` endpoints. Pure standard library:

* :class:`MediaRange`   — frozen ``{type, subtype, q}`` carrier with ``as_dict()``.
* :func:`parse_accept`  — header → q-sorted tuple of :class:`MediaRange`.
* :func:`best_match`    — pick the best available media type (or ``None``).
* :func:`acceptable`    — is a concrete media type acceptable at all?

Missing or empty ``Accept`` is treated as ``*/*`` (everything acceptable).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_WILDCARD = "*"


def _clamp_q(value: float) -> float:
    """Зажать q в [0, 1] / clamp a quality value into ``[0.0, 1.0]``."""
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class MediaRange:
    """Неизменяемый разобранный элемент ``Accept`` / one parsed ``Accept`` range.

    Carries the ``type`` and ``subtype`` (either may be ``"*"``) plus the
    quality factor ``q`` (already clamped to ``[0.0, 1.0]``). :meth:`as_dict`
    gives a plain field view for logging and assertions.
    """

    type: str
    subtype: str
    q: float

    def as_dict(self) -> dict[str, object]:
        """Обычный dict полей / plain field dict for logging and assertions."""
        return {"type": self.type, "subtype": self.subtype, "q": self.q}

    def specificity(self) -> int:
        """Точность диапазона: ``*/*``=0, ``t/*``=1, ``t/s``=2 (§14.9).

        Concrete ``type``/``subtype`` beat wildcards, so ``text/html`` sorts
        ahead of ``text/*`` which sorts ahead of ``*/*`` at equal ``q``.
        """
        return (self.type != _WILDCARD) + (self.subtype != _WILDCARD)

    def matches(self, media_type: str) -> bool:
        """Покрывает ли диапазон конкретный media type / does it cover it.

        ``*/*`` matches anything, ``type/*`` matches any subtype of ``type``,
        and ``type/subtype`` matches only that exact pair (case-insensitive).
        """
        mtype, _, msub = media_type.strip().lower().partition("/")
        if self.type == _WILDCARD and self.subtype == _WILDCARD:
            return True
        if self.type != mtype:
            return False
        return self.subtype in (_WILDCARD, msub)


def _parse_q(params: list[str]) -> float:
    """Достать ``q`` из параметров, иначе 1.0 / read ``q`` from params.

    Scans ``;``-separated params for ``q=<float>``; a missing or malformed
    value defaults to ``1.0``. The result is clamped to ``[0.0, 1.0]``.
    """
    for param in params:
        key, sep, value = param.partition("=")
        if sep and key.strip().lower() == "q":
            try:
                return _clamp_q(float(value.strip()))
            except ValueError:
                return 1.0
    return 1.0


def parse_accept(header: str) -> tuple[MediaRange, ...]:
    """Разобрать ``Accept`` в q-сортированный кортеж диапазонов (§14.9).

    Splits ``header`` on commas, parses each ``type/subtype;q=..`` element,
    clamps ``q`` to ``[0.0, 1.0]`` and sorts by ``q`` descending then by
    specificity descending (stable, so original order breaks final ties).
    An empty or whitespace-only header is treated as a single ``*/*`` range.
    """
    if not header or not header.strip():
        return (MediaRange(_WILDCARD, _WILDCARD, 1.0),)
    ranges: list[MediaRange] = []
    for raw in header.split(","):
        part = raw.strip()
        if not part:
            continue
        media, *params = part.split(";")
        mtype, _, msub = media.strip().lower().partition("/")
        if not mtype:
            continue
        if not msub:
            msub = _WILDCARD
        ranges.append(MediaRange(mtype, msub, _parse_q(params)))
    ranges.sort(key=lambda mr: (mr.q, mr.specificity()), reverse=True)
    return tuple(ranges)


def best_match(header: str, available: Sequence[str]) -> str | None:
    """Лучший media type из ``available`` под ``Accept`` (§14.9).

    Returns the entry of ``available`` whose best-matching range has the
    highest ``q`` (``q == 0`` means "not acceptable" and never wins). Ties are
    broken by the order of ``available``. Returns ``None`` when nothing matches.
    """
    ranges = parse_accept(header)
    best: str | None = None
    best_q = 0.0
    for candidate in available:
        candidate_q = 0.0
        for mr in ranges:
            if mr.matches(candidate) and mr.q > candidate_q:
                candidate_q = mr.q
        if candidate_q > best_q:
            best_q = candidate_q
            best = candidate
    return best


def acceptable(header: str, media_type: str) -> bool:
    """Приемлем ли ``media_type`` при данном ``Accept`` / is it acceptable.

    ``True`` when some parsed range matches ``media_type`` with ``q > 0``;
    an empty/missing header (``*/*``) makes everything acceptable.
    """
    return any(mr.matches(media_type) and mr.q > 0.0 for mr in parse_accept(header))
