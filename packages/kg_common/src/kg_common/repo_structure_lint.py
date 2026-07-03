"""Monorepo tree linter — базовая структура репозитория (§2.1 / §6.1).

The Science-Ball monorepo (§6.1) fixes a top-level layout: seven ``apps/*``
services, a ``frontend`` app, five ``packages/kg_*`` libraries and a shared
``infra`` root. When a required directory silently disappears (a bad merge, a
missed ``git add``) downstream tooling breaks with confusing errors. Эта модуль
сверяет фактическое дерево с эталонным списком §6.1 и заранее сообщает, каких
директорий не хватает, чтобы CI мог провалиться с понятным сообщением.

Public API:

* :data:`REQUIRED_DIRS`   — frozenset эталонных путей §6.1.
* :class:`StructureReport` — frozen ``{missing, present, ok}`` + ``as_dict``.
* :func:`check_structure` — фактическое дерево → :class:`StructureReport`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "REQUIRED_DIRS",
    "StructureReport",
    "check_structure",
]

REQUIRED_DIRS: frozenset[str] = frozenset(
    {
        "apps/api-gateway",
        "apps/agent-service",
        "apps/ingestion-service",
        "apps/graph-service",
        "apps/search-service",
        "apps/extraction-service",
        "apps/curation-service",
        "apps/frontend",
        "packages/kg_schema",
        "packages/kg_extractors",
        "packages/kg_retrievers",
        "packages/kg_eval",
        "packages/kg_common",
        "infra",
    }
)
"""Эталонные top-level директории монорепо (§6.1)."""


@dataclass(frozen=True, slots=True)
class StructureReport:
    """Отчёт линтера структуры — missing + present + ok-флаг (§2.1)."""

    missing: tuple[str, ...]
    present: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        """Сериализуемое представление — JSON-friendly dict."""
        return {
            "missing": list(self.missing),
            "present": list(self.present),
            "ok": bool(self.ok),
        }


def _normalize(path: str) -> str:
    """Нормализовать путь — убрать хвостовой ``/`` (``infra/`` → ``infra``)."""
    return path.rstrip("/")


def check_structure(
    existing: Iterable[str],
    required: Iterable[str] = REQUIRED_DIRS,
) -> StructureReport:
    """Сверить фактическое дерево с эталоном §6.1 → :class:`StructureReport`.

    Paths are normalized (trailing ``/`` stripped) on both sides, so a supplied
    ``infra/`` matches the required ``infra``. Extra unrelated paths in
    ``existing`` are ignored. ``missing`` and ``present`` are sorted tuples;
    ``ok`` is ``True`` iff nothing is missing.
    """
    have = {_normalize(p) for p in existing}
    want = {_normalize(p) for p in required}

    missing = tuple(sorted(want - have))
    present = tuple(sorted(want & have))
    return StructureReport(missing=missing, present=present, ok=not missing)
