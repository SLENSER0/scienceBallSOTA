"""Tests for §25.13 absence-verdict provenance audit.

Hand-checkable: each cell is a plain enriched dict; we assert the exact codes
raised (or the clean case) against the four documented rules. No graph is
touched — the audit is a read-only linter over dicts.
"""

from __future__ import annotations

from kg_retrievers.absence_provenance_audit import (
    AUDIT_CODES,
    MISS_WITHOUT_MENTION,
    NO_CALIBRATION_STATE,
    PROB_RANGE,
    RETRACTED_WITHOUT_EVIDENCE,
    AuditReport,
    AuditViolation,
    audit_absence_cells,
)
from kg_retrievers.absence_signals import GENUINE_GAP, POSSIBLE_MISS, RETRACTED


def _valid_cell() -> dict:
    """A fully-populated, internally-consistent absence cell."""
    return {
        "material_id": "mat-1",
        "property_name": "band_gap",
        "verdict": GENUINE_GAP,
        "p_truly_absent": 0.8,
        "p_extractor_missed": 0.2,
        "mentions": 0,
        "absence_meta": {"calibrated": True},
    }


def test_valid_cell_no_violations() -> None:
    # (1) a fully-populated valid cell -> violations == [] and ok True.
    report = audit_absence_cells([_valid_cell()])
    assert isinstance(report, AuditReport)
    assert report.violations == []
    assert report.ok is True
    assert report.n_checked == 1


def test_prob_out_of_range() -> None:
    # (2) p_truly_absent = 1.5 -> a 'prob_range' violation.
    cell = _valid_cell()
    cell["p_truly_absent"] = 1.5
    report = audit_absence_cells([cell])
    codes = {v.code for v in report.violations}
    assert PROB_RANGE in codes
    assert report.ok is False


def test_negative_prob_extractor_missed() -> None:
    # p_extractor_missed below 0 is also a 'prob_range' violation.
    cell = _valid_cell()
    cell["p_extractor_missed"] = -0.1
    report = audit_absence_cells([cell])
    assert any(v.code == PROB_RANGE for v in report.violations)


def test_possible_miss_without_mention() -> None:
    # (3) verdict possible_miss with mentions == 0 -> 'miss_without_mention'.
    cell = _valid_cell()
    cell["verdict"] = POSSIBLE_MISS
    cell["mentions"] = 0
    report = audit_absence_cells([cell])
    assert any(v.code == MISS_WITHOUT_MENTION for v in report.violations)
    assert report.ok is False


def test_possible_miss_with_mention_ok() -> None:
    # A possible_miss backed by a MENTIONS signal raises no miss violation.
    cell = _valid_cell()
    cell["verdict"] = POSSIBLE_MISS
    cell["mentions"] = 3
    report = audit_absence_cells([cell])
    assert not any(v.code == MISS_WITHOUT_MENTION for v in report.violations)


def test_missing_mentions_key_is_absent_signal() -> None:
    # A possible_miss whose mentions key is *absent* is still unsupported.
    cell = _valid_cell()
    cell["verdict"] = POSSIBLE_MISS
    del cell["mentions"]
    report = audit_absence_cells([cell])
    assert any(v.code == MISS_WITHOUT_MENTION for v in report.violations)


def test_missing_calibration_state() -> None:
    # (4) a cell missing 'calibrated' -> 'no_calibration_state'.
    cell = _valid_cell()
    cell["absence_meta"] = {}  # meta present but no calibrated key
    report = audit_absence_cells([cell])
    assert any(v.code == NO_CALIBRATION_STATE for v in report.violations)

    cell2 = _valid_cell()
    del cell2["absence_meta"]  # absence_meta absent entirely
    report2 = audit_absence_cells([cell2])
    assert any(v.code == NO_CALIBRATION_STATE for v in report2.violations)


def test_retracted_without_evidence() -> None:
    cell = _valid_cell()
    cell["verdict"] = RETRACTED  # no retracted_evidence / n_retracted recorded
    report = audit_absence_cells([cell])
    assert any(v.code == RETRACTED_WITHOUT_EVIDENCE for v in report.violations)


def test_retracted_with_evidence_ok() -> None:
    cell = _valid_cell()
    cell["verdict"] = RETRACTED
    cell["retracted_evidence"] = ["meas-9"]
    report = audit_absence_cells([cell])
    assert not any(v.code == RETRACTED_WITHOUT_EVIDENCE for v in report.violations)

    cell2 = _valid_cell()
    cell2["verdict"] = RETRACTED
    cell2["n_retracted"] = 2
    report2 = audit_absence_cells([cell2])
    assert not any(v.code == RETRACTED_WITHOUT_EVIDENCE for v in report2.violations)


def test_n_checked_matches_len() -> None:
    # (5) n_checked == len(cells).
    cells = [_valid_cell() for _ in range(5)]
    report = audit_absence_cells(cells)
    assert report.n_checked == len(cells) == 5

    assert audit_absence_cells([]).n_checked == 0


def test_ok_false_whenever_any_violation() -> None:
    # (6) ok is False whenever any violation exists; True on a clean batch.
    dirty = _valid_cell()
    dirty["p_truly_absent"] = 2.0
    report = audit_absence_cells([_valid_cell(), dirty])
    assert len(report.violations) >= 1
    assert report.ok is False

    clean = audit_absence_cells([_valid_cell(), _valid_cell()])
    assert clean.violations == []
    assert clean.ok is True


def test_empty_batch_is_ok() -> None:
    report = audit_absence_cells([])
    assert report.violations == []
    assert report.ok is True
    assert report.n_checked == 0


def test_every_code_is_documented() -> None:
    # (7) each AuditViolation.code is one of the four documented codes.
    cell = _valid_cell()
    cell["verdict"] = POSSIBLE_MISS  # will trip miss_without_mention
    cell["mentions"] = 0
    cell["p_truly_absent"] = 1.5  # will trip prob_range
    cell["absence_meta"] = {}  # will trip no_calibration_state
    report = audit_absence_cells([cell])
    assert len(report.violations) >= 3
    for v in report.violations:
        assert isinstance(v, AuditViolation)
        assert v.code in AUDIT_CODES
    assert len(AUDIT_CODES) == 4


def test_as_dict_round_trips() -> None:
    cell = _valid_cell()
    cell["p_extractor_missed"] = 5.0
    report = audit_absence_cells([cell])
    d = report.as_dict()
    assert d["n_checked"] == 1
    assert d["ok"] is False
    assert isinstance(d["violations"], list)
    first = d["violations"][0]
    assert set(first) == {"material_id", "property_name", "code", "detail"}
    assert first["code"] in AUDIT_CODES
    assert first["material_id"] == "mat-1"
    assert first["property_name"] == "band_gap"
