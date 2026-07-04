"""Golden-set ER evaluation + CI regression gate (§8.12).

Loads the labelled golden ER sets (``data/golden/{material,equipment,person,
lab}.jsonl``), runs the real resolver (:func:`kg_er.resolve`) over each type's
mentions, and scores the predicted clustering against the gold clustering with
the pairwise / cluster metrics in :mod:`kg_er.metrics` (pairwise P/R/F1, B³,
purity). This turns "ER quality" into a reproducible number: it is what the
demo shows ("Material F1 = 0.9x") and what the CI gate defends against model
regressions.

Each golden line is one *mention* record carrying the same feature fields the
feature builders read (``name``/``formula``/``designation`` for Material,
``manufacturer``/``model`` for Equipment, ``orcid``/``email`` for Person,
``org``/``city``/``country`` for Lab) plus a gold ``canonical_id`` that groups
mentions belonging to the same real-world entity. Gold clusters are the
``canonical_id`` groups; predicted clusters come from ``ResolveResult.clusters``.

Public API
----------
* :func:`load_golden` — parse one ``<type>.jsonl`` into mentions + gold clusters.
* :func:`evaluate_type` — resolve + score one entity type -> :class:`TypeEval`.
* :func:`evaluate_all` — score every configured type -> :class:`EvalReport`.
* :func:`load_thresholds` — per-type F1 acceptance thresholds from YAML.
* ``python -m kg_er.eval`` — print the report and exit non-zero on regression
  (the CI gate; also driven by ``tests/test_golden_eval.py``).

Everything runs on the deterministic scoring path (golden sets are < 50 rows),
so results are stable across runs — no Splink/EM randomness in the gate.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from kg_er.metrics import ERMetrics, all_metrics
from kg_er.pipeline import resolve

# --------------------------------------------------------------------------- #
# Locations                                                                    #
# --------------------------------------------------------------------------- #
_DATA_DIR = Path(__file__).resolve().parent / "data"
GOLDEN_DIR = _DATA_DIR / "golden"
THRESHOLDS_PATH = _DATA_DIR / "er_eval_thresholds.yaml"

# golden file stem -> resolver entity_type (kg_er.SUPPORTED_TYPES)
TYPE_FILES: dict[str, str] = {
    "material": "Material",
    "equipment": "Equipment",
    "person": "Person",
    "lab": "Lab",
}

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "material": 0.85,
    "equipment": 0.85,
    "person": 0.80,
    "lab": 0.80,
}


# --------------------------------------------------------------------------- #
# Result containers                                                            #
# --------------------------------------------------------------------------- #
@dataclass
class TypeEval:
    """Scored evaluation of one entity type against its golden set (§8.12)."""

    entity_type: str
    file: str
    metrics: ERMetrics
    threshold: float
    n_mentions: int
    n_gold_clusters: int
    backend: str

    @property
    def f1(self) -> float:
        """Pairwise F1 — the value gated in CI (§8.12)."""
        return self.metrics.pairwise.f1

    @property
    def passed(self) -> bool:
        return self.f1 >= self.threshold

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "file": self.file,
            "threshold": round(self.threshold, 4),
            "f1": round(self.f1, 4),
            "passed": self.passed,
            "n_mentions": self.n_mentions,
            "n_gold_clusters": self.n_gold_clusters,
            "backend": self.backend,
            "metrics": self.metrics.as_dict(),
        }


@dataclass
class EvalReport:
    """Aggregate golden ER evaluation across all types (§8.12 gate)."""

    types: list[TypeEval] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """The CI gate passes only if every scored type meets its threshold."""
        return bool(self.types) and all(t.passed for t in self.types)

    @property
    def min_f1(self) -> float:
        return min((t.f1 for t in self.types), default=0.0)

    @property
    def mean_f1(self) -> float:
        return sum(t.f1 for t in self.types) / len(self.types) if self.types else 0.0

    def failures(self) -> list[TypeEval]:
        return [t for t in self.types if not t.passed]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "min_f1": round(self.min_f1, 4),
            "mean_f1": round(self.mean_f1, 4),
            "n_types": len(self.types),
            "types": [t.as_dict() for t in self.types],
        }


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #
def load_thresholds(path: Path | None = None) -> dict[str, float]:
    """Load per-type F1 acceptance thresholds; fall back to §8.12 defaults."""
    p = path or THRESHOLDS_PATH
    if not p.exists():
        return dict(_DEFAULT_THRESHOLDS)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = dict(_DEFAULT_THRESHOLDS)
    for k, v in raw.items():
        try:
            out[str(k).lower()] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def load_golden(path: Path) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """Parse a ``<type>.jsonl`` golden file.

    Returns ``(mentions, gold_clusters)`` where ``mentions`` are resolver-ready
    dicts (each with a ``unique_id``, gold ``canonical_id`` stripped) and
    ``gold_clusters`` groups the ``unique_id``s by their gold ``canonical_id``.
    """
    mentions: list[dict[str, Any]] = []
    groups: dict[str, list[str]] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        uid = rec.get("unique_id")
        canonical = rec.get("canonical_id")
        if not uid or not canonical:
            raise ValueError(
                f"{path.name}:{lineno} golden record needs unique_id + canonical_id"
            )
        groups.setdefault(canonical, []).append(uid)
        mention = {k: v for k, v in rec.items() if k != "canonical_id"}
        mentions.append(mention)
    gold_clusters = list(groups.values())
    return mentions, gold_clusters


# --------------------------------------------------------------------------- #
# Evaluation                                                                   #
# --------------------------------------------------------------------------- #
def evaluate_type(
    stem: str,
    entity_type: str,
    *,
    golden_dir: Path | None = None,
    thresholds: dict[str, float] | None = None,
) -> TypeEval:
    """Resolve + score one entity type against its golden set (§8.12)."""
    gdir = golden_dir or GOLDEN_DIR
    path = gdir / f"{stem}.jsonl"
    mentions, gold_clusters = load_golden(path)
    thr = (thresholds or load_thresholds()).get(stem, _DEFAULT_THRESHOLDS.get(stem, 0.85))

    # Deterministic scoring for a labelled set of this size (§8.5) — reproducible.
    result = resolve(entity_type, mentions)
    predicted = [list(c.members) for c in result.clusters]
    metrics = all_metrics(predicted, gold_clusters)

    return TypeEval(
        entity_type=entity_type,
        file=path.name,
        metrics=metrics,
        threshold=thr,
        n_mentions=len(mentions),
        n_gold_clusters=len(gold_clusters),
        backend=str(result.model_card.get("backend", "unknown")),
    )


def evaluate_all(
    *,
    golden_dir: Path | None = None,
    thresholds: dict[str, float] | None = None,
) -> EvalReport:
    """Score every configured entity type into one report (§8.12)."""
    thr = thresholds or load_thresholds()
    report = EvalReport()
    for stem, entity_type in TYPE_FILES.items():
        path = (golden_dir or GOLDEN_DIR) / f"{stem}.jsonl"
        if not path.exists():
            continue
        report.types.append(
            evaluate_type(stem, entity_type, golden_dir=golden_dir, thresholds=thr)
        )
    return report


# --------------------------------------------------------------------------- #
# CLI / CI gate                                                                #
# --------------------------------------------------------------------------- #
def _format(report: EvalReport) -> str:
    lines = [
        "Golden ER evaluation (§8.12) — pairwise-F1 regression gate",
        "=" * 62,
        f"{'type':<12}{'F1':>8}{'prec':>8}{'recall':>8}{'thr':>7}{'B3-F1':>8}  status",
        "-" * 62,
    ]
    for t in report.types:
        pw = t.metrics.pairwise
        status = "PASS" if t.passed else "FAIL"
        lines.append(
            f"{t.entity_type:<12}{t.f1:>8.3f}{pw.precision:>8.3f}{pw.recall:>8.3f}"
            f"{t.threshold:>7.2f}{t.metrics.b_cubed.f1:>8.3f}  {status}"
        )
    lines.append("-" * 62)
    lines.append(
        f"mean F1 = {report.mean_f1:.3f}   min F1 = {report.min_f1:.3f}   "
        f"GATE = {'PASS' if report.passed else 'FAIL'}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the golden ER report; return 1 if any type regresses below threshold."""
    report = evaluate_all()
    if argv and "--json" in argv:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(_format(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
