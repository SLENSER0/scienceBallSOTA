"""§11.3 GraphRAG input manifest — стабильный реестр документов корпуса (pure python).

Перед запуском GraphRAG-индексации корпус документов нужно свести к детерминированному
**манифесту**: у каждого выжившего документа появляется стабильный
``graphrag_document_id`` (``f'{doc_id}.txt'``), а «мусор» (дубли по контенту и явно
отклонённые ревью) отсекается и попадает в ``filtered_out`` — чтобы решение было
воспроизводимым и хендл-чекаемым.

- :class:`ManifestEntry` — один выживший документ (frozen), с :meth:`~ManifestEntry.as_dict`.
- :class:`CorpusManifest` — весь манифест сборки ``build_id`` (frozen), с
  :meth:`~CorpusManifest.as_dict`.
- :func:`build_manifest` — строит манифест: присваивает ``graphrag_document_id``, дедупит
  по ``file_hash`` (оставляя первое вхождение), отбрасывает ``review_status`` из
  ``drop_status``. Порядок выживших = порядок входа (stable).
- :func:`reverse_lookup` — обратный поиск ``graphrag_document_id`` → ``doc_id`` (или None).

Pure python — no numpy, no store/graph/DB access: на вход уже прочитанные doc-``dict``.
Kuzu note: custom node props are NOT queryable columns — callers RETURN base columns and
read the rest via ``get_node()`` before assembling the doc dicts fed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Дефолт §11.3: review_status, при которых документ выбрасывается из корпуса.
DEFAULT_DROP_STATUS: tuple[str, ...] = ("rejected",)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """Один выживший документ манифеста / a single surviving corpus document (§11.3)."""

    doc_id: str
    graphrag_document_id: str
    source_path: str
    file_hash: str
    source_type: str

    def as_dict(self) -> dict[str, str]:
        """Сериализовать запись в плоский dict / flatten the entry to a plain dict (§11.3)."""
        return {
            "doc_id": self.doc_id,
            "graphrag_document_id": self.graphrag_document_id,
            "source_path": self.source_path,
            "file_hash": self.file_hash,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class CorpusManifest:
    """Манифест корпуса для одной сборки / corpus manifest for one build (§11.3)."""

    build_id: str
    entries: list[ManifestEntry]
    filtered_out: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать манифест целиком / serialize the whole manifest (§11.3)."""
        return {
            "build_id": self.build_id,
            "entries": [e.as_dict() for e in self.entries],
            "filtered_out": list(self.filtered_out),
        }


def build_manifest(
    build_id: str,
    docs: list[dict],
    *,
    drop_status: tuple = DEFAULT_DROP_STATUS,
) -> CorpusManifest:
    """Построить манифест корпуса / build the corpus manifest (§11.3).

    Каждый ``doc`` — dict с ключами ``doc_id`` / ``file_hash`` / ``review_status`` /
    ``access_policy`` / ``source_type`` / ``source_path``. Правила:

    - ``graphrag_document_id`` = ``f'{doc_id}.txt'`` (стабильный, детерминированный);
    - дедуп по ``file_hash``: оставляем **первое** вхождение, дубли → ``filtered_out``;
    - если ``review_status in drop_status`` — документ исключается → ``filtered_out``;
    - порядок выживших записей повторяет порядок входа (stable).
    """
    drop: set[str] = set(drop_status)
    entries: list[ManifestEntry] = []
    filtered_out: list[str] = []
    seen_hashes: set[str] = set()

    for doc in docs:
        doc_id = doc["doc_id"]
        if doc.get("review_status") in drop:
            filtered_out.append(doc_id)
            continue
        file_hash = doc["file_hash"]
        if file_hash in seen_hashes:
            filtered_out.append(doc_id)
            continue
        seen_hashes.add(file_hash)
        entries.append(
            ManifestEntry(
                doc_id=doc_id,
                graphrag_document_id=f"{doc_id}.txt",
                source_path=doc["source_path"],
                file_hash=file_hash,
                source_type=doc["source_type"],
            )
        )

    return CorpusManifest(build_id=build_id, entries=entries, filtered_out=filtered_out)


def reverse_lookup(manifest: CorpusManifest, graphrag_document_id: str) -> str | None:
    """Обратный поиск ``graphrag_document_id`` → ``doc_id`` / reverse map (§11.3).

    Возвращает ``doc_id`` первой совпавшей записи или ``None``, если такого id нет.
    """
    for entry in manifest.entries:
        if entry.graphrag_document_id == graphrag_document_id:
            return entry.doc_id
    return None


__all__: Sequence[str] = (
    "DEFAULT_DROP_STATUS",
    "ManifestEntry",
    "CorpusManifest",
    "build_manifest",
    "reverse_lookup",
)
