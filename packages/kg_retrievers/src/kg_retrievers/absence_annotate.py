"""§25.13 — annotate detected gaps with an absence verdict.

Gap-detection (§15/§25) hands downstream a flat list of suspected пробелы
(gaps), each a bare ``(material, property)`` cell. §25.13 asks a sharper
question of every one of them: *is this actually absent, or did the extractor
merely miss it — or is the cell in fact already covered?* This module answers by
running the fused §25.11 classifier (:func:`kg_retrievers.absence_signals.
classify_cell`) over each gap and attaching its verdict:

- ``present`` / ``covered`` — the cell turns out to hold an active observation,
  so the gap is *downgraded* (снят): it was never a real absence;
- ``retracted`` — the cell's only observation was soft-withdrawn (§25.12): its
  own class, neither coverage nor a scoreable gap;
- ``possible_miss`` — mentioned-but-unmeasured, or an empty cell we strongly
  expected to be covered: probably a пропуск извлечения (extraction miss);
- ``genuine_gap`` — an empty, unmentioned cell we did not expect covered: a
  настоящий пробел (real absence);
- ``abstain`` — too uncertain to call.

:func:`annotate_gaps` yields one frozen :class:`AnnotatedGap` per input gap
(verdict, ``p_truly_absent`` carried through from the classifier, and a short
RU/EN note). :func:`filter_genuine` then keeps only the *actionable* verdicts —
``genuine_gap`` and ``possible_miss`` — dropping the downgraded / retracted ones.

Read-only. This module never writes to the graph; the verdict vocabulary and all
probability math are reused verbatim from :mod:`kg_retrievers.absence_signals`.
The Kuzu note holds transitively: the classifier reads the ``retracted``
tombstone (a JSON ``props`` catch-all, not a queryable column) through
:meth:`~kg_retrievers.graph_store.KuzuGraphStore.get_node`, never a RETURN
column, and this module adds no queries of its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from kg_common import get_logger, make_id
from kg_retrievers.absence_signals import (
    ABSTAIN,
    COVERED,
    DEFAULT_RECALL_PRIOR,
    GENUINE_GAP,
    POSSIBLE_MISS,
    PRESENT,
    RETRACTED,
    classify_cell,
)
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("absence_annotate")

# Verdicts worth acting on: a real absence or a likely extraction miss. The
# downgraded (present/covered), retracted and abstain verdicts are *not* kept.
GENUINE_VERDICTS = frozenset({GENUINE_GAP, POSSIBLE_MISS})

# One short RU/EN note per verdict (§25.13). Never empty — the note explains, in
# plain terms, why the gap was kept, downgraded, or set aside.
_NOTES: dict[str, str] = {
    PRESENT: "Есть наблюдение со значением — пробел снят. / Valued observation, downgraded.",
    COVERED: "Есть наблюдение без значения — пробел снят. / Valueless observation, downgraded.",
    RETRACTED: "Наблюдение отозвано (§25.12) — не покрытие. / Only observation retracted.",
    POSSIBLE_MISS: "Вероятный пропуск извлечения. / Likely extraction miss; re-check.",
    GENUINE_GAP: "Настоящий пробел — данных нет. / Genuine gap; no data found.",
    ABSTAIN: "Недостаточно данных для вердикта. / Too uncertain to decide.",
}


@dataclass(frozen=True)
class AnnotatedGap:
    """A suspected gap tagged with its §25.13 absence verdict.

    ``verdict`` is one of the §25.11 vocabulary (``present`` / ``covered`` /
    ``retracted`` / ``possible_miss`` / ``genuine_gap`` / ``abstain``);
    ``p_truly_absent`` is the classifier's posterior P(truly absent) carried
    through unchanged (in ``[0, 1]``; ``0.0`` for decided/covered cells);
    ``note`` is a non-empty RU/EN gloss of the verdict.
    """

    gap_id: str
    material_id: str
    property_id: str
    verdict: str
    p_truly_absent: float
    note: str

    @property
    def is_genuine(self) -> bool:
        """True when the verdict is actionable (genuine_gap / possible_miss)."""
        return self.verdict in GENUINE_VERDICTS

    def as_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "material_id": self.material_id,
            "property_id": self.property_id,
            "verdict": self.verdict,
            "p_truly_absent": self.p_truly_absent,
            "note": self.note,
        }


def _read(gap: Any, key: str) -> Any:
    """Read ``key`` from a gap given as a mapping or an attribute-bearing object."""
    if isinstance(gap, Mapping):
        return gap.get(key)
    return getattr(gap, key, None)


def _note_for(verdict: str) -> str:
    """Non-empty RU/EN note for a verdict (falls back to the abstain gloss)."""
    return _NOTES.get(verdict, _NOTES[ABSTAIN])


def annotate_gaps(
    store: KuzuGraphStore,
    gaps: Iterable[Any],
    *,
    recall_prior: float = DEFAULT_RECALL_PRIOR,
    value_gate: bool = False,
) -> list[AnnotatedGap]:
    """Annotate each gap with a §25.13 absence verdict via :func:`classify_cell`.

    Each item in ``gaps`` supplies ``material_id``, ``property_id`` and (optional)
    ``gap_id`` — as mapping keys or object attributes; a missing ``gap_id`` is
    derived deterministically from the cell. ``property_id`` may be a ``Property``
    node id or a bare property name (whatever :func:`classify_cell` accepts).
    ``recall_prior`` is forwarded to the classifier and governs how empty,
    unmentioned cells split between ``genuine_gap`` and ``possible_miss``.
    ``value_gate`` (opt-in, default off — §33/N2) is forwarded too: with it on, a
    mentioned cell whose prose only *names* the property (states no value) is
    downgraded ``possible_miss`` → ``genuine_gap``. The classifier's
    ``p_truly_absent`` is carried through unchanged. Read-only.
    """
    out: list[AnnotatedGap] = []
    for gap in gaps:
        material_id = _read(gap, "material_id")
        property_id = _read(gap, "property_id")
        gap_id = _read(gap, "gap_id") or make_id("Gap", f"{material_id}:{property_id}")
        sig = classify_cell(
            store, material_id, property_id, recall_prior=recall_prior, value_gate=value_gate
        )
        out.append(
            AnnotatedGap(
                gap_id=gap_id,
                material_id=material_id,
                property_id=property_id,
                verdict=sig.verdict,
                p_truly_absent=sig.p_truly_absent,
                note=_note_for(sig.verdict),
            )
        )
    _log.info("annotate_gaps.done", gaps=len(out), recall_prior=recall_prior, value_gate=value_gate)
    return out


def filter_genuine(annotated: Iterable[AnnotatedGap]) -> list[AnnotatedGap]:
    """Keep only actionable gaps — ``genuine_gap`` and ``possible_miss`` (§25.13).

    Downgraded (``present`` / ``covered``), ``retracted`` and ``abstain`` gaps
    are dropped: they are not real, scoreable absences.
    """
    return [a for a in annotated if a.verdict in GENUINE_VERDICTS]
