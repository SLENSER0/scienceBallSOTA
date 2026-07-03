"""Build the §5.5/§5.7 document parse manifest (``manifest.json``).

A parse manifest is the compact, serialisable record emitted when the ingestion
pipeline (§5) finishes parsing one source document: which parser/OCR ran, how many
pages and structural elements were extracted, per-artifact checksums, and the sorted
list of object-store artifact keys the parse produced. It is written next to the
parsed artifacts and read back by downstream chunking/indexing stages.

Сборка манифеста разбора документа (§5.5/§5.7): парсер, флаг OCR, число страниц,
разделов, таблиц, рисунков и изображений, контрольные суммы и ключи артефактов.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ParseManifest:
    """Immutable record describing one completed document parse (§5.5/§5.7).

    Неизменяемое описание завершённого разбора одного документа.
    """

    doc_id: str
    parser_used: str
    ocr_used: bool
    page_count: int
    n_sections: int
    n_tables: int
    n_figures: int
    n_images: int
    checksums: dict[str, str] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Serialise the manifest to a plain JSON-safe dict.

        Сериализация манифеста в обычный dict.
        """
        return {
            "doc_id": self.doc_id,
            "parser_used": self.parser_used,
            "ocr_used": self.ocr_used,
            "page_count": self.page_count,
            "n_sections": self.n_sections,
            "n_tables": self.n_tables,
            "n_figures": self.n_figures,
            "n_images": self.n_images,
            "checksums": dict(self.checksums),
            "artifacts": list(self.artifacts),
        }

    def to_json(self) -> str:
        """Render the manifest as a deterministic, sorted-key JSON string.

        Представление манифеста в виде JSON-строки с отсортированными ключами.
        """
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> ParseManifest:
        """Rebuild a manifest from :meth:`to_json` output (round-trips to equality).

        Восстановление манифеста из JSON-строки (обратная к ``to_json``).
        """
        data = json.loads(s)
        return cls(
            doc_id=str(data["doc_id"]),
            parser_used=str(data["parser_used"]),
            ocr_used=bool(data["ocr_used"]),
            page_count=int(data["page_count"]),
            n_sections=int(data["n_sections"]),
            n_tables=int(data["n_tables"]),
            n_figures=int(data["n_figures"]),
            n_images=int(data["n_images"]),
            checksums={str(k): str(v) for k, v in dict(data.get("checksums", {})).items()},
            artifacts=tuple(str(a) for a in data.get("artifacts", ())),
        )


def build_manifest(
    doc_id: str,
    parser_used: str,
    page_count: int,
    n_sections: int,
    n_tables: int,
    n_figures: int,
    n_images: int,
    artifact_keys: list[str],
    checksums: dict[str, str] | None = None,
    ocr_used: bool = False,
) -> ParseManifest:
    """Assemble a :class:`ParseManifest`, de-duplicating and sorting artifact keys.

    ``artifact_keys`` are normalised into a sorted, unique tuple; ``checksums`` defaults
    to an empty dict (never ``None``); ``ocr_used`` defaults to ``False``.

    Сборка манифеста: ключи артефактов дедуплицируются и сортируются; контрольные
    суммы по умолчанию — пустой dict.
    """
    artifacts = tuple(sorted(set(artifact_keys)))
    return ParseManifest(
        doc_id=doc_id,
        parser_used=parser_used,
        ocr_used=ocr_used,
        page_count=page_count,
        n_sections=n_sections,
        n_tables=n_tables,
        n_figures=n_figures,
        n_images=n_images,
        checksums=dict(checksums) if checksums else {},
        artifacts=artifacts,
    )
