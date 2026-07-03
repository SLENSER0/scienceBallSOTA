"""Absence value-of-information ranking (§25.11).

RU: Ранжирование ячеек отсутствия по ожидаемому снижению неопределённости.
EN: Rank absence cells by expected uncertainty reduction (value of information).

Each empty coverage cell carries ``p_extractor_missed`` — the probability that the
observed absence is an extraction *miss* rather than a real absence. A cell is
maximally *ambiguous* when this probability is near ``0.5``: we learn the most by
resolving it. We quantify that ambiguity with the binary (Shannon) entropy

    H(p) = -p*log2(p) - (1-p)*log2(1-p)

so ``voi = H(p_extractor_missed)`` peaks at ``1.0`` for ``p = 0.5`` and falls to
``0.0`` for the certain ends ``p = 0`` / ``p = 1``. Curators resolving the highest-VoI
cells first strip out the most uncertainty per unit of effort.

This is distinct from ``expected_missed_facts.py`` (which ranks the *yield* backlog
by ``1 - confidence_of_absence``) and from ``reextraction_batch_planner.py`` (which
groups cells by document): here we rank by *ambiguity*, not by expected yield or
locality.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2

SCHEMA_VERSION = "0.1.0"


def _binary_entropy(p: float) -> float:
    """Binary Shannon entropy ``H(p)`` in bits (§25.11).

    RU: бинарная энтропия; H(0)=H(1)=0.0. EN: binary entropy; H(0)=H(1)=0.0.
    """
    p = float(p)
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * log2(p) - (1.0 - p) * log2(1.0 - p)


@dataclass(frozen=True, slots=True)
class VoICell:
    """One absence cell scored by value of information (§25.11).

    RU: ячейка отсутствия с оценкой VoI. EN: an absence cell with a VoI score.
    """

    material_id: str
    property_name: str
    p_missed: float
    voi: float

    def as_dict(self) -> dict[str, object]:
        """RU: сериализация в словарь. EN: serialise to a plain dict."""
        return {
            "material_id": self.material_id,
            "property_name": self.property_name,
            "p_missed": self.p_missed,
            "voi": self.voi,
        }


@dataclass(frozen=True, slots=True)
class VoIReport:
    """Ranked value-of-information report over absence cells (§25.11).

    RU: ранжированный отчёт VoI по ячейкам отсутствия. EN: ranked VoI report.
    """

    cells: tuple[VoICell, ...]
    total_voi: float
    top: tuple[VoICell, ...]

    def as_dict(self) -> dict[str, object]:
        """RU: сериализация в словарь. EN: serialise to a plain dict."""
        return {
            "schema_version": SCHEMA_VERSION,
            "cells": [cell.as_dict() for cell in self.cells],
            "total_voi": self.total_voi,
            "top": [cell.as_dict() for cell in self.top],
        }


def rank_value_of_information(
    cells: list[dict],
    *,
    top_n: int = 10,
    p_key: str = "p_extractor_missed",
) -> VoIReport:
    """Rank absence cells by binary-entropy value of information (§25.11).

    RU: ранжирует ячейки по убыванию VoI (энтропии), затем по (material, property).
    EN: ranks cells by descending VoI (entropy), then by (material, property).

    Cells lacking ``p_key`` get ``voi = 0.0``. Sorted by ``voi`` descending, then by
    ``(material_id, property_name)`` ascending. ``top`` is the first ``top_n`` cells.
    """
    scored: list[VoICell] = []
    for cell in cells:
        material_id = str(cell.get("material_id", ""))
        property_name = str(cell.get("property_name", ""))
        raw = cell.get(p_key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            p_missed = 0.0
            voi = 0.0
        else:
            p_missed = float(raw)
            voi = _binary_entropy(p_missed)
        scored.append(
            VoICell(
                material_id=material_id,
                property_name=property_name,
                p_missed=p_missed,
                voi=voi,
            )
        )

    scored.sort(key=lambda c: (-c.voi, c.material_id, c.property_name))
    total_voi = sum(cell.voi for cell in scored)
    top = tuple(scored[:top_n])
    return VoIReport(cells=tuple(scored), total_voi=total_voi, top=top)
