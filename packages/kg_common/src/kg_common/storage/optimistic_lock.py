"""Оптимистичная блокировка версий — optimistic concurrency check (§16.9).

HTTP-mutating endpoints (PUT/PATCH/DELETE над узлом или записью) защищаются
optimistic concurrency control: клиент присылает ``expected_version`` (эквивалент
заголовка ``If-Match`` с ETag), а сервер сравнивает его с текущей версией ресурса
перед записью. Это исключает потерянные обновления (lost update) при конкурентной
правке — двух кураторов, редактирующих один узел, — не удерживая блокировку в БД.

Семантика / semantics:

* ``expected_version is None`` — предусловие не задано: запись разрешена
  (``ok=True``, ``status=200``). Для мутаций, где версия обязательна, вызывающий
  передаёт ``require=True`` — тогда отсутствие версии даёт ``428 Precondition
  Required`` (клиент обязан прислать ``If-Match``).
* ``expected_version == current_version`` — совпадение: запись разрешена (200).
* ``expected_version != current_version`` — рассинхронизация: ``409 Conflict``
  (ресурс изменён кем-то другим; клиент должен перечитать и повторить).

Модуль чистый и backend-agnostic: он не трогает хранилище, а лишь возвращает
:class:`ConcurrencyCheck`. Вызывающий на ``ok`` выполняет запись и присваивает
:func:`next_version`, иначе отдаёт ``status`` наружу как HTTP-ответ.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# HTTP statuses (§16.9) --------------------------------------------------------
_OK = 200
_CONFLICT = 409  # версия рассинхронизирована / stale expected_version
_PRECONDITION_REQUIRED = 428  # мутация без обязательного If-Match


@dataclass(frozen=True)
class ConcurrencyCheck:
    """Результат проверки optimistic-lock — outcome of a version precondition (§16.9).

    :param ok: whether the mutating write is allowed to proceed.
    :param status: HTTP status to surface (200 ok, 409 conflict, 428 precondition).
    :param current_version: the resource's current stored version (echoed back).
    :param expected_version: the caller-supplied ``If-Match`` version (``-1`` if none).
    :param detail: human-readable reason — непустая строка при отказе (409/428).
    """

    ok: bool
    status: int
    current_version: int
    expected_version: int
    detail: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-dict view — сериализуемое представление результата."""
        return asdict(self)


def check_version(
    current_version: int,
    expected_version: int | None,
    *,
    require: bool = False,
) -> ConcurrencyCheck:
    """Compare ``expected_version`` against ``current_version`` (§16.9).

    Проверяет предусловие ``If-Match`` перед мутацией:

    * ``expected_version is None`` and not ``require`` — предусловие не задано,
      запись разрешена (``ok=True``, 200).
    * ``expected_version is None`` and ``require`` — обязательный ``If-Match``
      отсутствует: ``428 Precondition Required`` (``ok=False``).
    * ``expected_version == current_version`` — совпадение, запись разрешена (200).
    * otherwise — рассинхронизация: ``409 Conflict`` (``ok=False``).

    :param current_version: the resource's current stored version.
    :param expected_version: caller-supplied version, or ``None`` when omitted.
    :param require: if true, a missing ``expected_version`` is a 428 error.
    :returns: a frozen :class:`ConcurrencyCheck` echoing both versions.
    """
    echoed = -1 if expected_version is None else expected_version

    if expected_version is None:
        if require:
            return ConcurrencyCheck(
                ok=False,
                status=_PRECONDITION_REQUIRED,
                current_version=current_version,
                expected_version=echoed,
                detail=(
                    "precondition required: If-Match / expected_version is mandatory "
                    "for this mutation — предусловие версии обязательно"
                ),
            )
        return ConcurrencyCheck(
            ok=True,
            status=_OK,
            current_version=current_version,
            expected_version=echoed,
            detail="",
        )

    if expected_version == current_version:
        return ConcurrencyCheck(
            ok=True,
            status=_OK,
            current_version=current_version,
            expected_version=echoed,
            detail="",
        )

    return ConcurrencyCheck(
        ok=False,
        status=_CONFLICT,
        current_version=current_version,
        expected_version=echoed,
        detail=(
            f"version conflict: expected {expected_version} but current is "
            f"{current_version} — ресурс изменён, перечитайте и повторите"
        ),
    )


def next_version(current_version: int) -> int:
    """Return the version to store after a successful write — ``current + 1`` (§16.9)."""
    return current_version + 1
