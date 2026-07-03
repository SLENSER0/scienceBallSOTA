"""§5.8 Per-format parser priority resolver.

Config-driven per-format parser ordering that feeds
:func:`ingestion_service.parser_protocol.parse_with_fallback`. The fallback
orchestrator tries parsers *in order*; this module supplies the configurable
priority table (например, HTML предпочитает ``unstructured``, PDF — ``docling``)
so the order is data, not code.

Public surface:

- :class:`PriorityTable` — frozen ``order`` map (fmt → parser tuple) plus a
  ``default`` fallback tuple, with :meth:`PriorityTable.as_dict` для JSON;
- :data:`DEFAULT_TABLE` — shipped defaults (pdf/docx/pptx → ``docling`` first,
  html → ``unstructured`` first);
- :func:`resolve_order` — normalize a format (strip leading dot, lowercase) and
  return its ordered parser tuple, else :attr:`PriorityTable.default`;
- :func:`merge_overrides` — return a *new* table with per-format replacements.

Pure Python: no LLM / network / I/O. Works on RU + EN inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


def _normalize_fmt(fmt: str) -> str:
    """Normalize a format token: strip a leading dot, lowercase, trim.

    Приводит ``.PDF`` / ``pdf`` / `` PDF `` к каноническому ``pdf``.
    """

    return fmt.strip().lstrip(".").lower()


@dataclass(frozen=True)
class PriorityTable:
    """Per-format parser ordering (§5.8).

    - ``order``   — mapping *normalized fmt* → tuple of parser names, most
      preferred first (наиболее приоритетный парсер первым);
    - ``default`` — tuple used when a format is not listed in ``order``.

    The instance is frozen; :meth:`as_dict` yields a JSON-safe view.
    """

    order: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    default: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """JSON-safe view: ``order`` as dict-of-lists, ``default`` as list."""

        return {
            "order": {fmt: list(parsers) for fmt, parsers in self.order.items()},
            "default": list(self.default),
        }


#: Shipped defaults (§5.8): docling-first for office/pdf, unstructured-first for html.
DEFAULT_TABLE: PriorityTable = PriorityTable(
    order=MappingProxyType(
        {
            "pdf": ("docling", "unstructured", "default"),
            "docx": ("docling", "unstructured", "default"),
            "pptx": ("docling", "unstructured", "default"),
            "html": ("unstructured", "docling", "default"),
        }
    ),
    default=("default",),
)


def resolve_order(table: PriorityTable, fmt: str) -> tuple[str, ...]:
    """Return the ordered parser tuple for ``fmt`` (normalized), else default.

    Unknown formats fall back to :attr:`PriorityTable.default`.
    Неизвестный формат → ``table.default``.
    """

    return table.order.get(_normalize_fmt(fmt), table.default)


def merge_overrides(base: PriorityTable, overrides: Mapping[str, tuple[str, ...]]) -> PriorityTable:
    """Return a *new* :class:`PriorityTable` with per-format ``overrides`` applied.

    Only the listed formats are replaced; all others остаются как в ``base``.
    ``base`` is not mutated (frozen dataclass) — a fresh table is returned.
    Override keys are normalized and their parser sequences coerced to tuples.
    """

    merged: dict[str, tuple[str, ...]] = dict(base.order)
    for fmt, parsers in overrides.items():
        merged[_normalize_fmt(fmt)] = tuple(parsers)
    return PriorityTable(order=merged, default=base.default)
