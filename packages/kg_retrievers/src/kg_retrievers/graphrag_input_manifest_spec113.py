"""§11.3 GraphRAG input manifest (spec-113 variant) — frozen corpus manifest (pure python).

RU: Детерминированный **манифест** входа GraphRAG-индексации. Каждому выжившему
документу присваивается стабильный ``document_id`` (``f'{doc_id}.txt'``); дубли по
``file_hash`` (первое вхождение выигрывает) и явно отклонённые ревью документы
отбрасываются со счётчиками ``skipped_duplicate`` / ``skipped_rejected``. Записи
сортируются по ``doc_id`` по возрастанию — воспроизводимо и хендл-чекаемо.
EN: Deterministic input **manifest** for GraphRAG indexing. Each surviving document
gets a stable ``document_id`` (``f'{doc_id}.txt'``); duplicates by ``file_hash``
(first wins) and review-rejected documents are dropped with ``skipped_duplicate`` /
``skipped_rejected`` counters. Entries are sorted ascending by ``doc_id``.

- :class:`ManifestEntry` — один выживший документ (frozen), с :meth:`ManifestEntry.as_dict`.
- :class:`InputManifest` — весь манифест сборки ``build_id`` (frozen), с :meth:`as_dict`.
- :func:`build_manifest` — строит манифест: ``document_id``, дедуп, фильтр, сортировка.
- :func:`manifest_lookup` — ``document_id`` → :class:`ManifestEntry` (или ``None``).

Pure python — no numpy, no store/graph/DB access: на вход уже прочитанные doc-``dict``.
Kuzu note: custom node props are NOT queryable columns — callers RETURN base columns and
read the rest via ``get_node()`` before assembling the doc dicts fed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Дефолт §11.3: review_status, при которых документ исключается / default drop statuses.
DEFAULT_EXCLUDE_STATUS: tuple[str, ...] = ("rejected",)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """Один выживший документ манифеста / a single surviving corpus document (§11.3)."""

    doc_id: str
    document_id: str
    source_path: str
    file_hash: str
    source_type: str

    def as_dict(self) -> dict[str, str]:
        """Сериализовать запись в плоский dict / flatten the entry to a plain dict (§11.3)."""
        return {
            "doc_id": self.doc_id,
            "document_id": self.document_id,
            "source_path": self.source_path,
            "file_hash": self.file_hash,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class InputManifest:
    """Манифест входа для одной сборки / input manifest for one build (§11.3)."""

    build_id: str
    entries: tuple[ManifestEntry, ...]
    skipped_rejected: int
    skipped_duplicate: int

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать манифест целиком / serialize the whole manifest (§11.3).

        ``entries`` возвращается как ``list`` из плоских ``dict`` — round-trip через
        ``json.dumps`` без потерь / entries become a list of plain dicts.
        """
        return {
            "build_id": self.build_id,
            "entries": [e.as_dict() for e in self.entries],
            "skipped_rejected": self.skipped_rejected,
            "skipped_duplicate": self.skipped_duplicate,
        }


def build_manifest(
    build_id: str,
    docs: list[dict],
    *,
    exclude_status: tuple = DEFAULT_EXCLUDE_STATUS,
) -> InputManifest:
    """Построить манифест входа / build the input manifest (§11.3).

    Каждый ``doc`` — dict с ключами ``doc_id`` / ``file_hash`` / ``source_path`` /
    ``source_type`` и опциональным ``review_status``. Правила:

    - ``document_id`` = ``f'{doc_id}.txt'`` (стабильный, детерминированный);
    - если ``review_status in exclude_status`` — исключается, ``skipped_rejected += 1``;
    - дедуп по ``file_hash``: остаётся **первое** вхождение (в порядке входа), дубли
      увеличивают ``skipped_duplicate``;
    - выжившие записи сортируются по ``doc_id`` по возрастанию (stable, детерминированно).
    """
    exclude: set[str] = set(exclude_status)
    survivors: list[ManifestEntry] = []
    seen_hashes: set[str] = set()
    skipped_rejected = 0
    skipped_duplicate = 0

    for doc in docs:
        if doc.get("review_status") in exclude:
            skipped_rejected += 1
            continue
        file_hash = doc["file_hash"]
        if file_hash in seen_hashes:
            skipped_duplicate += 1
            continue
        seen_hashes.add(file_hash)
        doc_id = doc["doc_id"]
        survivors.append(
            ManifestEntry(
                doc_id=doc_id,
                document_id=f"{doc_id}.txt",
                source_path=doc["source_path"],
                file_hash=file_hash,
                source_type=doc["source_type"],
            )
        )

    survivors.sort(key=lambda e: e.doc_id)
    return InputManifest(
        build_id=build_id,
        entries=tuple(survivors),
        skipped_rejected=skipped_rejected,
        skipped_duplicate=skipped_duplicate,
    )


def manifest_lookup(m: InputManifest, document_id: str) -> ManifestEntry | None:
    """Поиск записи по ``document_id`` / look up an entry by ``document_id`` (§11.3).

    Возвращает первую совпавшую :class:`ManifestEntry` или ``None``, если такого id нет.
    """
    for entry in m.entries:
        if entry.document_id == document_id:
            return entry
    return None


__all__: Sequence[str] = (
    "DEFAULT_EXCLUDE_STATUS",
    "ManifestEntry",
    "InputManifest",
    "build_manifest",
    "manifest_lookup",
)
