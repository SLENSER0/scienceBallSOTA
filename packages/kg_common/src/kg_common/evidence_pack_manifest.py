"""Reproducible evidence-pack manifest — манифест доказательного пакета (§23.29).

An *evidence pack* bundles a set of in-memory files (``name -> bytes``) that back
a claim, an export, or an audit result. To make such a pack *reproducible* and
*verifiable*, this module builds a deterministic cryptographic **manifest** over
those files, so anyone can later re-hash the bytes and confirm nothing changed
(«манифест фиксирует контрольные суммы для воспроизводимости»).

Everything here is pure standard library (``hashlib`` + ``json``), deterministic
and side-effect free — no wall-clock, no I/O, no randomness. The same set of
files always yields byte-identical output regardless of insertion order.

Manifest layout:

* Each file contributes a :class:`FileEntry` ``{name, sha256, size}``.
* Entries are sorted lexicographically by ``name`` so the manifest is canonical.
* ``root_sha256`` is the SHA-256 of the concatenation of ``"name:sha256\\n"``
  lines (in sorted order) — a single digest committing to the whole pack.
* ``total_bytes`` is the sum of all file sizes.

Public API:

* :class:`FileEntry`     — frozen ``{name, sha256, size}`` with :meth:`as_dict`.
* :class:`PackManifest`  — frozen manifest with :meth:`as_dict` / :meth:`to_json`.
* :data:`EMPTY_SHA256`   — the well-known SHA-256 of the empty byte string.
* :func:`sha256_hex`     — SHA-256 hex digest of raw bytes.
* :func:`build_manifest` — build a :class:`PackManifest` from a file mapping.
* :func:`verify`         — re-hash files and report mismatched/missing names.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EMPTY_SHA256",
    "FileEntry",
    "PackManifest",
    "build_manifest",
    "sha256_hex",
    "verify",
]

#: Well-known SHA-256 hex digest of ``b""`` — эталон пустой строки (§23.29).
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: Default manifest schema version — версия схемы манифеста (§23.29).
DEFAULT_SCHEMA_VERSION = "1"


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data`` — hex-дайджест байтов (§23.29)."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FileEntry:
    """One file's checksum record — запись контрольной суммы файла (§23.29).

    Attributes:
        name: Logical file name within the pack — имя файла в пакете.
        sha256: SHA-256 hex digest of the file's bytes — дайджест содержимого.
        size: Size of the file in bytes — размер в байтах.
    """

    name: str
    sha256: str
    size: int

    def as_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` view — словарное представление (§23.29)."""
        return {"name": self.name, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class PackManifest:
    """Deterministic manifest over an evidence pack — манифест пакета (§23.29).

    Attributes:
        entries: File entries sorted by ``name`` — записи, отсортированные по имени.
        total_bytes: Sum of all file sizes — суммарный размер в байтах.
        root_sha256: Digest committing to the whole pack — корневой дайджест.
        schema_version: Manifest schema version — версия схемы манифеста.
    """

    entries: tuple[FileEntry, ...]
    total_bytes: int
    root_sha256: str
    schema_version: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` view — словарное представление (§23.29)."""
        return {
            "schema_version": self.schema_version,
            "root_sha256": self.root_sha256,
            "total_bytes": self.total_bytes,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def to_json(self) -> str:
        """Return canonical sorted-keys JSON — канонический JSON (§23.29)."""
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def _root_digest(entries: tuple[FileEntry, ...]) -> str:
    """SHA-256 over ``"name:sha256\\n"`` lines — корневой дайджест (§23.29)."""
    lines = "".join(f"{entry.name}:{entry.sha256}\n" for entry in entries)
    return sha256_hex(lines.encode("utf-8"))


def build_manifest(
    files: Mapping[str, bytes],
    *,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> PackManifest:
    """Build a :class:`PackManifest` from ``files`` — построить манифест (§23.29).

    Entries are sorted lexicographically by name, so the result is independent
    of the mapping's insertion order («порядок вставки не влияет на манифест»).
    """
    entries = tuple(
        FileEntry(name=name, sha256=sha256_hex(files[name]), size=len(files[name]))
        for name in sorted(files)
    )
    total_bytes = sum(entry.size for entry in entries)
    return PackManifest(
        entries=entries,
        total_bytes=total_bytes,
        root_sha256=_root_digest(entries),
        schema_version=schema_version,
    )


def verify(
    manifest: PackManifest,
    files: Mapping[str, bytes],
) -> tuple[bool, tuple[str, ...]]:
    """Re-hash ``files`` against ``manifest`` — проверить пакет (§23.29).

    Returns ``(ok, mismatched_names)`` where ``mismatched_names`` is the sorted
    tuple of manifest entries whose bytes are missing or whose digest no longer
    matches. Extra files in ``files`` that are absent from the manifest are
    ignored — only manifest names are checked («проверяются только имена из
    манифеста»).
    """
    mismatched: list[str] = []
    for entry in manifest.entries:
        data = files.get(entry.name)
        if data is None or sha256_hex(data) != entry.sha256:
            mismatched.append(entry.name)
    mismatched.sort()
    return (not mismatched, tuple(mismatched))
