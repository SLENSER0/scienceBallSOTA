"""Extraction-recall evaluation by modality on a gold set (§25.16).

Turns confidence-of-absence from a hand-tuned heuristic into a *measured* number.
The absence layer (§25.11) needs a per-modality recall (полнота извлечения) to tell a
real knowledge gap from mere non-extraction; §25.10 supplies **heuristic** priors
(``catalog_row ≈ 0.98``, ``table_row ≈ 0.90``, ``prose ≈ 0.15`` offline). This module
*checks those priors against reality*: it runs a deterministic, LLM-free reference
extractor over a modality-split gold set and reports recall per modality and overall,
with attribution ``fact → evidence → modality``.

Why the prose blind spot is real (not fabricated). Structured rows (``table_row`` /
``catalog_row``) carry an explicit ``subject :: property = value unit`` shape, so an
offline parser recovers them almost perfectly. Dense scientific prose packs several
materials and several measurements into one sentence; binding *which* value belongs to
*which* subject/property needs an LLM. The offline extractor here refuses to guess —
it only emits a prose fact when a sentence has exactly one material and exactly one
measurement of a given class — so most prose facts go unrecovered. The low prose recall
therefore *emerges* from the corpus, and that number is exactly the calibration input
the absence layer should consume in place of the heuristic prior.

Matching model. A gold fact is *extracted* iff its ``fact_key`` (from
:mod:`kg_eval.extraction_recall_eval_2516`) — the tuple
``(doc_id, subject, property_name, value)`` — appears in the set of extracted keys.
Recall is ``extracted / expected`` per gold modality and overall. Modalities whose
recall falls strictly below ``blind_spot_at`` (default ``0.5``) are reported as blind
spots. Precision is **deliberately not computed**: the reference paths are deterministic
and carry no false-positive labels, so a precision number would be meaningless here.

CLI (критерий приёмки §25.16)::

    python -m kg_eval.run_extraction_eval                     # JSON report to stdout
    python -m kg_eval.run_extraction_eval --gold PATH \\
        --backend offline --extraction-run-id run-42 \\
        --output report.json --markdown
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from kg_eval.extraction_eval import extract
from kg_eval.extraction_recall_eval_2516 import (
    ExtractionRecallReport,
    evaluate_extraction_recall,
    fact_key,
)

# packages/kg_eval/src/kg_eval/run_extraction_eval.py -> packages/kg_eval
_PKG_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_PATH = _PKG_ROOT / "data" / "gold_extraction" / "gold_extraction.json"

# Modalities recovered by pure structured-cell parsing (no natural-language binding).
STRUCTURED_MODALITIES: frozenset[str] = frozenset({"table_row", "catalog_row"})
# Free-text modality label used in the gold set; mapped to the ``prose`` prior below.
PROSE_MODALITY: str = "chunk"

# Modality -> the §25.10 prior key so measured recall lines up with the heuristic it
# is meant to replace (``chunk`` is this corpus's label for free-text ``prose``).
_PRIOR_KEY: dict[str, str] = {
    "catalog_row": "catalog_row",
    "table_row": "table_row",
    "chunk": "prose",
}

# Units the offline structured parser trusts (value + unit → property is read from the
# cell, so the map is only a validity gate, not a property classifier).
_KNOWN_UNITS: frozenset[str] = frozenset(
    {"HV", "HRC", "HB", "MPa", "GPa", "°C", "K", "%", "h", "min", "s", "µm", "nm",
     "mm/year", "A/dm^2"}
)

# A clean structured value cell: a single number followed by a single known unit. A
# range ("1020-1080 MPa"), an operator ("≥ 950 MPa") or an unknown unit fails to match
# and is dropped — the offline path canonicalises nothing, which is an honest miss.
_STRUCTURED_VALUE = re.compile(
    r"^\s*(?P<num>-?\d+(?:[.,]\d+)?)\s*(?P<unit>\S+)\s*$"
)
_STRUCTURED_CELL = re.compile(r"^(?P<subject>.+?)::(?P<property>.+?)=(?P<value>.+)$")


@dataclass(frozen=True)
class GoldFact:
    """One expected fact with its source modality/evidence provenance (§25.16)."""

    doc_id: str
    modality: str
    subject: str
    property_name: str
    value: float
    unit: str
    evidence: str

    def as_row(self) -> dict:
        """Row shaped for :func:`evaluate_extraction_recall` (carries ``modality``)."""
        return {
            "doc_id": self.doc_id,
            "modality": self.modality,
            "subject": self.subject,
            "property_name": self.property_name,
            "value": self.value,
        }


@dataclass(frozen=True)
class EvidenceUnit:
    """A single source surface (one row/sentence) plus the facts it should yield."""

    doc_id: str
    modality: str
    content: str
    facts: tuple[GoldFact, ...]


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def load_gold(path: str | Path = DEFAULT_GOLD_PATH) -> list[EvidenceUnit]:
    """Load the modality-split gold set into evidence units (§25.16).

    Each unit lists a source ``content`` surface and the facts a complete extractor
    must recover from it. A fact with a non-numeric ``value`` raises loudly so a
    malformed gold file fails in CI rather than silently under-counting.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    units: list[EvidenceUnit] = []
    for u in raw["units"]:
        doc_id = u["doc_id"]
        modality = u["modality"]
        facts: list[GoldFact] = []
        for f in u["facts"]:
            value = _as_float(f.get("value"))
            if value is None:
                raise ValueError(
                    f"gold {doc_id}/{modality}: non-numeric value for "
                    f"{f.get('subject')!r}/{f.get('property_name')!r}"
                )
            facts.append(
                GoldFact(
                    doc_id=doc_id,
                    modality=modality,
                    subject=f["subject"],
                    property_name=f["property_name"],
                    value=value,
                    unit=f.get("unit", ""),
                    evidence=u["content"],
                )
            )
        units.append(EvidenceUnit(doc_id, modality, u["content"], tuple(facts)))
    return units


