"""Content-addressed artifact versioning — версионирование артефактов (§10.13).

Section 10.13 abstracts *where* raw and derived artifacts get versioned behind
an ``ARTIFACT_VERSIONING`` switch (``lakefs`` | ``dvc`` | ``none``). Only the
``none`` backend is embeddable — «встраиваемым является только none» — so the
edge deployment ships a self-contained, content-addressed versioner that keeps
history in memory instead of talking to a remote data-versioning service.

A commit is *content-addressed*: the ``version_id`` is a short (12-char) prefix
of the SHA-256 of the bytes, and ``content_hash`` is the full 64-char hex digest.
Committing identical bytes twice therefore yields the same hashes but two
distinct history entries («один и тот же контент — две записи истории»).

Public API:

* :class:`ArtifactVersion` — frozen record with :meth:`ArtifactVersion.as_dict`.
* :class:`Versioner`       — protocol/base with :meth:`Versioner.commit`.
* :class:`NoopVersioner`   — embeddable in-memory, content-addressed backend.
* :func:`make_versioner`   — factory over ``ARTIFACT_VERSIONING`` kinds.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "ArtifactVersion",
    "NoopVersioner",
    "Versioner",
    "make_versioner",
]

# Length of the short content-address prefix — длина короткого адреса (§10.13).
_SHORT_ID_LEN = 12

# Backends that are declared but not embeddable — не встраиваемые бэкенды (§10.13).
_UNAVAILABLE_KINDS: frozenset[str] = frozenset({"lakefs", "dvc"})


@dataclass(frozen=True)
class ArtifactVersion:
    """An immutable content-addressed version record — версия артефакта (§10.13).

    Bundles the artifact ``uri`` with its content hashes and a caller-supplied
    ``created_at`` timestamp. ``version_id`` is the short SHA-256 prefix used as a
    human-friendly handle; ``content_hash`` is the full 64-char hex digest.
    """

    uri: str
    version_id: str
    content_hash: str
    created_at: str

    def as_dict(self) -> dict[str, str]:
        """JSON-friendly view — ``{uri, version_id, content_hash, created_at}``.

        Serializes the record as a plain string mapping so it can be logged or
        embedded in an API payload without importing this module's dataclass.
        """
        return {
            "uri": self.uri,
            "version_id": self.version_id,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }


@runtime_checkable
class Versioner(Protocol):
    """Artifact-versioning contract — контракт версионирования (§10.13).

    A backend accepts the artifact ``uri``, its raw ``content`` bytes and a
    ``created_at`` timestamp, and returns the :class:`ArtifactVersion` it recorded.
    """

    def commit(self, uri: str, content: bytes, created_at: str) -> ArtifactVersion:
        """Record a new version of *uri* for the given *content* — фиксация."""
        ...


class NoopVersioner:
    """Embeddable in-memory content-addressed versioner — none-бэкенд (§10.13).

    The ``none`` backend needs no external service: it hashes the bytes to derive
    a deterministic ``version_id`` / ``content_hash`` and appends the resulting
    :class:`ArtifactVersion` to a per-URI in-memory history. Identical bytes hash
    identically yet still produce a fresh history entry on every commit.
    """

    def __init__(self) -> None:
        # Append-only history per artifact URI — история по URI (§10.13).
        self._history: dict[str, list[ArtifactVersion]] = {}

    def commit(self, uri: str, content: bytes, created_at: str) -> ArtifactVersion:
        """Hash *content* and append a version for *uri* — фиксация версии (§10.13).

        Computes the SHA-256 of *content*; ``version_id`` is its first
        ``12`` hex chars and ``content_hash`` the full digest. The record is
        appended to *uri*'s history and returned.
        """
        digest = hashlib.sha256(content).hexdigest()
        version = ArtifactVersion(
            uri=uri,
            version_id=digest[:_SHORT_ID_LEN],
            content_hash=digest,
            created_at=created_at,
        )
        self._history.setdefault(uri, []).append(version)
        return version

    def history(self, uri: str) -> tuple[ArtifactVersion, ...]:
        """All recorded versions of *uri*, oldest first — история (§10.13).

        Returns an empty tuple for a URI that was never committed
        («для неизвестного URI — пустая история»).
        """
        return tuple(self._history.get(uri, ()))

    def latest(self, uri: str) -> ArtifactVersion | None:
        """The most recent version of *uri*, or ``None`` — последняя версия (§10.13)."""
        versions = self._history.get(uri)
        return versions[-1] if versions else None


def make_versioner(kind: str = "none") -> Versioner:
    """Build a versioner for an ``ARTIFACT_VERSIONING`` kind — фабрика (§10.13).

    Only ``none`` is embeddable, so it returns a :class:`NoopVersioner`. The
    remote backends ``lakefs`` / ``dvc`` are declared but unavailable here and
    raise :class:`ValueError` («не встраиваемо»); any other value is rejected as
    an unknown kind.
    """
    if kind == "none":
        return NoopVersioner()
    if kind in _UNAVAILABLE_KINDS:
        raise ValueError(f"artifact versioning backend not embeddable: {kind!r}")
    raise ValueError(f"unknown artifact versioning backend: {kind!r}")
