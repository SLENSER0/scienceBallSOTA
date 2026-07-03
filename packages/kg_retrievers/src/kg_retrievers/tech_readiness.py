"""Technology-readiness (TRL) scoring over technology solutions (§24.8).

Оценка технологической готовности (*technology-readiness level*, TRL 1..9) для
``TechnologySolution`` — по стадии практики и подтверждающему эвиденсу решение
относится к одному из уровней зрелости:

* **industrial practice** (промышленная эксплуатация) → TRL 8-9;
* **pilot / demonstration** (пилотная / опытно-демонстрационная) → TRL 6-7;
* **lab-scale** (лабораторная стадия) → TRL 3-4;
* **concept** (концепция, без данных) → TRL 1-2.

English: :func:`assess_readiness` reads a solution's maturity signal off its
``practice_type`` (plus a few maturity fields and free-text descriptions) and its
linked measurements / evidence, maps it to a two-level TRL band, then bumps to the
top of the band when the supporting evidence is strong (peer-reviewed / patent /
standard, or two-plus corroborating items). The result is always clamped to 1..9.

Kuzu note: a solution's ``practice_type`` and every custom field are read back
through :meth:`KuzuGraphStore.get_node`; the neighbour walk only returns base
``Node`` columns (``id`` / ``label`` / ``evidence_strength`` / ``name`` / ``text`` /
``practice_type`` / ``source_type``). The module is read-only: it never writes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Node label of the technology solution being scored (§24.2 / §24.8).
SOLUTION_LABEL = "TechnologySolution"

# Bounds of the technology-readiness scale (§24.8): TRL 1 (concept) .. TRL 9 (proven).
TRL_MIN = 1
TRL_MAX = 9

# TRL assigned when a solution cannot be found in the graph (minimal readiness).
UNKNOWN_TRL = 1

# Two or more corroborating evidence items bump a solution to the top of its band.
EVIDENCE_BUMP_COUNT = 2

# Labels counted as measurement / evidence support for a solution (§24.8).
MEASUREMENT_LABELS: frozenset[str] = frozenset({"Measurement", "TechnoEconomicIndicator"})
EVIDENCE_LABELS: frozenset[str] = frozenset({"Evidence", "Paper", "Document"})
EVIDENCE_ALL_LABELS: frozenset[str] = MEASUREMENT_LABELS | EVIDENCE_LABELS

# Provenance strengths strong enough to lift a solution to the top of its TRL band.
STRONG_STRENGTHS: frozenset[str] = frozenset(
    {"peer_reviewed", "patent", "standard", "experiment_protocol"}
)

# TRL bands per maturity stage: ``stage -> (low, high)`` (§24.8).
STAGE_BANDS: dict[str, tuple[int, int]] = {
    "industrial": (8, 9),
    "pilot": (6, 7),
    "lab": (3, 4),
    "concept": (1, 2),
}

# Maturity stages in descending order — the highest one reached fixes the TRL band.
STAGE_ORDER: tuple[str, ...] = ("industrial", "pilot", "lab", "concept")

# Solution fields that may carry an explicit maturity value (matched exactly).
MATURITY_FIELDS: tuple[str, ...] = (
    "practice_type",
    "stage",
    "maturity",
    "readiness_stage",
    "trl_stage",
    "development_stage",
)

# Exact (normalised) maturity-field values mapped to a stage (§24.8).
STAGE_VOCAB: dict[str, frozenset[str]] = {
    "industrial": frozenset(
        {
            "industrial",
            "industrial_practice",
            "commercial",
            "production",
            "operational",
            "deployed",
            "full_scale",
        }
    ),
    "pilot": frozenset(
        {
            "pilot",
            "pilot_plant",
            "demonstration",
            "demo",
            "prototype",
            "field_trial",
            "semi_industrial",
        }
    ),
    "lab": frozenset({"lab", "laboratory", "lab_scale", "bench", "bench_scale", "experimental"}),
    "concept": frozenset(
        {"concept", "conceptual", "theoretical", "proposed", "idea", "modeling", "simulation"}
    ),
}

# Distinctive free-text keywords per stage (RU/EN) — safe substrings only, no bare "lab".
STAGE_TEXT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "industrial": ("industrial", "commercial", "промышленн", "производств", "эксплуатац"),
    "pilot": ("pilot", "demonstration", "prototype", "пилот", "опытн", "демонстрац"),
    "lab": (
        "laboratory",
        "lab-scale",
        "lab scale",
        "bench-scale",
        "bench scale",
        "лаборатор",
        "стенд",
    ),
    "concept": ("concept", "theoretical", "proposed", "концепт", "теоретич"),
}

# Human-readable phrase per stage for the assessment rationale (RU/EN).
_STAGE_PHRASE: dict[str, str] = {
    "industrial": "industrial practice (промышленная эксплуатация)",
    "pilot": "pilot / demonstration stage (пилотная стадия)",
    "lab": "lab-scale validation (лабораторная стадия)",
    "concept": "concept only (концепция)",
}


@dataclass(frozen=True)
class ReadinessAssessment:
    """Technology-readiness assessment for one solution (§24.8).

    ``trl`` is the inferred readiness level in ``1..9``; ``evidence_count`` counts the
    linked measurement / evidence items; ``has_pilot`` / ``has_industrial`` flag which
    maturity stages were detected (both can be true — a proven industrial solution that
    also passed through a pilot). ``rationale`` is a short human-readable justification.
    """

    solution_id: str
    trl: int
    evidence_count: int
    has_pilot: bool
    has_industrial: bool
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{solution_id, trl, evidence_count, has_pilot, has_industrial,
        rationale}``."""
        return {
            "solution_id": self.solution_id,
            "trl": self.trl,
            "evidence_count": self.evidence_count,
            "has_pilot": self.has_pilot,
            "has_industrial": self.has_industrial,
            "rationale": self.rationale,
        }


