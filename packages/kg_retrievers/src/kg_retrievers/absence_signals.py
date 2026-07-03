"""§25.11 — fuse three absence signals into a single cell verdict.

Три сигнала (three signals), one call. The absence layer already exposes each
signal in isolation; what §25.11 needs — and the individual modules miss — is a
verdict that *combines* them for a single (material, property) cell:

1. *existing observations* — an active ``Measurement`` / ``Claim`` about the cell
   (:func:`kg_retrievers.retractions.active_measurements`);
2. *retracted observations* — soft-withdrawn measurements
   (:func:`kg_retrievers.retractions.is_retracted`), which §25.12 says must be
   classified **separately** and never counted as coverage;
3. *MENTIONS-without-observation* — the material is упомянут in some document yet
   carries no measurement of the property
   (:func:`kg_retrievers.mentions_lineage.is_mentioned_without_observation`).

:func:`classify_cell` fuses them into one :class:`AbsenceSignal`:

- an active measurement -> ``present`` (a numeric value is present) / ``covered``
  (observed but valueless);
- a cell whose *only* measurements are retracted -> ``retracted`` (NOT covered,
  neither a genuine gap nor a miss — §25.12);
- mentioned-but-never-measured -> ``possible_miss`` (пропуск извлечения);
- otherwise a one-step Bayesian update turns ``recall_prior`` into P(truly
  absent) vs P(extractor missed), thresholded into ``possible_miss`` /
  ``genuine_gap`` / ``abstain``.

Read-only: this module reuses its siblings and never writes to the graph. The
Kuzu note applies throughout — the ``retracted`` tombstone lives in the JSON
``props`` catch-all, so retraction state is read back through
:meth:`~kg_retrievers.graph_store.KuzuGraphStore.get_node`, never via a column.

Bayesian note. Given *no* observed evidence, the datum is either a настоящий gap
(truly absent) or a miss (it exists but was not extracted). With prior
P(exists) = ``recall_prior`` (π) and a background extraction recall ``r =
EXTRACTOR_RECALL``::

    P(missed | no evidence)  = π(1 - r) / (π(1 - r) + (1 - π))
    P(absent | no evidence)  = 1 - P(missed | no evidence)

so a *high* ``recall_prior`` (we strongly expected this datum to be covered)
makes an empty cell look like a miss, while a *low* one makes an empty cell a
genuine gap. Thresholds are applied to P(missed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.confidence_of_absence import DEFAULT_RECALL
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.mentions_lineage import (
    is_mentioned_without_observation,
    mention_value_status,
)
from kg_retrievers.retractions import active_measurements, is_retracted

_log = get_logger("absence_signals")

# -- verdicts --------------------------------------------------------------
PRESENT = "present"  # active measurement with a numeric value
COVERED = "covered"  # active observation exists but carries no numeric value
RETRACTED = "retracted"  # only retracted measurements — classified apart (§25.12)
POSSIBLE_MISS = "possible_miss"  # extractor probably missed a datum (пропуск)
GENUINE_GAP = "genuine_gap"  # confident real absence (настоящий пробел)
ABSTAIN = "abstain"  # too uncertain to call either way

# -- thresholds on P(extractor missed | no evidence) -----------------------
POSSIBLE_MISS_AT = 0.60  # P(missed) >= this -> possible_miss
GENUINE_GAP_AT = 0.25  # P(missed) <= this -> genuine_gap (otherwise abstain)

# Default prior P(datum exists) — neutral, slightly above even odds.
DEFAULT_RECALL_PRIOR = 0.55
# Background extraction recall used in the Bayesian update (lock-step with the
# absence layer's ``DEFAULT_RECALL``, §25.10/§25.11).
EXTRACTOR_RECALL = DEFAULT_RECALL
# A MENTIONS link makes the datum's existence near-certain (§25.7): if the topic
# is упомянут yet unmeasured, an extraction miss is the likely explanation.
MENTION_EXISTS_PRIOR = 0.9
# §33/N2 value gate: when prose names the property but states NO measurable value,
# the mention is not evidence the datum exists, so the existence prior collapses to
# this floor — well below GENUINE_GAP_AT, so the cell reads as a genuine gap
# (property discussed, never measured) rather than an extractor miss.
VALUE_GATE_EXISTS_PRIOR = 0.1

_EPS = 1e-9


def _clamp_open(x: float) -> float:
    """Clamp ``x`` into the open interval ``(0, 1)`` so the posterior is defined."""
    return max(_EPS, min(float(x), 1.0 - _EPS))


def _verdict_from_p_missed(p_missed: float) -> str:
    """Threshold P(extractor missed) into a verdict (§25.11)."""
    if p_missed >= POSSIBLE_MISS_AT:
        return POSSIBLE_MISS
    if p_missed <= GENUINE_GAP_AT:
        return GENUINE_GAP
    return ABSTAIN


@dataclass(frozen=True)
class AbsenceSignal:
    """Fused §25.11 verdict for one (material, property) cell.

    ``verdict`` is one of ``present`` / ``covered`` / ``retracted`` /
    ``possible_miss`` / ``genuine_gap`` / ``abstain``. ``p_truly_absent`` and
    ``p_extractor_missed`` are the Bayesian posteriors on "no evidence" (both in
    ``[0, 1]``; ``0.0`` for decided cells). ``signals`` carries the raw три
    сигнала that drove the call.
    """

    verdict: str
    p_truly_absent: float
    p_extractor_missed: float
    signals: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "p_truly_absent": self.p_truly_absent,
            "p_extractor_missed": self.p_extractor_missed,
            "signals": dict(self.signals),
        }


def _resolve_property_name(store: KuzuGraphStore, property_id: str) -> str:
    """Resolve ``property_id`` to a Measurement ``property_name`` (§25.11).

    Accepts a ``Property`` node id (resolved via its ``property_name`` / ``name``
    field) or a bare property-name string (used as-is when no such node exists).
    Mirrors the resolution :func:`is_mentioned_without_observation` applies, so
    both signals agree on which property the cell is about.
    """
    nd = store.get_node(property_id)
    if nd:
        return nd.get("property_name") or nd.get("name") or property_id
    return property_id


def _has_value(measurement: dict[str, Any]) -> bool:
    """True when an observation carries a concrete normalized value."""
    return measurement.get("value_normalized") is not None


def _bayes_absence(exists_prior: float, recall: float) -> tuple[float, float]:
    """One-step Bayesian update on *no evidence* -> ``(p_truly_absent, p_missed)``.

    ``exists_prior`` is π = P(the datum exists); ``recall`` is the background
    extraction recall r. Returns both posteriors (they sum to 1), each rounded to
    four decimals and strictly inside ``[0, 1]`` (priors are clamped open first,
    so the denominator is always positive).
    """
    pi = _clamp_open(exists_prior)
    r = _clamp_open(recall)
    num_missed = pi * (1.0 - r)  # exists yet produced no evidence (a miss)
    num_absent = 1.0 - pi  # truly absent -> no evidence with certainty
    denom = num_missed + num_absent
    p_extractor_missed = round(num_missed / denom, 4)
    p_truly_absent = round(num_absent / denom, 4)
    return p_truly_absent, p_extractor_missed


def classify_cell(
    store: KuzuGraphStore,
    material_id: str,
    property_id: str,
    *,
    recall_prior: float = DEFAULT_RECALL_PRIOR,
    value_gate: bool = False,
) -> AbsenceSignal:
    """Fuse the three absence signals into one verdict for a cell (§25.11).

    ``property_id`` may be a ``Property`` node id or a bare property name.
    ``recall_prior`` is the prior P(the datum exists) used only when the cell is
    empty *and* unmentioned: a high value makes an empty cell read as a
    ``possible_miss``, a low value as a ``genuine_gap``. Never writes to the graph.

    ``value_gate`` (opt-in, default off — §33/N2) refines the mentioned-but-
    unmeasured case: when every prose mention names the property yet states **no**
    measurable value (:func:`~kg_retrievers.mentions_lineage.mention_value_status`
    returns ``False``), the cell is downgraded ``possible_miss`` → ``genuine_gap``
    (property discussed, never measured), instead of blaming the extractor. With
    the gate off, or on missing/positive value evidence, verdicts are unchanged.
    """
    prop_name = _resolve_property_name(store, property_id)
    # Both active and retracted observations of *this* property (§25.12 opt-in).
    cell_meas = [
        m
        for m in active_measurements(store, material_id, include_retracted=True)
        if m.get("property_name") == prop_name
    ]
    active = [m for m in cell_meas if not is_retracted(store, m["id"])]
    retracted = [m for m in cell_meas if is_retracted(store, m["id"])]
    mentioned_miss = is_mentioned_without_observation(store, material_id, property_id)

    signals: dict[str, Any] = {
        "active_observations": len(active),
        "retracted_observations": len(retracted),
        "mentioned_without_observation": mentioned_miss,
        "recall_prior": recall_prior,
    }

    if active:
        verdict = PRESENT if any(_has_value(m) for m in active) else COVERED
        return _emit(verdict, 0.0, 0.0, signals, material_id, prop_name)
    if retracted:
        # Only withdrawn measurements: a datum was observed then retracted. Per
        # §25.12 this is its own class — never ``covered`` and not scored as absence.
        return _emit(RETRACTED, 0.0, 0.0, signals, material_id, prop_name)
    if mentioned_miss:
        if value_gate:
            # §33/N2: does the mentioning prose actually STATE a value, or only name
            # the property? Only a definitive "no value" (False) downgrades; missing
            # / positive evidence (None / True) leaves the miss verdict untouched.
            vp = mention_value_status(store, material_id, property_id)
            signals["mention_value_present"] = vp
            if vp is False:
                # Property named but never measured -> a genuine gap, not a miss.
                # Collapse the existence prior to the value-gate floor and threshold.
                p_ta, p_em = _bayes_absence(VALUE_GATE_EXISTS_PRIOR, EXTRACTOR_RECALL)
                return _emit(
                    _verdict_from_p_missed(p_em), p_ta, p_em, signals, material_id, prop_name
                )
        # Mentioned but never measured -> the extractor most plausibly missed it.
        p_ta, p_em = _bayes_absence(MENTION_EXISTS_PRIOR, EXTRACTOR_RECALL)
        return _emit(POSSIBLE_MISS, p_ta, p_em, signals, material_id, prop_name)

    # Empty and unmentioned: let the recall prior decide via Bayes.
    p_ta, p_em = _bayes_absence(recall_prior, EXTRACTOR_RECALL)
    return _emit(_verdict_from_p_missed(p_em), p_ta, p_em, signals, material_id, prop_name)


def _emit(
    verdict: str,
    p_truly_absent: float,
    p_extractor_missed: float,
    signals: dict[str, Any],
    material_id: str,
    prop_name: str,
) -> AbsenceSignal:
    _log.info(
        "classify_cell.done",
        material_id=material_id,
        property_name=prop_name,
        verdict=verdict,
        p_truly_absent=p_truly_absent,
        p_extractor_missed=p_extractor_missed,
    )
    return AbsenceSignal(
        verdict=verdict,
        p_truly_absent=p_truly_absent,
        p_extractor_missed=p_extractor_missed,
        signals=signals,
    )
