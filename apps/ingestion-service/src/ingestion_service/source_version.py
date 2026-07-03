"""Source version decision policy for idempotent upload + logical-key versioning (§5.4).

On upload the ingestion service must decide, from the new file's content hash and its
logical key (e.g. a stable filename/document identity), whether the file is a brand-new
source, a byte-identical duplicate of something already ingested, or a fresh version of an
existing logical source. ``SourceRegistry`` carries no version column yet, so this is a
pure, side-effect-free decision policy: given the candidate keys and the existing registry
rows, it yields a :class:`VersionDecision` the caller can act on (insert / skip / re-version).

Политика версионирования источника при загрузке (§5.4): по хешу содержимого и логическому
ключу файла решает, новый ли это источник, точный дубликат или новая версия существующего.
Чистая функция без побочных эффектов — реестр источников ещё не имеет колонки версии.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VersionDecision:
    """Outcome of the §5.4 upload decision: what to do with the incoming file.

    ``action`` is one of ``'new_source'``, ``'duplicate'`` or ``'new_version'``.
    ``version`` is the version number to assign (or echo, for a duplicate).
    ``duplicate`` is True only when a byte-identical file already exists.
    ``source_id`` echoes the existing row on a duplicate, else None.

    Результат решения о версии: действие, номер версии, признак дубликата, id источника.
    """

    action: str
    version: int
    duplicate: bool
    source_id: str | None

    def as_dict(self) -> dict[str, Any]:
        """Serialise this decision to a plain JSON-safe dict."""
        return {
            "action": self.action,
            "version": self.version,
            "duplicate": self.duplicate,
            "source_id": self.source_id,
        }


def decide_version(
    file_hash: str,
    logical_key: str,
    existing: list[dict[str, Any]],
) -> VersionDecision:
    """Decide new-source / duplicate / new-version for an uploaded file (§5.4).

    ``existing`` is the current registry state: each row is a dict with keys
    ``file_hash`` / ``logical_key`` / ``version`` / ``source_id``. Decision order:

    1. Any row whose ``file_hash`` matches -> ``'duplicate'`` (echo its version/source_id,
       never incrementing the version) — idempotent re-upload.
    2. Else any row sharing ``logical_key`` -> ``'new_version'`` at ``max(version)+1``.
    3. Else -> ``'new_source'`` at version 1.

    Решает: точный дубликат по хешу (идемпотентно), иначе новая версия того же логического
    ключа (max+1), иначе — совершенно новый источник (версия 1).
    """
    for row in existing:
        if row.get("file_hash") == file_hash:
            row_version = int(row.get("version", 1))
            return VersionDecision(
                action="duplicate",
                version=row_version,
                duplicate=True,
                source_id=row.get("source_id"),
            )

    same_key_versions = [
        int(row.get("version", 1)) for row in existing if row.get("logical_key") == logical_key
    ]
    if same_key_versions:
        return VersionDecision(
            action="new_version",
            version=max(same_key_versions) + 1,
            duplicate=False,
            source_id=None,
        )

    return VersionDecision(
        action="new_source",
        version=1,
        duplicate=False,
        source_id=None,
    )
