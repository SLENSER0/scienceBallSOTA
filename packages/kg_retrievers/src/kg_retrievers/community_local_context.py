"""GraphRAG local-search context builder (§11.7).

GraphRAG local search собирает контекст для LLM из нескольких источников —
community reports (отчёты по кластерам), entities (сущности), relationships
(связи) и text units (фрагменты-источники) — и укладывает их в общий бюджет
токенов (token budget) в фиксированном порядке секций.

This module is a pure-python, offline-safe builder: it takes four scored lists
and packs their text lines into a :class:`LocalContext` in the fixed section
order ``['reports', 'entities', 'relationships', 'sources']`` (the ``text_units``
list maps to the ``'sources'`` section). Within each section items are ordered by
score descending; lines are appended, section by section, while the running token
estimate (``len(text) // chars_per_token``) stays within ``budget_tokens``. Every
item that cannot fit is left out and counted in ``dropped``. No store, no LLM,
no clock — deterministic given identical inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Fixed §11.7 section order. ``text_units`` is exposed to callers as ``sources``.
SECTION_ORDER: tuple[str, ...] = ("reports", "entities", "relationships", "sources")


@dataclass(frozen=True)
class LocalContext:
    """Token-budgeted local-search context (§11.7), sections in fixed order.

    Attributes:
        sections: ordered tuple of ``(name, lines)`` pairs, one per §11.7 section
            (``reports``/``entities``/``relationships``/``sources``); ``lines`` are
            the text lines that fit within the budget, in score-descending order.
        used_tokens: cumulative estimated tokens of all included lines
            (``sum(len(text) // chars_per_token)``); always ``<= budget_tokens``.
        dropped: number of scored items that did not fit and were excluded.
    """

    sections: tuple[tuple[str, tuple[str, ...]], ...]
    used_tokens: int
    dropped: int

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict; each section → name + lines list."""
        return {
            "sections": [{"name": name, "lines": list(lines)} for name, lines in self.sections],
            "used_tokens": self.used_tokens,
            "dropped": self.dropped,
        }


def _est_tokens(text: str, chars_per_token: int) -> int:
    """Estimate token count of ``text`` as ``len(text) // chars_per_token`` (§11.7)."""
    return len(text) // chars_per_token


def _order_by_score(items: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """Return items sorted by score descending (stable for equal scores)."""
    return sorted(items, key=lambda it: it[2], reverse=True)


def build_local_context(
    *,
    reports: list[tuple[str, str, float]],
    entities: list[tuple[str, str, float]],
    relationships: list[tuple[str, str, float]],
    text_units: list[tuple[str, str, float]],
    budget_tokens: int,
    chars_per_token: int = 4,
) -> LocalContext:
    """Build a token-budgeted local-search context in fixed section order (§11.7).

    Each of the four inputs is a list of ``(id, text, score)`` triples. Section order
    is always ``['reports', 'entities', 'relationships', 'sources']`` (``text_units``
    becomes ``sources``). Within a section items are ordered by score descending; the
    text of each item is appended as a line while the cumulative estimated token count
    (``len(text) // chars_per_token``) stays ``<= budget_tokens``. Any item whose text
    would push the running total over the budget is skipped and counted in ``dropped``;
    later items in the same or subsequent sections that still fit are kept.

    Empty sections still appear (with no lines), preserving the fixed order. All-empty
    inputs yield ``used_tokens == 0`` and ``dropped == 0``.
    """
    raw_sections: tuple[tuple[str, list[tuple[str, str, float]]], ...] = (
        ("reports", reports),
        ("entities", entities),
        ("relationships", relationships),
        ("sources", text_units),
    )
    built: list[tuple[str, tuple[str, ...]]] = []
    used_tokens = 0
    dropped = 0
    for name, items in raw_sections:
        lines: list[str] = []
        for _id, text, _score in _order_by_score(list(items)):
            cost = _est_tokens(text, chars_per_token)
            if used_tokens + cost <= budget_tokens:
                lines.append(text)
                used_tokens += cost
            else:
                dropped += 1
        built.append((name, tuple(lines)))
    return LocalContext(sections=tuple(built), used_tokens=used_tokens, dropped=dropped)
