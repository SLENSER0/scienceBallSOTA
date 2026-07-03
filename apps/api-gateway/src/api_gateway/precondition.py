"""Optimistic-concurrency preconditions for mutations (§14.9).

Проверка условных заголовков ``If-Match``/``If-Unmodified-Since`` на выбранных
мутациях (§14.9). Чистый stdlib: :func:`evaluate_if_match` реализует слабое
сравнение ETag (``None`` — нет условия → проход, ``*`` — проход если ресурс
существует, иначе слабонормализованный тег обязан совпасть),
:func:`evaluate_if_unmodified_since` парсит HTTP-дату через :mod:`email.utils`
и проходит, когда время правки ресурса ≤ указанной даты, а
:func:`check_preconditions` объединяет их в :class:`PreconditionResult`
(``200`` при успехе, ``412 Precondition Failed`` при провале).

Optimistic-concurrency ``If-Match``/``If-Unmodified-Since`` precondition checks
for the §14.9 mutations. Pure standard library:

* :func:`evaluate_if_match`            — weak ETag comparison (``None``/``*``/tag).
* :func:`evaluate_if_unmodified_since` — HTTP-date guard on last-modified epoch.
* :class:`PreconditionResult`          — frozen ``{passed, status}`` with ``as_dict``.
* :func:`check_preconditions`          — combine both into a 200-or-412 result.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

# HTTP status codes for the two outcomes (§14.9).
_STATUS_OK = 200
_STATUS_PRECONDITION_FAILED = 412


def _normalize(tag: str) -> str:
    """Снять префикс ``W/`` и кавычки для слабого сравнения / weak-compare form."""
    tag = tag.strip()
    if tag.startswith("W/"):
        tag = tag[2:].strip()
    return tag.strip('"')


def evaluate_if_match(if_match: str | None, current_etag: str | None) -> bool:
    """Проверить условие ``If-Match`` против текущего ETag ресурса (§14.9).

    ``None`` — заголовок отсутствует, условие всегда проходит. ``*`` проходит,
    когда ресурс существует (``current_etag`` не ``None``). Иначе значение может
    быть списком через запятую; проход, если хотя бы один слабонормализованный
    тег (без ``W/`` и кавычек) совпадает с текущим ETag.

    ``None`` means the header is absent and the precondition passes. ``*`` passes
    when the resource exists (non-``None`` ``current_etag``). Otherwise the value
    may be a comma list and passes when any weak-normalized tag equals the current
    ETag.
    """
    if if_match is None:
        return True
    current = None if current_etag is None else _normalize(current_etag)
    for candidate in if_match.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        if candidate == "*":
            return current is not None
        if current is not None and _normalize(candidate) == current:
            return True
    return False


def evaluate_if_unmodified_since(header: str | None, last_modified_epoch: int) -> bool:
    """Проверить условие ``If-Unmodified-Since`` по времени правки (§14.9).

    ``None`` — заголовок отсутствует, условие проходит. Иначе HTTP-дата
    разбирается через :func:`email.utils.parsedate_to_datetime`; условие
    проходит, когда время последней правки ресурса ≤ разобранной даты.
    Непарсибельная дата трактуется как непройденное условие.

    ``None`` means the header is absent and passes. Otherwise the HTTP-date is
    parsed via :func:`email.utils.parsedate_to_datetime` and the check passes
    when ``last_modified_epoch`` is at or before the parsed instant. An
    unparseable date fails closed.
    """
    if header is None:
        return True
    try:
        parsed = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return False
    if parsed is None:
        return False
    return last_modified_epoch <= int(parsed.timestamp())


@dataclass(frozen=True, slots=True)
class PreconditionResult:
    """Неизменяемый итог проверки предусловий мутации (§14.9).

    Frozen outcome of the precondition checks: ``passed`` is the combined verdict
    and ``status`` is ``200`` on success or ``412`` (Precondition Failed).
    """

    passed: bool
    status: int

    def as_dict(self) -> dict[str, Any]:
        """Итог как ``{passed, status}`` / plain field dict (§14.9)."""
        return {"passed": self.passed, "status": self.status}


def check_preconditions(
    if_match: str | None,
    if_unmodified_since: str | None,
    current_etag: str | None,
    last_modified_epoch: int,
) -> PreconditionResult:
    """Объединить ``If-Match`` и ``If-Unmodified-Since`` в один вердикт (§14.9).

    Оба заголовка должны пройти (отсутствующий заголовок проходит); при провале
    любого — ``412 Precondition Failed``, иначе ``200``.

    Both headers must pass (an absent header passes). If either fails the result
    is ``412 Precondition Failed``; otherwise ``200``.
    """
    passed = evaluate_if_match(if_match, current_etag) and evaluate_if_unmodified_since(
        if_unmodified_since, last_modified_epoch
    )
    status = _STATUS_OK if passed else _STATUS_PRECONDITION_FAILED
    return PreconditionResult(passed=passed, status=status)
