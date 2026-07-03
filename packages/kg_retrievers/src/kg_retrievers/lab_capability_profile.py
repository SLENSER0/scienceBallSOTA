"""Per-lab capability profile builder (§24.12).

Assembles the lab "capability profile" enumerated in §24.12 — *equipment*,
*processes*, *materials*, *confirmed experiments* and an *activity score* — from
a raw records mapping. No such profile assembler exists today; the retrievers
surface only individual lab fields, never the consolidated §24.12 view with a
deduplicated capability inventory and an experiment-derived activity score.

Собирает профиль возможностей лаборатории из §24.12 (оборудование, процессы,
материалы, подтверждённые эксперименты, показатель активности) из сырого
отображения records, дедуплицируя перечни и выводя показатель активности из
числа подтверждённых и неподтверждённых экспериментов.

Activity score = ``n_confirmed_experiments + 0.5 * n_unconfirmed_experiments``.

Pure, read-only data logic — no store access.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Record keys whose values become deduplicated, sorted tuple fields.
_TUPLE_FIELDS: tuple[str, ...] = ("equipment", "processes", "materials")


def _dedupe_sorted(values: Iterable[object]) -> tuple[str, ...]:
    """Return string values with duplicates dropped, sorted ascending."""
    return tuple(sorted({str(value) for value in values}))


@dataclass(frozen=True)
class LabCapabilityProfile:
    """Consolidated §24.12 capability profile for a single lab.

    - ``lab_id`` — identifier of the profiled lab;
    - ``equipment`` — equipment inventory, deduped and sorted;
    - ``processes`` — process inventory, deduped and sorted;
    - ``materials`` — material inventory, deduped and sorted;
    - ``n_confirmed_experiments`` — count of experiments flagged confirmed;
    - ``activity_score`` — ``n_confirmed + 0.5 * n_unconfirmed``.
    """

    lab_id: str
    equipment: tuple[str, ...]
    processes: tuple[str, ...]
    materials: tuple[str, ...]
    n_confirmed_experiments: int
    activity_score: float

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly mapping; tuple fields become lists."""
        return {
            "lab_id": self.lab_id,
            "equipment": list(self.equipment),
            "processes": list(self.processes),
            "materials": list(self.materials),
            "n_confirmed_experiments": self.n_confirmed_experiments,
            "activity_score": self.activity_score,
        }


def build_lab_capability_profile(lab_id: str, records: dict) -> LabCapabilityProfile:
    """Build a §24.12 :class:`LabCapabilityProfile` from ``lab_id`` and ``records``.

    ``records`` is a mapping of the form::

        {
            'equipment': [...],
            'processes': [...],
            'materials': [...],
            'experiments': [{'confirmed': bool, 'year': int}, ...],
        }

    The three inventory fields are deduplicated and sorted; absent keys yield an
    empty tuple. Experiments are split by their ``confirmed`` flag: the confirmed
    count is reported directly, and the activity score adds half a point per
    unconfirmed experiment.
    """
    inventories: dict[str, tuple[str, ...]] = {}
    for key in _TUPLE_FIELDS:
        inventories[key] = _dedupe_sorted(records.get(key) or ())

    experiments = records.get("experiments") or ()
    n_confirmed = sum(1 for exp in experiments if exp.get("confirmed"))
    n_unconfirmed = len(experiments) - n_confirmed
    activity_score = float(n_confirmed) + 0.5 * float(n_unconfirmed)

    return LabCapabilityProfile(
        lab_id=str(lab_id),
        equipment=inventories["equipment"],
        processes=inventories["processes"],
        materials=inventories["materials"],
        n_confirmed_experiments=n_confirmed,
        activity_score=activity_score,
    )
