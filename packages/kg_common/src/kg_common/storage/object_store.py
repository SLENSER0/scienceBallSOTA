"""Local object store (§5.5): S3-like blob storage over the local filesystem.

§5.5 abstracts object storage behind a MinIO/S3-compatible surface. The
*embedded* profile ships no MinIO server, so blobs (raw docs, extracted
assets, exports — сырые документы, вложения, экспорты) live on the local
filesystem under a root directory, one subdirectory per bucket. The *server*
profile swaps this for a real S3/MinIO client behind the same API
(``put``/``get``/``exists``/``delete``/``list``), so callers stay unchanged.

Keys are validated to stay inside their bucket: ``..`` segments and absolute
paths are rejected (защита от обхода каталога / path-traversal).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = ["ObjectRef", "ObjectStore"]

# Reserved key for the per-bucket JSON manifest (реестр объектов бакета, §5.5).
MANIFEST_KEY = "manifest.json"


@dataclass(frozen=True)
class ObjectRef:
    """Immutable pointer to a stored blob (§5.5): ссылка на объект хранилища."""

    bucket: str
    key: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_bucket(bucket: str) -> None:
    """Reject bucket names that are empty or contain path separators (§5.5)."""
    if not bucket or "/" in bucket or "\\" in bucket or bucket in {".", ".."}:
        raise ValueError(f"invalid bucket: {bucket!r}")


def _validate_key(key: str) -> str:
    """Reject unsafe keys (§5.5 path-safety): ``..`` segments or absolute paths.

    Returns the POSIX-normalized key (backslashes folded to ``/``) on success;
    raises :class:`ValueError` otherwise (path-traversal / абсолютный путь).
    """
    if not key:
        raise ValueError("empty key")
    normalized = key.replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError(f"absolute key not allowed: {key!r}")
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise ValueError(f"path traversal not allowed: {key!r}")
    return normalized


class ObjectStore:
    """Filesystem-backed S3-like object store (§5.5, embedded profile).

    Each bucket is a subdirectory of *root_dir*; each object a file whose
    relative path is its key. Content-addressed writes derive the key from the
    SHA-256 of the payload, so identical content is stored once (dedup).
    """

    def __init__(self, root_dir: str | os.PathLike[str]) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, bucket: str, key: str) -> tuple[str, Path]:
        """Validate *bucket*/*key* and return (safe_key, absolute filesystem path)."""
        _validate_bucket(bucket)
        safe_key = _validate_key(key)
        return safe_key, self.root / bucket / safe_key

    def put(self, bucket: str, key: str, data: bytes) -> ObjectRef:
        """Store *data* under ``bucket/key`` and return its :class:`ObjectRef`."""
        safe_key, path = self._resolve(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ObjectRef(
            bucket=bucket,
            key=safe_key,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def get(self, bucket: str, key: str) -> bytes:
        """Read the blob at ``bucket/key``; raise :class:`KeyError` if absent."""
        _, path = self._resolve(bucket, key)
        if not path.is_file():
            raise KeyError(f"{bucket}/{key}")
        return path.read_bytes()

    def exists(self, bucket: str, key: str) -> bool:
        """Return whether an object exists at ``bucket/key``."""
        _, path = self._resolve(bucket, key)
        return path.is_file()

    def delete(self, bucket: str, key: str) -> bool:
        """Delete ``bucket/key``; return True if removed, False if it was absent."""
        _, path = self._resolve(bucket, key)
        if path.is_file():
            path.unlink()
            return True
        return False

    def list(self, bucket: str, prefix: str = "") -> list[str]:
        """List object keys in *bucket* filtered by *prefix* (sorted, POSIX keys)."""
        _validate_bucket(bucket)
        base = self.root / bucket
        if not base.is_dir():
            return []
        keys: list[str] = []
        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(base).as_posix()
                if rel.startswith(prefix):
                    keys.append(rel)
        return sorted(keys)

    def put_content(self, bucket: str, data: bytes) -> str:
        """Content-addressed write (§5.5): key = SHA-256 hex; identical bytes dedup.

        The key is the hex SHA-256 digest of *data*, so re-putting identical
        content resolves to the same path and stores a single blob.
        """
        key = hashlib.sha256(data).hexdigest()
        self.put(bucket, key, data)
        return key

    def write_manifest(self, bucket: str, entries: dict[str, Any]) -> ObjectRef:
        """Write a JSON manifest of *entries* under ``manifest.json`` (§5.5)."""
        payload = json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        return self.put(bucket, MANIFEST_KEY, payload)

    def read_manifest(self, bucket: str) -> dict[str, Any]:
        """Read back the JSON manifest written by :meth:`write_manifest` (§5.5)."""
        raw = self.get(bucket, MANIFEST_KEY)
        return json.loads(raw.decode("utf-8"))
