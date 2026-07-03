"""Command palette (Cmd+K) index: build and rank nav targets (§17.5).

Фронтенд-независимый индекс для палитры команд (Cmd+K, §17.5). Собирает
единый список целей навигации из сущностей, сохранённых представлений,
недавних вопросов и статических маршрутов, а затем ранжирует их по запросу.
Неизменяемый frozen dataclass :class:`PaletteEntry` с :meth:`as_dict`
(camelCase-ключи). Скоринг совпадений по метке/ключевым словам:
префикс=3.0, начало слова=2.0, подстрока=1.0; без совпадения — исключается.
Регистр не учитывается, при равенстве баллов сохраняется исходный порядок.

A frontend-agnostic index backing the Cmd+K command palette (§17.5). It builds
a single list of navigation targets from entities, saved views, recent
questions and static routes, then ranks them against a query. The immutable
frozen :class:`PaletteEntry` exposes :meth:`as_dict` with camelCase keys.
Match scoring over label/keywords: prefix=3.0, word-start=2.0, substring=1.0;
no match is excluded. Matching is case-insensitive and ties keep input order.

* :class:`PaletteEntry` — frozen nav-target record with :meth:`as_dict`.
* :func:`build_palette` — assemble entries from the four source lists.
* :func:`rank_palette` — score/filter/order entries for a query.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

# Границы слов — пробелы и дефисы; скобки/пунктуация словами не считаются.
# Word boundaries are whitespace and hyphens only; parentheses/punctuation
# do not start a new word, so ``metal (al)`` matches ``al`` only as substring.
_WORD_SPLIT = re.compile(r"[\s\-]+")

_PREFIX = 3.0
_WORD_START = 2.0
_SUBSTRING = 1.0
_NO_MATCH = 0.0

_KINDS = ("entity", "saved_view", "question", "route")


@dataclass(frozen=True, slots=True)
class PaletteEntry:
    """Неизменяемая цель навигации палитры команд (§17.5).

    Immutable command-palette navigation target. ``keywords`` is a lower-cased
    tuple; ``score`` carries a relevance value (0.0 until :func:`rank_palette`
    assigns a match score).
    """

    id: str
    kind: str
    label: str
    subtitle: str
    route: str
    keywords: tuple[str, ...]
    score: float

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в JSON-совместимый dict с camelCase-ключами.

        Serialise to a JSON-ready ``dict`` using camelCase keys; ``keywords`` is
        emitted as a ``list``. The field names are already single words, so the
        camelCase keys coincide with the attribute names.
        """
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "subtitle": self.subtitle,
            "route": self.route,
            "keywords": list(self.keywords),
            "score": self.score,
        }


def _keywords(raw: Any) -> tuple[str, ...]:
    """Привести ключевые слова к нижнему регистру в виде кортежа.

    Normalise a raw keyword iterable to a lower-cased tuple of strings.
    """
    if not raw:
        return ()
    return tuple(str(kw).lower() for kw in raw)


def _entry(kind: str, row: Mapping[str, Any], default_route: str) -> PaletteEntry:
    """Построить :class:`PaletteEntry` из строки-источника заданного вида.

    Build a :class:`PaletteEntry` from a source ``row`` for the given ``kind``,
    using ``default_route`` unless the row supplies an explicit ``route``.
    """
    route = str(row.get("route") or default_route)
    return PaletteEntry(
        id=str(row["id"]),
        kind=kind,
        label=str(row["label"]),
        subtitle=str(row.get("subtitle", "")),
        route=route,
        keywords=_keywords(row.get("keywords")),
        score=float(row.get("score", 0.0)),
    )


def build_palette(
    entities: Sequence[Mapping[str, Any]],
    saved_views: Sequence[Mapping[str, Any]],
    recent_questions: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
) -> tuple[PaletteEntry, ...]:
    """Собрать единый список целей палитры из четырёх источников (§17.5).

    Assemble a unified palette from entities, saved views, recent questions and
    static routes. Each ``kind`` gets a sensible default route
    (``/entity/{id}``, ``/views/{id}``, ``/chat/{id}``, ``/{id}``) unless the
    source row provides ``route``. Keywords are lower-cased. Order follows the
    input: entities, then saved views, then questions, then routes.
    """
    out: list[PaletteEntry] = []
    for row in entities:
        out.append(_entry("entity", row, f"/entity/{row['id']}"))
    for row in saved_views:
        out.append(_entry("saved_view", row, f"/views/{row['id']}"))
    for row in recent_questions:
        out.append(_entry("question", row, f"/chat/{row['id']}"))
    for row in routes:
        out.append(_entry("route", row, f"/{row['id']}"))
    return tuple(out)


def _match_score(text: str, query: str) -> float:
    """Оценить совпадение одной строки с запросом (регистр уже нижний).

    Score how well ``text`` matches ``query`` (both already lower-cased):
    prefix=3.0, word-start=2.0, substring=1.0, otherwise 0.0.
    """
    if text.startswith(query):
        return _PREFIX
    for word in _WORD_SPLIT.split(text):
        if word.startswith(query):
            return _WORD_START
    if query in text:
        return _SUBSTRING
    return _NO_MATCH


def _entry_score(entry: PaletteEntry, query: str) -> float:
    """Лучший балл совпадения по метке и ключевым словам записи.

    The best match score across the entry's label and each keyword.
    """
    best = _match_score(entry.label.lower(), query)
    for keyword in entry.keywords:
        best = max(best, _match_score(keyword, query))
    return best


def rank_palette(
    entries: tuple[PaletteEntry, ...],
    query: str,
    *,
    limit: int = 20,
) -> tuple[PaletteEntry, ...]:
    """Отранжировать и отфильтровать записи палитры по запросу (§17.5).

    Score each entry over its label and keywords, drop non-matching entries and
    return up to ``limit`` in descending score with a stable original-order
    tie-break; the returned entries carry their computed match ``score``. An
    empty (or whitespace-only) query returns the first ``limit`` input entries
    unchanged, in input order.
    """
    normalized = query.strip().lower()
    if not normalized:
        return tuple(entries[:limit])

    scored: list[tuple[float, int, PaletteEntry]] = []
    for index, entry in enumerate(entries):
        score = _entry_score(entry, normalized)
        if score <= _NO_MATCH:
            continue
        scored.append((score, index, entry))

    # Сортировка по убыванию балла, при равенстве — исходный порядок (index).
    # Descending score; ties keep original input order via the stored index.
    scored.sort(key=lambda item: (-item[0], item[1]))
    return tuple(replace(entry, score=score) for score, _index, entry in scored[:limit])
