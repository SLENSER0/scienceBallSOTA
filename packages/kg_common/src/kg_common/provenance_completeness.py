"""Evidence-pack provenance completeness — полнота происхождения пакета (§23.29).

A *reproducible evidence pack* is only reproducible if it carries **every**
provenance slot needed to re-run and re-verify the work behind it. The manifest
module (:mod:`kg_common.evidence_pack_manifest`) hashes the pack's *file bytes*
but does **not** check that the accompanying provenance metadata is complete —
it never inspects fields like ``model_version`` or ``retrieval_scores``.

This module fills that gap. Given a provenance mapping, it reports which of the
required slots are present, which are missing, and an overall completeness ratio
(«отчёт о полноте метаданных происхождения»).

Required slots (per §23.29/§23.12/§23.14):

* ``model_version``          — LLM/model version — версия модели.
* ``prompt_version``         — prompt template version — версия промпта.
* ``extractor_run_id``       — extractor run identifier — идентификатор прогона.
* ``graph_schema_version``   — KG schema version — версия схемы графа.
* ``data_snapshot_version``  — data snapshot version — версия снимка данных.
* ``retrieval_scores``       — retrieval scores — оценки извлечения.

A slot counts as *present* iff its key exists **and** its value is not ``None``,
not an empty string, and not an empty collection. Notably, a falsy-but-real
value such as the integer ``0`` counts as present — «ноль это тоже значение».

Everything here is pure standard library, deterministic and side-effect free.

Public API:

* :data:`REQUIRED_SLOTS`  — canonical tuple of required provenance slots.
* :class:`ProvenanceReport` — frozen report with :meth:`as_dict`.
* :func:`check`           — build a :class:`ProvenanceReport` from a mapping.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Sized
from dataclasses import dataclass
from typing import Any

__all__ = [
    "REQUIRED_SLOTS",
    "ProvenanceReport",
    "check",
]

#: Canonical required provenance slots — обязательные слоты происхождения (§23.29).
REQUIRED_SLOTS: tuple[str, ...] = (
    "model_version",
    "prompt_version",
    "extractor_run_id",
    "graph_schema_version",
    "data_snapshot_version",
    "retrieval_scores",
)


def _is_present(value: object) -> bool:
    """Return ``True`` iff ``value`` is a real, non-empty provenance value (§23.29).

    ``None``, the empty string, and empty collections count as *missing*. A
    falsy scalar such as ``0`` or ``False`` still counts as *present* — «ноль
    это значение, а не отсутствие».
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    # Empty sized collections (list/tuple/set/dict/...) count as missing.
    if isinstance(value, Sized) and not isinstance(value, (str, bytes)):
        return len(value) > 0
    return True


@dataclass(frozen=True)
class ProvenanceReport:
    """Provenance completeness report — отчёт о полноте происхождения (§23.29).

    Attributes:
        required: Slots that were required — требуемые слоты (in check order).
        present: Required slots present and non-empty — присутствующие слоты.
        missing: Required slots absent or empty — отсутствующие слоты (sorted by
            the ``required`` ordering).
        completeness: ``len(present) / len(required)`` in ``[0.0, 1.0]`` — доля.
        complete: ``True`` iff nothing is missing — полнота достигнута.
    """

    required: tuple[str, ...]
    present: tuple[str, ...]
    missing: tuple[str, ...]
    completeness: float
    complete: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` view — словарное представление (§23.29)."""
        return {
            "required": list(self.required),
            "present": list(self.present),
            "missing": list(self.missing),
            "completeness": self.completeness,
            "complete": self.complete,
        }


def check(
    provenance: Mapping[str, object],
    required: Sequence[str] | None = None,
) -> ProvenanceReport:
    """Check ``provenance`` against required slots — проверить полноту (§23.29).

    Args:
        provenance: Mapping of provenance slot -> value — метаданные происхождения.
        required: Slots to require; defaults to :data:`REQUIRED_SLOTS` — слоты.

    Returns:
        A :class:`ProvenanceReport`. ``completeness`` is ``0.0`` when ``required``
        is empty. ``present``/``missing`` preserve the ``required`` ordering.
    """
    req: tuple[str, ...] = tuple(REQUIRED_SLOTS if required is None else required)
    present = tuple(slot for slot in req if _is_present(provenance.get(slot)))
    missing = tuple(slot for slot in req if slot not in present)
    completeness = (len(present) / len(req)) if req else 0.0
    return ProvenanceReport(
        required=req,
        present=present,
        missing=missing,
        completeness=completeness,
        complete=missing == (),
    )
