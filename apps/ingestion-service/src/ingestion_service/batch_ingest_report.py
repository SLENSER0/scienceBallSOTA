"""Aggregated batch/seed ingestion report (§5.10 / §5.12).

A §5.10 batch (or seed) ingestion runs many documents through the pipeline and yields one
result per document. This module folds those per-document results into a single summary the
operator can read at a glance: how many were attempted, how many finished, how many failed,
how many were duplicates, a per-status tally, and the concrete failure details. It is a pure,
side-effect-free aggregator — distinct from a dedup report (which groups by content hash);
here we group by outcome status. The §5.12 aggregated report proper is still unbuilt, so this
is the minimal building block for it.

Сводный отчёт по пакетной/начальной загрузке (§5.10 / §5.12): сворачивает результаты по
каждому документу в одну сводку — сколько всего, готово, с ошибкой, дубликатов, разбивку по
статусам и детали ошибок. Чистая функция без побочных эффектов; в отличие от dedup-отчёта
(группировка по хешу) здесь группировка по статусу.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BatchIngestReport:
    """Immutable summary of one §5.10 batch ingestion run.

    ``total`` is the number of per-document results folded in. ``done`` / ``failed`` count the
    results whose ``status`` is ``'done'`` / ``'failed'``. ``duplicates`` counts results flagged
    as a duplicate. ``by_status`` tallies every status string seen (its values sum to ``total``).
    ``failures`` carries one ``{'doc_id', 'error'}`` entry per failed result.

    Неизменяемая сводка одного прогона пакетной загрузки: всего/готово/ошибок/дубликатов,
    разбивка по статусам (сумма значений равна total) и детали ошибок.
    """

    total: int
    done: int
    failed: int
    duplicates: int
    by_status: dict[str, int]
    failures: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-safe dict (``failures`` becomes a list)."""
        return {
            "total": self.total,
            "done": self.done,
            "failed": self.failed,
            "duplicates": self.duplicates,
            "by_status": dict(self.by_status),
            "failures": [dict(entry) for entry in self.failures],
        }


def build_batch_report(results: list[dict[str, Any]]) -> BatchIngestReport:
    """Fold per-document ingestion ``results`` into one :class:`BatchIngestReport` (§5.10).

    Each result is a dict with keys ``doc_id`` / ``status`` / ``duplicate`` / ``error``. Rules:

    * ``total`` == ``len(results)``.
    * ``done`` counts results with ``status == 'done'``; ``failed`` counts ``status == 'failed'``.
    * ``duplicates`` counts results whose ``duplicate`` value is truthy.
    * ``by_status`` tallies every status seen; its values always sum to ``total``.
    * every failed result contributes a ``{'doc_id', 'error'}`` entry to ``failures``.

    An empty input yields all-zero counts, ``by_status == {}`` and ``failures == ()``.

    Сворачивает результаты по документам в один отчёт: суммы, разбивка по статусам и ошибки.
    """
    done = 0
    failed = 0
    duplicates = 0
    by_status: dict[str, int] = {}
    failures: list[dict[str, Any]] = []

    for result in results:
        status = result.get("status")
        status_key = status if isinstance(status, str) else str(status)
        by_status[status_key] = by_status.get(status_key, 0) + 1

        if status == "done":
            done += 1
        elif status == "failed":
            failed += 1
            failures.append({"doc_id": result.get("doc_id"), "error": result.get("error")})

        if result.get("duplicate"):
            duplicates += 1

    return BatchIngestReport(
        total=len(results),
        done=done,
        failed=failed,
        duplicates=duplicates,
        by_status=by_status,
        failures=tuple(failures),
    )