def _norm(value: object) -> str:
    """Normalise a maturity value: lower-cased, spaces/hyphens folded to ``_`` (else ``""``)."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _vocab_stage(value: object) -> str | None:
    """Stage of an exact (normalised) maturity-field value, or ``None`` when unrecognised."""
    key = _norm(value)
    if not key:
        return None
    for stage, vocab in STAGE_VOCAB.items():
        if key in vocab:
            return stage
    return None


def _text_stages(texts: Iterable[object]) -> set[str]:
    """Stages implied by any distinctive keyword found in the given free-text strings."""
    found: set[str] = set()
    for raw in texts:
        if not isinstance(raw, str) or not raw:
            continue
        low = raw.lower()
        for stage, keywords in STAGE_TEXT_KEYWORDS.items():
            if any(kw in low for kw in keywords):
                found.add(stage)
    return found


def _linked_nodes(store: KuzuGraphStore, solution_id: str) -> list[dict[str, Any]]:
    """Distinct nodes linked to the solution (either direction), as base-column dicts.

    Only queryable ``Node`` columns are returned; DISTINCT + a Python de-dup on ``id``
    guard against a node reachable through several relations being counted twice.
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[r:Rel]-(m:Node) "
        "RETURN DISTINCT m.id, m.label, m.evidence_strength, m.name, m.text, "
        "m.practice_type, m.source_type",
        {"sid": solution_id},
    )
    seen: dict[str, dict[str, Any]] = {}
    for mid, label, strength, name, text, ptype, stype in rows:
        if mid in seen:
            continue
        seen[mid] = {
            "id": mid,
            "label": label,
            "evidence_strength": strength,
            "name": name,
            "text": text,
            "practice_type": ptype,
            "source_type": stype,
        }
    return list(seen.values())


def _detect_stages(node: dict[str, Any], linked: list[dict[str, Any]]) -> set[str]:
    """All maturity stages evidenced by the solution and its linked nodes (§24.8)."""
    stages: set[str] = set()
    for field in MATURITY_FIELDS:
        stage = _vocab_stage(node.get(field))
        if stage:
            stages.add(stage)
    stages |= _text_stages((node.get("name"), node.get("canonical_name"), node.get("text")))
    for item in linked:
        stage = _vocab_stage(item.get("practice_type"))
        if stage:
            stages.add(stage)
        stages |= _text_stages((item.get("name"), item.get("text")))
    return stages


def _top_stage(stages: set[str], evidence_count: int) -> str:
    """The highest maturity stage present; defaults to lab (data) / concept (none)."""
    for stage in STAGE_ORDER:
        if stage in stages:
            return stage
    return "lab" if evidence_count > 0 else "concept"


def _rationale(
    stage: str,
    stages: set[str],
    evidence_count: int,
    strong: bool,
    has_pilot: bool,
    has_industrial: bool,
    trl: int,
) -> str:
    """Short, auditable justification for the assigned TRL (§24.8)."""
    if stage == "concept" and not stages and evidence_count == 0:
        base = "no maturity signal and no supporting evidence (нет данных)"
    elif stage == "lab" and "lab" not in stages:
        base = "no explicit maturity signal; measurements imply lab-scale (лаб. данные)"
    else:
        base = f"detected {_STAGE_PHRASE[stage]}"
    strong_note = "; strong evidence (сильный эвиденс)" if strong else ""
    return (
        f"{base}; evidence_count={evidence_count}{strong_note}; "
        f"has_pilot={has_pilot}; has_industrial={has_industrial} -> TRL {trl}"
    )


def assess_readiness(store: KuzuGraphStore, solution_id: str) -> ReadinessAssessment:
    """Assess a solution's technology-readiness level in ``1..9`` (§24.8).

    Reads the solution's maturity signal (``practice_type`` + maturity fields + free
    text) and its linked measurements / evidence, maps the highest reached stage to a
    TRL band (industrial 8-9, pilot 6-7, lab 3-4, concept 1-2), and bumps to the top of
    the band when the evidence is strong (peer-reviewed / patent / standard, or two-plus
    corroborating items). The result is always clamped to ``1..9``. An unknown
    ``solution_id`` yields a minimal-TRL assessment (graceful, never raises).
    """
    node = store.get_node(solution_id)
    if node is None:
        return ReadinessAssessment(
            solution_id=solution_id,
            trl=UNKNOWN_TRL,
            evidence_count=0,
            has_pilot=False,
            has_industrial=False,
            rationale=(
                "unknown solution — node not found in graph (решение не найдено); "
                f"assigned minimal TRL {UNKNOWN_TRL}"
            ),
        )

    linked = _linked_nodes(store, solution_id)
    evidence_count = sum(1 for item in linked if item.get("label") in EVIDENCE_ALL_LABELS)
    strong = any(_norm(item.get("evidence_strength")) in STRONG_STRENGTHS for item in linked)

    stages = _detect_stages(node, linked)
    has_industrial = "industrial" in stages
    has_pilot = "pilot" in stages

    stage = _top_stage(stages, evidence_count)
    low, high = STAGE_BANDS[stage]
    bump = 1 if (evidence_count >= EVIDENCE_BUMP_COUNT or strong) else 0
    trl = max(TRL_MIN, min(TRL_MAX, min(low + bump, high)))

    rationale = _rationale(stage, stages, evidence_count, strong, has_pilot, has_industrial, trl)
    return ReadinessAssessment(
        solution_id=solution_id,
        trl=trl,
        evidence_count=evidence_count,
        has_pilot=has_pilot,
        has_industrial=has_industrial,
        rationale=rationale,
    )
