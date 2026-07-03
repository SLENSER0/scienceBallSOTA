"""Dataset-catalog JSON export + summary (§9.2/§10.4 catalog export).

Чистый, безсетевой экспорт каталога метаданных (dataset-catalog export) поверх
:mod:`kg_common.storage.metadata_dtos`: три списка DTO — *источники*
(:class:`~kg_common.storage.metadata_dtos.SourceMetadata`), *документы*
(:class:`~kg_common.storage.metadata_dtos.DocumentMetadata`) и *датасеты*
(:class:`~kg_common.storage.metadata_dtos.DatasetMetadata`) — сериализуются в
один детерминированный JSON-документ для файлового экспорта / round-trip.

:func:`catalog_to_json` даёт стабильный (``sort_keys=True``) снимок каталога;
:func:`catalog_from_json` восстанавливает DTO обратно через их ``from_dict``, так
что ``from_json(to_json(x)) == x``. :func:`catalog_summary` собирает компактную
сводку (:class:`CatalogSummary`) — счётчики и разбивку источников *by owner*
(по владельцу) — для дашбордов и проверок без разбора всего документа.

This module reads :mod:`kg_common.storage.metadata_dtos` by composition and
modifies no existing file — каждое поле DTO уже round-trippable-колонка там.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from kg_common.storage.metadata_dtos import (
    DatasetMetadata,
    DocumentMetadata,
    SourceMetadata,
)

__all__ = [
    "CatalogSummary",
    "catalog_from_json",
    "catalog_summary",
    "catalog_to_json",
]


def catalog_to_json(
    sources: Sequence[SourceMetadata],
    documents: Sequence[DocumentMetadata],
    datasets: Sequence[DatasetMetadata],
) -> str:
    """Serialise the three DTO lists to one deterministic JSON string (§10.4).

    Форма документа — ``{"sources": [...], "documents": [...], "datasets":
    [...]}``; порядок списков сохраняется как на входе, ключи внутри объектов
    сортируются (``sort_keys=True``), поэтому одинаковый вход даёт побайтово
    одинаковый выход. Разделители заданы явно (``", "`` / ``": "``) для
    стабильного, hand-checkable результата.
    """
    payload = {
        "sources": [s.as_dict() for s in sources],
        "documents": [d.as_dict() for d in documents],
        "datasets": [ds.as_dict() for ds in datasets],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(", ", ": "))


def catalog_from_json(
    text: str,
) -> tuple[list[SourceMetadata], list[DocumentMetadata], list[DatasetMetadata]]:
    """Rehydrate the three DTO lists from :func:`catalog_to_json` output (§10.4).

    Обратная операция к :func:`catalog_to_json`: каждый объект восстанавливается
    через ``from_dict`` соответствующего DTO, так что связка сохраняет типы и
    значения — ``from_json(to_json(x)) == x``.
    """
    data: Mapping[str, Any] = json.loads(text)
    sources = [SourceMetadata.from_dict(s) for s in data.get("sources", [])]
    documents = [DocumentMetadata.from_dict(d) for d in data.get("documents", [])]
    datasets = [DatasetMetadata.from_dict(ds) for ds in data.get("datasets", [])]
    return sources, documents, datasets


@dataclass(frozen=True)
class CatalogSummary:
    """Компактная сводка каталога — счётчики + разбивка by owner (§9.2).

    ``by_owner`` — количество *источников* на владельца (``owner``); пустая
    строка ``""`` означает незаполненного владельца. Frozen, поэтому сводку
    можно свободно передавать; :meth:`as_dict` даёт JSON-friendly представление.
    """

    n_sources: int
    n_documents: int
    n_datasets: int
    by_owner: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_sources": self.n_sources,
            "n_documents": self.n_documents,
            "n_datasets": self.n_datasets,
            "by_owner": dict(self.by_owner),
        }


def catalog_summary(
    sources: Sequence[SourceMetadata],
    documents: Sequence[DocumentMetadata],
    datasets: Sequence[DatasetMetadata],
) -> CatalogSummary:
    """Build a :class:`CatalogSummary` over the three DTO lists (§9.2/§10.4).

    Считает элементы каждого списка и разбивает *источники* по ``owner``.
    ``by_owner`` — обычный ``dict`` с отсортированными ключами (детерминизм),
    поэтому равные входы дают равные сводки.
    """
    owners = Counter(s.owner for s in sources)
    by_owner = {owner: owners[owner] for owner in sorted(owners)}
    return CatalogSummary(
        n_sources=len(sources),
        n_documents=len(documents),
        n_datasets=len(datasets),
        by_owner=by_owner,
    )