# --------------------------------------------------------------------------- #
# Deterministic, LLM-free reference extractor (offline path)                   #
# --------------------------------------------------------------------------- #
def _extract_structured(unit: EvidenceUnit) -> list[dict]:
    """Parse a structured ``subject :: property = value unit`` cell.

    Emits a fact only for a clean ``number unit`` value whose unit is known; ranges,
    operators and unknown units are dropped (the offline path canonicalises nothing).
    """
    m = _STRUCTURED_CELL.match(unit.content)
    if not m:
        return []
    vm = _STRUCTURED_VALUE.match(m.group("value"))
    if not vm or vm.group("unit") not in _KNOWN_UNITS:
        return []
    value = _as_float(vm.group("num").replace(",", "."))
    if value is None:
        return []
    return [
        {
            "doc_id": unit.doc_id,
            "modality": unit.modality,
            "subject": m.group("subject").strip(),
            "property_name": m.group("property").strip(),
            "value": value,
            "evidence": unit.content,
        }
    ]


def _extract_prose(unit: EvidenceUnit) -> list[dict]:
    """Offline prose extraction with honest no-LLM binding limits (§25.16).

    Reuses the deterministic reference extractor (:func:`kg_eval.extraction_eval.extract`)
    for materials + measurements, then binds a measurement to a subject only when the
    sentence is unambiguous: exactly one material *and* exactly one measurement of that
    property class. Dense multi-material / multi-measurement sentences yield nothing —
    that abstention is the measured prose blind spot.
    """
    preds = extract(unit.content)
    materials = [p.text for p in preds if p.type == "material"]
    if len(materials) != 1:
        return []
    subject = materials[0]

    by_class: dict[str, list[float]] = {}
    for p in preds:
        if p.type == "measurement" and p.property and p.value is not None:
            by_class.setdefault(p.property, []).append(float(p.value))

    out: list[dict] = []
    for prop, values in by_class.items():
        if len(values) != 1:  # same-class collision → cannot bind without an LLM
            continue
        out.append(
            {
                "doc_id": unit.doc_id,
                "modality": unit.modality,
                "subject": subject,
                "property_name": prop,
                "value": values[0],
                "evidence": unit.content,
            }
        )
    return out


def extract_unit(unit: EvidenceUnit) -> list[dict]:
    """Offline reference extraction for one evidence unit, routed by modality."""
    if unit.modality in STRUCTURED_MODALITIES:
        return _extract_structured(unit)
    return _extract_prose(unit)


# --------------------------------------------------------------------------- #
# Recall report                                                               #
# --------------------------------------------------------------------------- #
def _modality_priors(modalities: list[str]) -> dict[str, dict[str, float]]:
    """Heuristic §25.10 priors (offline & LLM) for the observed modalities.

    Returns ``{}`` if the priors package is unavailable so the eval never hard-fails
    on an optional dependency — the recall numbers stand on their own.
    """
    try:
        from kg_retrievers.modality_recall_prior import recall_for_context
    except Exception:  # pragma: no cover - optional dependency
        return {}
    priors: dict[str, dict[str, float]] = {}
    for modality in modalities:
        key = _PRIOR_KEY.get(modality, modality)
        priors[modality] = {
            "offline": recall_for_context(key, llm_enabled=False).recall,
            "llm": recall_for_context(key, llm_enabled=True).recall,
        }
    return priors


@dataclass
class GoldRecallReport:
    """Full §25.16 extraction-recall report with attribution and prior comparison."""

    core: ExtractionRecallReport
    blind_spots: list[str]
    blind_spot_at: float
    attribution: list[dict]
    priors: dict[str, dict[str, float]]
    n_units: int
    backend: str
    extraction_run_id: str | None = None
    per_modality_extra: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        base = self.core.as_dict()
        by_modality = []
        for name, mr in self.core.by_modality.items():
            row = mr.as_dict()
            row["is_blind_spot"] = name in self.blind_spots
            row["prior"] = self.priors.get(name, {})
            row.update(self.per_modality_extra.get(name, {}))
            by_modality.append(row)
        return {
            "backend": self.backend,
            "extraction_run_id": self.extraction_run_id,
            "n_units": self.n_units,
            "by_modality": by_modality,
            "overall_recall": base["overall_recall"],
            "expected_total": base["expected_total"],
            "extracted_total": base["extracted_total"],
            "blind_spots": list(self.blind_spots),
            "blind_spot_at": self.blind_spot_at,
            "precision_note": (
                "Precision intentionally not computed: deterministic reference paths "
                "carry no false-positive labels (§25.16)."
            ),
            "attribution": self.attribution,
        }


