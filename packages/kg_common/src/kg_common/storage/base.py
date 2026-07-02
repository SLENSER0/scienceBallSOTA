"""MetaStore protocol + DTOs (§25.4).

The MetaStore persists *coverage telemetry* (which extractor looked for which
entity type over which chunk, and how many it found) and *extractor recall
priors*, so the absence-confidence layer (§25.11, :mod:`kg_retrievers.
confidence_of_absence`) can tell a true knowledge gap from mere non-extraction.

Two interchangeable backends implement this protocol over identical SQL
(SQLite for the embedded profile, PostgreSQL for the server profile); see
:class:`kg_common.storage.sql.SqlMetaStore`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CoverageEvent:
    """One (extractor × target_type) attempt over one chunk (§25.5)."""

    doc_id: str
    chunk_id: str
    extractor: str
    target_type: str
    attempted: bool = True
    found_count: int = 0
    run_id: str = "unspecified"


@dataclass(frozen=True)
class CoverageStats:
    target_type: str
    n_chunks: int
    n_attempts: int
    n_found: int
    n_docs: int

    @property
    def hit_rate(self) -> float:
        """Fraction of attempts that found ≥1 entity of the target type."""
        return self.n_found / self.n_attempts if self.n_attempts else 0.0


@dataclass(frozen=True)
class RecallPrior:
    extractor: str
    target_type: str
    recall: float
    sample_size: int = 0


@runtime_checkable
class MetaStore(Protocol):
    """Backend-agnostic metadata store (§25.4)."""

    def migrate(self) -> None:
        """Idempotently create/upgrade tables (rollback-safe)."""
        ...

    def log_coverage(self, event: CoverageEvent) -> None:
        """Upsert one coverage event; re-logging the same key must not duplicate."""
        ...

    def coverage_stats(
        self, *, target_type: str | None = None, doc_id: str | None = None
    ) -> list[CoverageStats]:
        """Aggregate coverage per target_type (optionally filtered)."""
        ...

    def save_recall_prior(self, prior: RecallPrior) -> None:
        """Upsert a recall prior for (extractor, target_type)."""
        ...

    def get_recall_priors(
        self, *, extractor: str | None = None, target_type: str | None = None
    ) -> list[RecallPrior]:
        ...
