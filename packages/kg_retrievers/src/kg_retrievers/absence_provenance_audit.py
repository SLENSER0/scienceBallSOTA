"""§25.13 — provenance audit over enriched absence-verdict cells.

Before an agent trusts a batch of §25.13 absence verdicts — presenting some
cells as настоящие пробелы (genuine gaps), others as пропуски извлечения
(extraction misses) or retracted observations — the *provenance* behind each
verdict must be internally consistent. A verdict is only as honest as the
evidence recorded alongside it: a probability outside ``[0, 1]`` is a broken
posterior, a ``possible_miss`` with **no** MENTIONS signal contradicts its own
justification, a cell with no ``calibrated`` flag was never checked for
calibration at all, and a ``retracted`` verdict with no retracted evidence is a
tombstone pointing at nothing (§25.12).

This module is a read-only linter over already-enriched absence cell dicts. It
never touches the graph — the Kuzu note holds transitively: any custom node
prop (retraction tombstone, calibration metadata) was read upstream via
``get_node`` and folded into the plain dict this audit consumes, never a RETURN
column. :func:`audit_absence_cells` walks the batch and emits one
:class:`AuditViolation` per rule breach, keyed by one of four documented codes:

- ``prob_range`` — ``p_truly_absent`` or ``p_extractor_missed`` fell outside
  ``[0, 1]`` (a malformed probability);
- ``miss_without_mention`` — the verdict is ``possible_miss`` yet the cell's
  MENTIONS signal is 0/absent, so the "extractor probably missed it" story has
  no support;
- ``no_calibration_state`` — ``absence_meta`` carries no ``calibrated`` key, so
  we cannot say whether the probabilities were calibrated;
- ``retracted_without_evidence`` — the verdict is ``retracted`` but no retracted
  evidence was recorded.

The result is a frozen :class:`AuditReport`: the list of violations, the number
of cells checked, and ``ok`` (True iff the batch is clean).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger
from kg_retrievers.absence_signals import POSSIBLE_MISS, RETRACTED

_log = get_logger("absence_provenance_audit")

# -- audit codes -----------------------------------------------------------
# A malformed probability — p_truly_absent / p_extractor_missed outside [0, 1].
PROB_RANGE = "prob_range"
# A possible_miss verdict with no MENTIONS signal — its justification is empty.
MISS_WITHOUT_MENTION = "miss_without_mention"
# No `calibrated` key in absence_meta — calibration state is unknown.
NO_CALIBRATION_STATE = "no_calibration_state"
# A retracted verdict with no recorded retracted evidence (§25.12 tombstone).
RETRACTED_WITHOUT_EVIDENCE = "retracted_without_evidence"

# The four documented codes, frozen for callers (and the test) to assert over.
AUDIT_CODES = frozenset(
    {PROB_RANGE, MISS_WITHOUT_MENTION, NO_CALIBRATION_STATE, RETRACTED_WITHOUT_EVIDENCE}
)

# Probability keys that must lie within the closed unit interval when present.
_PROB_KEYS = ("p_truly_absent", "p_extractor_missed")


@dataclass(frozen=True)
class AuditViolation:
    """One provenance breach on a single absence cell (§25.13).

    ``material_id`` / ``property_name`` locate the offending cell; ``code`` is
    one of the four documented audit codes (:data:`AUDIT_CODES`); ``detail`` is
    a short RU/EN gloss of what went wrong.
    """

    material_id: str
    property_name: str
    code: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "property_name": self.property_name,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AuditReport:
    """Batch-level provenance audit result over §25.13 absence cells.

    ``violations`` is the (possibly empty) list of :class:`AuditViolation`;
    ``n_checked`` is the number of cells walked; ``ok`` is True iff no violation
    was raised.
    """

    violations: list[AuditViolation]
    n_checked: int
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "violations": [v.as_dict() for v in self.violations],
            "n_checked": self.n_checked,
            "ok": self.ok,
        }


def _cell_id(cell: dict[str, Any]) -> tuple[str, str]:
    """Best-effort (material_id, property_name) locator for a cell dict."""
    material = str(cell.get("material_id", ""))
    prop = str(cell.get("property_name", ""))
    return material, prop


def _mentions_signal(cell: dict[str, Any]) -> int:
    """The cell's MENTIONS count — 0 when the key is absent or non-numeric."""
    raw = cell.get("mentions", cell.get("n_mentions", 0))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _has_retracted_evidence(cell: dict[str, Any]) -> bool:
    """True when the cell records any retracted evidence (§25.12 tombstone)."""
    if cell.get("retracted_evidence"):
        return True
    try:
        return int(cell.get("n_retracted", 0)) > 0
    except (TypeError, ValueError):
        return False


def _audit_cell(cell: dict[str, Any]) -> list[AuditViolation]:
    """Emit every provenance violation raised by a single absence cell."""
    material, prop = _cell_id(cell)
    out: list[AuditViolation] = []

    # (1) prob_range — any present probability must lie within [0, 1].
    for key in _PROB_KEYS:
        if key not in cell:
            continue
        value = cell[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            out.append(
                AuditViolation(
                    material,
                    prop,
                    PROB_RANGE,
                    f"{key} не число / not numeric: {value!r}",
                )
            )
        elif not (0.0 <= float(value) <= 1.0):
            out.append(
                AuditViolation(
                    material,
                    prop,
                    PROB_RANGE,
                    f"{key}={value} вне [0,1] / outside [0,1]",
                )
            )

    verdict = cell.get("verdict")

    # (2) miss_without_mention — possible_miss with no MENTIONS support.
    if verdict == POSSIBLE_MISS and _mentions_signal(cell) <= 0:
        out.append(
            AuditViolation(
                material,
                prop,
                MISS_WITHOUT_MENTION,
                "possible_miss без сигнала MENTIONS / no MENTIONS signal",
            )
        )

    # (3) no_calibration_state — absence_meta lacks a `calibrated` key.
    meta = cell.get("absence_meta")
    if not isinstance(meta, dict) or "calibrated" not in meta:
        out.append(
            AuditViolation(
                material,
                prop,
                NO_CALIBRATION_STATE,
                "нет ключа calibrated в absence_meta / missing calibrated key",
            )
        )

    # (4) retracted_without_evidence — retracted verdict, empty tombstone.
    if verdict == RETRACTED and not _has_retracted_evidence(cell):
        out.append(
            AuditViolation(
                material,
                prop,
                RETRACTED_WITHOUT_EVIDENCE,
                "retracted без отозванных доказательств / no retracted evidence",
            )
        )

    return out


def audit_absence_cells(cells: list[dict[str, Any]]) -> AuditReport:
    """Audit enriched §25.13 absence cells for provenance consistency.

    Walks every cell in ``cells``, emitting an :class:`AuditViolation` per rule
    breach (codes in :data:`AUDIT_CODES`). ``n_checked`` equals ``len(cells)``
    and ``ok`` is True iff no violation was raised. Read-only — consumes only
    the plain enriched dicts and never touches the graph.
    """
    violations: list[AuditViolation] = []
    for cell in cells:
        violations.extend(_audit_cell(cell))
    report = AuditReport(
        violations=violations,
        n_checked=len(cells),
        ok=not violations,
    )
    _log.debug(
        "absence provenance audit: n_checked=%d n_violations=%d ok=%s",
        report.n_checked,
        len(report.violations),
        report.ok,
    )
    return report
