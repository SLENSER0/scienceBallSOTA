"""Golden acceptance cases loader (§24.18)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# packages/kg_eval/src/kg_eval/golden.py -> packages/kg_eval
_PKG_ROOT = Path(__file__).resolve().parents[2]
_DATA = _PKG_ROOT / "data"


@dataclass
class GoldenCase:
    id: str
    title: str
    query: str
    query_en: str | None = None
    expected_entities: list[str] = field(default_factory=list)
    expected_constraint_units: list[str] = field(default_factory=list)
    expected_practice_types: list[str] = field(default_factory=list)
    expected_last_n_years: int | None = None
    expected_query_type: str | None = None
    expected_comparison: bool = False
    expect_gap: bool = False
    expect_contradiction: bool = False
    expect_table: bool = False
    expect_solutions: list[str] = field(default_factory=list)
    expect_facts_property: str | None = None
    min_evidence: int = 0


def load_cases(suite: str = "domain_science_ball") -> list[GoldenCase]:
    path = _DATA / suite / "cases.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenCase(**{k: v for k, v in row.items() if k in GoldenCase.__annotations__})
        for row in raw
    ]
