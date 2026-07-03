"""Recall-by-modality report from recall priors / telemetry (§25.9).

Given the per-cell recall priors derived from coverage telemetry (§25.10,
:mod:`kg_retrievers.recall_priors`), this module rolls them up into a compact
*recall report* for the gap dashboard: the average recall **per modality**
(способ извлечения — prose / table_row / catalog_row) and **per extractor**,
the weakest cells (the (modality, extractor) pairs most likely to under-extract),
and the share of priors that are *calibrated* from real telemetry versus a
*heuristic* neutral default (эвристика).

Input is a list of plain prior dicts, each carrying:

- ``target_type`` — the extraction modality (prose / table_row / catalog_row);
- ``extractor``   — the extractor label that produced the prior;
- ``recall``      — the (smoothed) recall estimate, normally in ``[0, 1]``;
- ``calibrated``  — ``True`` when backed by telemetry, ``False`` when heuristic.

Pure Python and read-only: it reads no store and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

# Known extraction modalities (способы извлечения) the report rolls priors up by (§25.9).
MODALITIES: tuple[str, ...] = ("prose", "table_row", "catalog_row")

# Default number of weakest cells (самые слабые ячейки) to flag in a report.
DEFAULT_WEAKEST_N: int = 3


@dataclass(frozen=True)
class RecallCell:
    """One recall prior projected onto a (modality, extractor) cell (§25.9)."""

    modality: str
    extractor: str
    recall: float
    calibrated: bool

    def as_dict(self) -> dict:
        return {
            "modality": self.modality,
            "extractor": self.extractor,
            "recall": self.recall,
            "calibrated": self.calibrated,
        }


@dataclass(frozen=True)
class RecallReport:
    """Recall roll-up per modality / extractor with weakest cells + calibrated share (§25.9)."""

    by_modality: dict[str, float]
    by_extractor: dict[str, float]
    weakest: tuple[RecallCell, ...]
    calibrated_share: float

    def as_dict(self) -> dict:
        return {
            "by_modality": dict(self.by_modality),
            "by_extractor": dict(self.by_extractor),
            "weakest": [cell.as_dict() for cell in self.weakest],
            "calibrated_share": self.calibrated_share,
        }


def _mean(values: list[float]) -> float:
    """Arithmetic mean; an empty group averages to ``0.0`` (no evidence)."""
    return sum(values) / len(values) if values else 0.0


def _group_mean(cells: list[RecallCell], key: str) -> dict[str, float]:
    """Mean recall per distinct ``key`` value, key-sorted for deterministic output."""
    groups: dict[str, list[float]] = {}
    for cell in cells:
        groups.setdefault(getattr(cell, key), []).append(cell.recall)
    return {name: _mean(vals) for name, vals in sorted(groups.items())}


def build_recall_report(priors: list[dict], *, weakest_n: int = DEFAULT_WEAKEST_N) -> RecallReport:
    """Summarize recall ``priors`` per modality / extractor for the gap dashboard (§25.9).

    Each prior dict contributes one :class:`RecallCell`. The report exposes mean
    recall ``by_modality`` and ``by_extractor``, the ``weakest_n`` cells sorted by
    ascending recall (ties broken by modality then extractor), and the
    ``calibrated_share`` — the fraction of priors flagged ``calibrated``. An empty
    input yields empty maps, no weakest cells and a ``0.0`` share.
    """
    cells = [
        RecallCell(
            modality=str(prior["target_type"]),
            extractor=str(prior["extractor"]),
            recall=float(prior["recall"]),
            calibrated=bool(prior["calibrated"]),
        )
        for prior in priors
    ]
    ranked = sorted(cells, key=lambda cell: (cell.recall, cell.modality, cell.extractor))
    n_calibrated = sum(1 for cell in cells if cell.calibrated)
    return RecallReport(
        by_modality=_group_mean(cells, "modality"),
        by_extractor=_group_mean(cells, "extractor"),
        weakest=tuple(ranked[: max(0, weakest_n)]),
        calibrated_share=(n_calibrated / len(cells) if cells else 0.0),
    )
