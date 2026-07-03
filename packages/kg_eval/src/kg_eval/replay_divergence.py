"""Reproducible evidence pack: replay-divergence comparator (§23.29).

Детерминированный «повтор» (replay) ответа должен воспроизводить оригинал
байт-в-байт по значимым полям. :func:`compare_replay` сравнивает оригинал и
повтор по трём осям — текст ответа (``answer_text``), цитаты (``citations`` как
множества) и происхождение (``provenance``: ``model_version`` / ``prompt_version``
/ ``schema_version`` / ``snapshot``) — и возвращает замороженный
:class:`DivergenceReport`. Дополнительно числовое содержимое ответа парсится
:func:`extract_numbers` и сравнивается по позициям: любое расхождение чисел
попадает в ``numbers_changed`` как строковая пара. Отчёт питает
воспроизводимостный гейт (reproducibility gate).

A deterministic replay of an answer must reproduce the original on the fields
that matter. :func:`compare_replay` diffs original vs replay across three axes —
``answer_text``, ``citations`` (as sets) and ``provenance`` — and returns a frozen
:class:`DivergenceReport`. Numeric content of the answer is parsed by
:func:`extract_numbers` and compared position-by-position; any mismatch is
recorded in ``numbers_changed`` as a stringified pair. The report feeds the
reproducibility gate.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Any

# Числовой токен: необязательный знак, дробная часть опциональна. Ловит
# ``180.5``, ``2``, ``-3.0`` и т.п. в порядке появления в тексте.
_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")

# Ключи блока provenance, которые сравниваются на равенство значений.
_PROVENANCE_KEYS = ("model_version", "prompt_version", "schema_version", "snapshot")


@dataclass(frozen=True)
class DivergenceReport:
    """Расхождения между оригиналом и повтором ответа (§23.29).

    ``identical`` is ``True`` iff every other field signals "no change": no text
    change, no numeric change, no citation added/removed, no provenance change.
    All tuple fields are sorted for determinism.
    """

    identical: bool
    answer_text_changed: bool
    numbers_changed: tuple[str, ...]
    citations_added: tuple[str, ...]
    citations_removed: tuple[str, ...]
    provenance_changed: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "identical": self.identical,
            "answer_text_changed": self.answer_text_changed,
            "numbers_changed": list(self.numbers_changed),
            "citations_added": list(self.citations_added),
            "citations_removed": list(self.citations_removed),
            "provenance_changed": list(self.provenance_changed),
        }


def extract_numbers(text: str) -> tuple[float, ...]:
    """Извлечь числовые токены из ``text`` по порядку → кортеж ``float`` (§23.29).

    Parses numeric tokens left-to-right, e.g.
    ``extract_numbers("hardness 180.5 MPa at 2 h") == (180.5, 2.0)``. Non-numeric
    text is ignored; a bare ``.`` or empty string yields ``()``.
    """
    return tuple(float(m.group()) for m in _NUMBER_RE.finditer(text))


def _as_str_set(value: Any) -> set[str]:
    """Привести значение цитат к множеству строк (пропущенный ключ → пусто)."""
    if value is None:
        return set()
    if isinstance(value, (str, bytes)):
        return {str(value)}
    if isinstance(value, (Set, list, tuple)):
        return {str(item) for item in value}
    return {str(value)}


def _number_diffs(original: str, replay: str) -> tuple[str, ...]:
    """Позиционное сравнение чисел двух текстов → строковые пары расхождений.

    Числа сравниваются по индексам; недостающая позиция обозначается ``None``.
    Каждое расхождение сериализуется как ``str((orig, replay))`` — устойчиво и
    проверяемо вручную.
    """
    orig_nums = extract_numbers(original)
    replay_nums = extract_numbers(replay)
    diffs: list[str] = []
    for i in range(max(len(orig_nums), len(replay_nums))):
        a = orig_nums[i] if i < len(orig_nums) else None
        b = replay_nums[i] if i < len(replay_nums) else None
        if a != b:
            diffs.append(str((a, b)))
    return tuple(diffs)


def _provenance_diffs(original: Mapping[str, Any], replay: Mapping[str, Any]) -> tuple[str, ...]:
    """Ключи provenance, чьи значения различаются (отсортированы)."""
    orig_prov = original.get("provenance") or {}
    replay_prov = replay.get("provenance") or {}
    changed = [key for key in _PROVENANCE_KEYS if orig_prov.get(key) != replay_prov.get(key)]
    return tuple(sorted(changed))


def compare_replay(original: Mapping[str, Any], replay: Mapping[str, Any]) -> DivergenceReport:
    """Сравнить детерминированный повтор с оригиналом → :class:`DivergenceReport`.

    Сопоставляются три поля: ``answer_text`` (равенство строк), ``citations``
    (как множества — добавленные/удалённые) и ``provenance`` (по ключам
    :data:`_PROVENANCE_KEYS`). Дополнительно числовое содержимое ответа
    сравнивается позиционно. ``identical`` истинно, только если ни одно поле не
    изменилось. Отсутствующий ключ ``citations`` трактуется как пустое множество.

    Compares ``answer_text``, ``citations`` (as sets) and ``provenance`` keys;
    numeric content of the answer is diffed position-by-position. ``identical`` is
    ``True`` only when nothing changed. A missing ``citations`` key is an empty set.
    """
    orig_text = original.get("answer_text", "")
    replay_text = replay.get("answer_text", "")
    answer_text_changed = orig_text != replay_text

    numbers_changed = _number_diffs(str(orig_text), str(replay_text))

    orig_cites = _as_str_set(original.get("citations"))
    replay_cites = _as_str_set(replay.get("citations"))
    citations_added = tuple(sorted(replay_cites - orig_cites))
    citations_removed = tuple(sorted(orig_cites - replay_cites))

    provenance_changed = _provenance_diffs(original, replay)

    identical = not (
        answer_text_changed
        or numbers_changed
        or citations_added
        or citations_removed
        or provenance_changed
    )
    return DivergenceReport(
        identical=identical,
        answer_text_changed=answer_text_changed,
        numbers_changed=numbers_changed,
        citations_added=citations_added,
        citations_removed=citations_removed,
        provenance_changed=provenance_changed,
    )
