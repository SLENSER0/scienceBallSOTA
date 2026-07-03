"""Extractor run metadata (§6.14 — a stamped record of one extraction run).

Каждый прогон экстрактора (*extractor run*) описывается неизменяемой записью
:class:`RunMetadata`: кто извлекал (``extractor`` / ``extractor_version``), какой
моделью (``model``) и с какими параметрами (``params``), когда (``started_at``), при
какой версии схемы (``schema_version``) и с каким объёмом результата
(``n_docs`` / ``n_entities`` / ``n_measurements``).

Эта запись — источник провенанса (*provenance source*): её
:meth:`RunMetadata.to_provenance` отдаёт ровно те три поля, которыми штампуется каждый
фактический узел графа (§3.7) — ``extractor_run_id`` / ``schema_version`` /
``created_at`` (см. :data:`kg_schema.provenance.REQUIRED_PROVENANCE`).

``run_id`` детерминирован (*deterministic*): :func:`make_run_metadata` выводит его из
хеша ``(extractor, started_at)``, поэтому один и тот же прогон всегда получает один и
тот же идентификатор — воспроизводимо для тестов и идемпотентного upsert (§8.9).

Kuzu note: кастомные свойства узла (``extractor``, ``params`` …) НЕ являются
запрашиваемыми колонками — их читают через ``get_node()``; в ``RETURN`` идут только
базовые колонки. Поэтому запись сериализуется плоским ``as_dict()`` без вложенности,
пригодной для property-map узла ``:ExtractorRun`` (§8.2).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Schema version in force when a run is stamped, if the caller does not pin one
# (§3.15 / §23.4). Matches kg_schema.__version__ / the LinkML ontology version.
DEFAULT_SCHEMA_VERSION = "0.1.0"

# Length of the hex digest kept for a deterministic run_id (§6.14).
_RUN_ID_HEX_LEN = 16

# The three provenance keys stamped on every factual node (§3.7). Kept in the same
# order as kg_schema.provenance.REQUIRED_PROVENANCE — the test guards against drift.
PROVENANCE_KEYS: tuple[str, str, str] = ("extractor_run_id", "schema_version", "created_at")


@dataclass(frozen=True)
class RunMetadata:
    """Immutable metadata for one extractor run (§6.14).

    Attributes
    ----------
    run_id:
        Stable identifier for the run — deterministic from ``(extractor,
        started_at)`` when built via :func:`make_run_metadata`. Becomes
        ``extractor_run_id`` on every node the run emits (§3.7 / §8.2).
    extractor:
        Extractor name (e.g. ``"llm"`` / ``"rule"`` / ``"regex-units"``).
    extractor_version:
        Version string of the extractor code that produced the run.
    model:
        Underlying model id, if any (``None`` for pure rule extractors).
    params:
        Free-form extractor parameters (temperature, prompt id, thresholds, …).
    started_at:
        ISO-8601 start timestamp; also the ``created_at`` stamped on nodes.
    schema_version:
        Ontology/schema version in force at extraction time (§3.15 / §23.4).
    n_docs / n_entities / n_measurements:
        Result-volume counters for the run.
    """

    run_id: str
    extractor: str
    extractor_version: str = "0.0.0"
    model: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    schema_version: str = DEFAULT_SCHEMA_VERSION
    n_docs: int = 0
    n_entities: int = 0
    n_measurements: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a flat, JSON-friendly dict (§6.14).

        ``params`` is copied so callers cannot mutate the frozen record through
        the returned mapping. Round-trips via ``RunMetadata(**md.as_dict())``.
        """
        return {
            "run_id": self.run_id,
            "extractor": self.extractor,
            "extractor_version": self.extractor_version,
            "model": self.model,
            "params": dict(self.params),
            "started_at": self.started_at,
            "schema_version": self.schema_version,
            "n_docs": self.n_docs,
            "n_entities": self.n_entities,
            "n_measurements": self.n_measurements,
        }

    def to_provenance(self) -> dict[str, str]:
        """Return the provenance subset stamped on each factual node (§3.7).

        Maps ``run_id → extractor_run_id`` and ``started_at → created_at``; the
        result carries exactly :data:`PROVENANCE_KEYS`, ready to splat onto a
        node dict before upsert (``{**node, **md.to_provenance()}``).
        """
        return {
            "extractor_run_id": self.run_id,
            "schema_version": self.schema_version,
            "created_at": self.started_at,
        }


def _utc_now_iso() -> str:
    """Current UTC instant as an ISO-8601 string (§6.14)."""
    return datetime.now(UTC).isoformat()


def _deterministic_run_id(extractor: str, started_at: str) -> str:
    """Derive a stable ``run_id`` from ``(extractor, started_at)`` (§6.14).

    Same inputs → same id (SHA-256 over ``"{extractor}|{started_at}"``), so a run
    is reproducibly identifiable across processes and re-ingests (§8.9).
    """
    payload = f"{extractor}|{started_at}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:_RUN_ID_HEX_LEN]
    return f"run:{digest}"


def make_run_metadata(extractor: str, **kw: Any) -> RunMetadata:
    """Build a :class:`RunMetadata` with a deterministic ``run_id`` (§6.14).

    ``started_at`` defaults to the current UTC instant when not supplied; the
    ``run_id`` is then derived deterministically from ``(extractor, started_at)``
    unless the caller pins one explicitly. Any remaining keyword is forwarded to
    :class:`RunMetadata` (``extractor_version``, ``model``, ``params``,
    ``schema_version``, ``n_docs`` / ``n_entities`` / ``n_measurements``).
    """
    started_at = kw.pop("started_at", None) or _utc_now_iso()
    run_id = kw.pop("run_id", None) or _deterministic_run_id(extractor, started_at)
    return RunMetadata(run_id=run_id, extractor=extractor, started_at=started_at, **kw)


__all__ = [
    "DEFAULT_SCHEMA_VERSION",
    "PROVENANCE_KEYS",
    "RunMetadata",
    "make_run_metadata",
]