def run_extraction_eval(
    gold_path: str | Path = DEFAULT_GOLD_PATH,
    *,
    blind_spot_at: float = 0.5,
    backend: str = "offline",
    extraction_run_id: str | None = None,
) -> GoldRecallReport:
    """Run the modality-attributed extraction-recall eval over the gold set (§25.16).

    Runs the offline reference extractor per evidence unit, attributes each extracted
    fact to ``doc_id + modality`` (``observation_extracted_from``), scores recall per
    modality and overall (reusing :func:`evaluate_extraction_recall`), flags blind-spot
    modalities and lines the measured recall up against the §25.10 heuristic priors.
    """
    units = load_gold(gold_path)

    gold_rows: list[dict] = []
    gold_facts: list[GoldFact] = []
    for unit in units:
        for gf in unit.facts:
            gold_rows.append(gf.as_row())
            gold_facts.append(gf)

    extracted_rows: list[dict] = []
    for unit in units:
        extracted_rows.extend(extract_unit(unit))

    core = evaluate_extraction_recall(gold_rows, extracted_rows)
    blind_spots = sorted(
        name for name, mr in core.by_modality.items() if mr.recall < blind_spot_at
    )

    # Attribution: every gold fact → its evidence surface → matched flag (fact→ev→modality).
    extracted_keys = {fact_key(r) for r in extracted_rows}
    attribution = [
        {
            "doc_id": gf.doc_id,
            "modality": gf.modality,
            "subject": gf.subject,
            "property_name": gf.property_name,
            "value": gf.value,
            "unit": gf.unit,
            "evidence": gf.evidence,
            "extracted": fact_key(gf.as_row()) in extracted_keys,
        }
        for gf in gold_facts
    ]

    priors = _modality_priors(list(core.by_modality))
    # Surface the gap between measured recall and the heuristic prior it should replace.
    extra: dict[str, dict] = {}
    for name, mr in core.by_modality.items():
        p = priors.get(name, {})
        if "offline" in p:
            extra[name] = {"recall_minus_prior_offline": round(mr.recall - p["offline"], 4)}

    return GoldRecallReport(
        core=core,
        blind_spots=blind_spots,
        blind_spot_at=blind_spot_at,
        attribution=attribution,
        priors=priors,
        n_units=len(units),
        backend=backend,
        extraction_run_id=extraction_run_id,
        per_modality_extra=extra,
    )


# --------------------------------------------------------------------------- #
# Reporting / CLI                                                             #
# --------------------------------------------------------------------------- #
def to_markdown(report: GoldRecallReport) -> str:
    """Render a compact Markdown blind-spot report of the §25.16 metrics."""
    d = report.as_dict()
    lines = [
        "# Extraction-recall eval by modality (§25.16)",
        "",
        f"Backend: **{d['backend']}** · gold units: **{d['n_units']}** · "
        f"overall recall: **{d['overall_recall']}** "
        f"({d['extracted_total']}/{d['expected_total']} facts).",
        "",
        "| modality | expected | extracted | recall | prior (offline) | blind spot |",
        "|---|---:|---:|---:|---:|:--:|",
    ]
    for m in d["by_modality"]:
        prior = m.get("prior", {}).get("offline")
        prior_s = "—" if prior is None else f"{prior}"
        flag = "⚠︎" if m["is_blind_spot"] else ""
        lines.append(
            f"| {m['modality']} | {m['expected']} | {m['extracted']} | "
            f"{m['recall']} | {prior_s} | {flag} |"
        )
    spots = ", ".join(d["blind_spots"]) or "none"
    lines += [
        "",
        f"**Blind spots** (recall < {d['blind_spot_at']}): **{spots}**.",
        "",
        f"_{d['precision_note']}_",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction-recall eval by modality (§25.16)")
    parser.add_argument("--gold", default=str(DEFAULT_GOLD_PATH), help="path to gold set JSON")
    parser.add_argument("--backend", default="offline", help="extractor backend label")
    parser.add_argument("--extraction-run-id", default=None, help="extraction run id to tag")
    parser.add_argument(
        "--blind-spot-at", type=float, default=0.5, help="recall threshold for a blind spot"
    )
    parser.add_argument("--output", default=None, help="write JSON report to this path")
    parser.add_argument("--markdown", action="store_true", help="also print a Markdown report")
    args = parser.parse_args(argv)

    report = run_extraction_eval(
        args.gold,
        blind_spot_at=args.blind_spot_at,
        backend=args.backend,
        extraction_run_id=args.extraction_run_id,
    )
    payload = report.as_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.markdown:
        print("\n" + to_markdown(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
