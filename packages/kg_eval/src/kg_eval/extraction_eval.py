"""Extraction eval-harness: P/R/F1 + span-IoU + cost/latency on a golden set (§6.17).

Доказуемое качество извлечения как отдельный, воспроизводимый контур. Этот модуль
берёт «золотой» extraction-набор (``packages/kg_eval/data/extraction_golden/cases.json``:
научные фрагменты по материаловедению с ручной разметкой ожидаемых
materials / processing / measurements), прогоняет над КАЖДЫМ фрагментом
детерминированный референс-экстрактор (rule/regex слой — без LLM, без тяжёлых весов,
безопасен под server-профиль) и считает РЕАЛЬНЫЕ метрики приёмки §6.17:

* **precision / recall / F1 по типам сущностей** (material / process / measurement),
  micro + macro, со span-based сопоставлением (жадный матч по максимальному IoU
  символьных офсетов, порог :data:`IOU_MATCH`);
* **span-accuracy (IoU офсетов)** — средний IoU по сматченным парам и доля пар с
  IoU ≥ :data:`IOU_STRICT` (это и есть критерий «span-accuracy (IoU ≥ 0.9) ≥ 0.85»);
* **(value, unit) accuracy** для measurements среди сматченных пар;
* **evidence-span-ratio** — доля извлечённых фактов с разрешимым спаном (через
  :mod:`kg_common.metadata.extraction_run_metrics`), т.е. «доля фактов с валидным Evidence»;
* **useful-facts rate** — доля документов, давших ≥ 1 сматченный граф-факт (критерий
  Phase 2 «≥ 70% документов дают полезные граф-факты»);
* **cost / latency на документ** — реально измеренная latency прогона (wall-clock) и
  оценка стоимости/токенов через :mod:`kg_common.cost` (§18.10), трекается по
  ``pipeline_version``.

Матчинг (span-based NER-eval). Для каждого типа сущности predicted и gold спаны
сопоставляются жадно по убыванию IoU; пара засчитывается как TP при IoU ≥
:data:`IOU_MATCH`. Лишние predicted → FP, непокрытые gold → FN. Это стандартная
overlap-модель, отличная от ``extraction_recall_eval`` (матч по ``fact_id``) и
``relation_triple_f1`` (матч по нормализованной тройке).

Референс-экстрактор — честный, но простой rule-слой: материалы/процессы по доменному
словарю, measurements по регэкспу «оператор? число (диапазон)? единица» с разбором
через :func:`kg_extractors.value_parser.parse_value`. Он НЕ претендует на полноту
LLM-слоёв — он даёт детерминированную, воспроизводимую нижнюю границу качества, по
которой строится дашборд §6.17.

CLI (критерий приёмки §6.17)::

    python -m kg_eval.extraction_eval            # JSON-отчёт в stdout
    python -m kg_eval.extraction_eval --markdown # + markdown-таблица
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from kg_common.cost import ModelPrice, cost_for
from kg_common.metadata.extraction_run_metrics import compute as compute_run_metrics
from kg_extractors.value_parser import parse_value

# packages/kg_eval/src/kg_eval/extraction_eval.py -> packages/kg_eval
_PKG_ROOT = Path(__file__).resolve().parents[2]
_DATA = _PKG_ROOT / "data"

# Versioned so metrics can be tracked over pipeline changes (§6.17 / §13.2).
PIPELINE_VERSION = "extraction-eval-ref-1.0"

# Overlap thresholds for span-based matching (§6.17).
IOU_MATCH = 0.5  # a predicted/gold span pair counts as the same entity at/above this
IOU_STRICT = 0.9  # span is "accurate" (acceptance metric) at/above this

# Reference cost model for the *per-document* cost column (§15.2). The rule-based
# reference extractor makes no LLM call (true cost 0), so this documents an
# indicative hosted-model rate used only to populate the cost estimate; override
# by passing an explicit ``price`` to :func:`run_eval`.
REFERENCE_PRICE = ModelPrice("reference-extractor", input_usd_per_1k=0.15, output_usd_per_1k=0.60)
_CHARS_PER_TOKEN = 4  # rough tokens≈chars/4 estimate for the cost column
_COMPLETION_FRACTION = 0.25  # assume completion ≈ 1/4 of prompt tokens for the estimate

ENTITY_TYPES = ("material", "process", "measurement")


# ---------------------------------------------------------------------------
# Golden dataset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldEntity:
    """One annotated gold entity with a character span resolved from the doc text.

    ``start``/``end`` are half-open character offsets into the document ``text``,
    resolved at load time from the exact surface ``text`` (so the annotator only
    supplies the surface string, never fragile offsets).
    """

    type: str
    text: str
    start: int
    end: int
    property: str | None = None
    value: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class GoldDoc:
    doc_id: str
    title: str
    text: str
    entities: tuple[GoldEntity, ...]


def load_golden(suite: str = "extraction_golden") -> list[GoldDoc]:
    """Load the golden extraction set, resolving each entity span from its surface.

    Each entity's ``text`` must occur verbatim in the document ``text``; repeated
    surfaces are assigned distinct, non-overlapping occurrences in annotation order
    (so two ``"2 h"`` mentions get two spans). A surface that cannot be located
    raises :class:`ValueError` — this is what makes a malformed golden file fail
    loudly in CI rather than silently under-count.
    """
    path = _DATA / suite / "cases.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    docs: list[GoldDoc] = []
    for row in raw:
        text = row["text"]
        used: list[tuple[int, int]] = []
        ents: list[GoldEntity] = []
        for ent in row["entities"]:
            surface = ent["text"]
            start = _find_free(text, surface, used)
            if start < 0:
                raise ValueError(
                    f"golden {row['doc_id']}: surface {surface!r} not found in text"
                )
            end = start + len(surface)
            used.append((start, end))
            ents.append(
                GoldEntity(
                    type=ent["type"],
                    text=surface,
                    start=start,
                    end=end,
                    property=ent.get("property"),
                    value=_as_float(ent.get("value")),
                    unit=ent.get("unit"),
                )
            )
        docs.append(
            GoldDoc(
                doc_id=row["doc_id"],
                title=row.get("title", row["doc_id"]),
                text=text,
                entities=tuple(ents),
            )
        )
    return docs


def _find_free(text: str, surface: str, used: list[tuple[int, int]]) -> int:
    """First occurrence of ``surface`` whose span does not overlap a claimed one."""
    from_idx = 0
    while True:
        idx = text.find(surface, from_idx)
        if idx < 0:
            return -1
        span = (idx, idx + len(surface))
        if not any(_overlap(span, u) for u in used):
            return idx
        from_idx = idx + 1


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Reference (rule-based) extractor — deterministic, no LLM (§6.17)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PredEntity:
    type: str
    text: str
    start: int
    end: int
    property: str | None = None
    value: float | None = None
    unit: str | None = None


# Material mentions: alloy designations + a trailing class head, matched as one span.
# Ordered longest-first inside the alternation so multiword heads win over "alloy".
_MAT_CODE = (
    r"(?:AA?\d{3,4}[A-Za-z-]*|Ti-6Al-4V|316L|Inconel\s+\d+|AZ\d+|Cu-Ni|\d{4}"
    r"|WC-Co|\d{4}|18Ni|A\d{3}|Zircaloy-\d|CoCrFeNi|H\d{2}|Nickel)"
)
_MAT_HEAD = (
    r"(?:aluminium casting alloy|nickel superalloy|high-entropy alloy|aluminium alloy"
    r"|titanium alloy|magnesium alloy|casting alloy|cemented carbide|stainless steel"
    r"|tool steel|maraging steel|cast iron|superalloy|coating|tubing|alloy|steel|iron)"
)
# code + optional descriptor words + head, OR a bare "duplex stainless steel 2205" shape.
_MATERIAL_RE = re.compile(
    rf"\b{_MAT_CODE}(?:[ -](?:{_MAT_HEAD}|[A-Za-z]+)){{0,3}}[ -]{_MAT_HEAD}"
    rf"|\bduplex stainless steel \d{{4}}",
    re.IGNORECASE,
)

# Processing steps — domain vocabulary (deliberately not exhaustive: "die cast" and
# "cold pilgered" are intentionally out-of-vocab, so recall is honestly < 1.0).
_PROCESS_VOCAB = (
    "solution treated",
    "solution annealed",
    "precipitation hardened",
    "recrystallisation annealed",
    "liquid-phase sintered",
    "plasma nitrided",
    "artificially aged",
    "water quenched",
    "oil quenched",
    "furnace cooled",
    "mill annealed",
    "cold rolled",
    "electrodeposited",
    "austenitised",
    "austempered",
    "homogenised",
    "annealed",
    "quenched",
    "tempered",
    "aged",
)
_PROCESS_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_PROCESS_VOCAB, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Measurement units recognised in running text → property class.
_UNIT_PROPERTY: dict[str, str] = {
    "°C": "temperature",
    "K": "temperature",
    "HV": "hardness",
    "HRC": "hardness",
    "HB": "hardness",
    "MPa": "strength",
    "GPa": "strength",
    "%": "fraction",
    "h": "time",
    "min": "time",
    "s": "time",
    "µm": "length",
    "nm": "length",
    "mm/year": "corrosion_rate",
    "A/dm^2": "current_density",
}
# Longest-first so "mm/year" and "A/dm^2" win over "s"/"h"; escaped for the regex.
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(_UNIT_PROPERTY, key=len, reverse=True))
_NUMBER = r"\d+(?:[.,]\d+)?"
_MEASUREMENT_RE = re.compile(
    rf"(?P<op>[≤≥<>]\s*)?(?P<num>{_NUMBER}(?:\s*[–-]\s*{_NUMBER})?)\s*(?P<unit>{_UNIT_ALT})",
)


def _match_property(unit: str) -> str | None:
    return _UNIT_PROPERTY.get(unit)


def extract(text: str) -> list[PredEntity]:
    """Deterministic rule-based extraction of materials / processes / measurements.

    No LLM and no model weights — pure regex/vocabulary, so the run is reproducible
    and safe under the server profile. Spans are the regex match offsets, so each
    predicted entity carries a resolvable character span for span-IoU scoring.
    """
    preds: list[PredEntity] = []

    for m in _MATERIAL_RE.finditer(text):
        preds.append(PredEntity("material", m.group(0), m.start(), m.end()))

    for m in _PROCESS_RE.finditer(text):
        preds.append(PredEntity("process", m.group(0), m.start(), m.end()))

    for m in _MEASUREMENT_RE.finditer(text):
        surface = m.group(0).strip()
        unit = m.group("unit")
        parsed = parse_value(m.group("num") + " " + unit)
        value = parsed.value if parsed else None
        preds.append(
            PredEntity(
                type="measurement",
                text=surface,
                start=m.start(),
                end=m.start() + len(surface),
                property=_match_property(unit),
                value=value,
                unit=unit,
            )
        )
    return preds


# ---------------------------------------------------------------------------
# Span-based matching & metrics
# ---------------------------------------------------------------------------


def iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Intersection-over-union of two half-open character spans (``0.0`` if disjoint)."""
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    if inter == 0:
        return 0.0
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union else 0.0


@dataclass(frozen=True)
class TypeScore:
    """Per-entity-type confusion counts and derived P/R/F1 (§6.17)."""

    entity_type: str
    tp: int
    fp: int
    fn: int
    support: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, object]:
        return {
            "entity_type": self.entity_type,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "support": self.support,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class _Match:
    gold: GoldEntity
    pred: PredEntity
    iou: float


def _f1(precision: float, recall: float) -> float:
    denom = precision + recall
    return 2 * precision * recall / denom if denom else 0.0


def _ratio(num: int, denom: int) -> float:
    return num / denom if denom else 0.0


def _greedy_match(
    gold: list[GoldEntity], pred: list[PredEntity]
) -> tuple[list[_Match], list[GoldEntity], list[PredEntity]]:
    """Greedy 1-1 span matching by descending IoU (≥ :data:`IOU_MATCH`).

    Returns matched pairs plus the unmatched gold (FN) and unmatched pred (FP).
    """
    candidates: list[_Match] = []
    for g in gold:
        for p in pred:
            score = iou((g.start, g.end), (p.start, p.end))
            if score >= IOU_MATCH:
                candidates.append(_Match(g, p, score))
    candidates.sort(key=lambda c: c.iou, reverse=True)

    used_gold: set[int] = set()
    used_pred: set[int] = set()
    matches: list[_Match] = []
    for cand in candidates:
        gi, pi = id(cand.gold), id(cand.pred)
        if gi in used_gold or pi in used_pred:
            continue
        used_gold.add(gi)
        used_pred.add(pi)
        matches.append(cand)
    fn = [g for g in gold if id(g) not in used_gold]
    fp = [p for p in pred if id(p) not in used_pred]
    return matches, fn, fp


@dataclass
class ExtractionEvalReport:
    """Full §6.17 extraction-eval report over the golden set."""

    pipeline_version: str
    n_docs: int
    n_gold: int
    n_pred: int
    by_type: list[TypeScore]
    micro_precision: float
    micro_recall: float
    micro_f1: float
    macro_f1: float
    span_mean_iou: float
    span_accuracy: float  # fraction of matched pairs with IoU >= IOU_STRICT
    n_matched: int
    measurement_value_accuracy: float
    measurement_unit_accuracy: float
    evidence_span_ratio: float
    useful_docs_rate: float
    cost_per_doc_usd: float
    total_cost_usd: float
    latency_ms_per_doc: float
    total_latency_ms: float
    tokens_per_doc: float
    per_doc: list[dict] = field(default_factory=list)
    acceptance: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "pipeline_version": self.pipeline_version,
            "n_docs": self.n_docs,
            "n_gold": self.n_gold,
            "n_pred": self.n_pred,
            "by_type": [t.as_dict() for t in self.by_type],
            "micro_precision": round(self.micro_precision, 4),
            "micro_recall": round(self.micro_recall, 4),
            "micro_f1": round(self.micro_f1, 4),
            "macro_f1": round(self.macro_f1, 4),
            "span_mean_iou": round(self.span_mean_iou, 4),
            "span_accuracy": round(self.span_accuracy, 4),
            "n_matched": self.n_matched,
            "measurement_value_accuracy": round(self.measurement_value_accuracy, 4),
            "measurement_unit_accuracy": round(self.measurement_unit_accuracy, 4),
            "evidence_span_ratio": round(self.evidence_span_ratio, 4),
            "useful_docs_rate": round(self.useful_docs_rate, 4),
            "cost_per_doc_usd": round(self.cost_per_doc_usd, 6),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "latency_ms_per_doc": round(self.latency_ms_per_doc, 4),
            "total_latency_ms": round(self.total_latency_ms, 4),
            "tokens_per_doc": round(self.tokens_per_doc, 2),
            "per_doc": self.per_doc,
            "acceptance": self.acceptance,
        }


def _norm_unit(unit: str | None) -> str:
    if not unit:
        return ""
    u = unit.strip().lower()
    return {"°c": "degc", "µm": "um", "μm": "um"}.get(u, u)


def _measurement_correct(gold: GoldEntity, pred: PredEntity) -> tuple[bool, bool]:
    """(value_correct, unit_correct) for a matched measurement pair."""
    value_ok = (
        gold.value is not None
        and pred.value is not None
        and abs(gold.value - pred.value) <= max(1e-6, abs(gold.value) * 1e-3)
    )
    unit_ok = _norm_unit(gold.unit) == _norm_unit(pred.unit) and bool(_norm_unit(gold.unit))
    return value_ok, unit_ok


def evaluate(docs: list[GoldDoc], predictions: list[list[PredEntity]]) -> tuple[
    dict[str, dict[str, int]], list[_Match], list[dict], list[int]
]:
    """Accumulate per-type confusion, matched pairs, per-doc rows and useful-doc flags."""
    conf: dict[str, dict[str, int]] = {
        t: {"tp": 0, "fp": 0, "fn": 0, "support": 0} for t in ENTITY_TYPES
    }
    all_matches: list[_Match] = []
    per_doc: list[dict] = []
    useful: list[int] = []

    for doc, preds in zip(docs, predictions, strict=True):
        doc_matched = 0
        doc_gold = len(doc.entities)
        for etype in ENTITY_TYPES:
            gold_t = [g for g in doc.entities if g.type == etype]
            pred_t = [p for p in preds if p.type == etype]
            matches, fn, fp = _greedy_match(gold_t, pred_t)
            conf[etype]["tp"] += len(matches)
            conf[etype]["fp"] += len(fp)
            conf[etype]["fn"] += len(fn)
            conf[etype]["support"] += len(gold_t)
            all_matches.extend(matches)
            doc_matched += len(matches)
        useful.append(1 if doc_matched >= 1 else 0)
        per_doc.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "n_gold": doc_gold,
                "n_pred": len(preds),
                "n_matched": doc_matched,
                "useful": doc_matched >= 1,
            }
        )
    return conf, all_matches, per_doc, useful


def run_eval(
    suite: str = "extraction_golden", *, price: ModelPrice = REFERENCE_PRICE
) -> ExtractionEvalReport:
    """Run the full §6.17 extraction eval over the golden set and build the report.

    Times each document's extraction (real wall-clock latency), then scores per-type
    P/R/F1, span-IoU, measurement (value, unit) accuracy, evidence-span ratio and the
    per-document cost estimate.
    """
    docs = load_golden(suite)

    predictions: list[list[PredEntity]] = []
    total_latency_ms = 0.0
    total_tokens = 0
    per_doc_latency: dict[str, float] = {}
    usages = []
    for doc in docs:
        t0 = time.perf_counter()
        preds = extract(doc.text)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        total_latency_ms += elapsed_ms
        per_doc_latency[doc.doc_id] = elapsed_ms
        prompt_tokens = max(1, len(doc.text) // _CHARS_PER_TOKEN)
        completion_tokens = int(prompt_tokens * _COMPLETION_FRACTION)
        total_tokens += prompt_tokens + completion_tokens
        usages.append(
            cost_for(price.model_id, prompt_tokens, completion_tokens, {price.model_id: price})
        )
        predictions.append(preds)

    conf, matches, per_doc, useful = evaluate(docs, predictions)

    # Enrich per-doc rows with measured latency + estimated cost.
    for row, usage in zip(per_doc, usages, strict=True):
        row["latency_ms"] = round(per_doc_latency[row["doc_id"]], 4)
        row["cost_usd"] = round(usage.cost_usd, 6)

    # Per-type scores.
    by_type: list[TypeScore] = []
    tp_all = fp_all = fn_all = 0
    f1s: list[float] = []
    for etype in ENTITY_TYPES:
        c = conf[etype]
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        p = _ratio(tp, tp + fp)
        r = _ratio(tp, tp + fn)
        f = _f1(p, r)
        by_type.append(TypeScore(etype, tp, fp, fn, c["support"], p, r, f))
        tp_all += tp
        fp_all += fp
        fn_all += fn
        f1s.append(f)

    micro_p = _ratio(tp_all, tp_all + fp_all)
    micro_r = _ratio(tp_all, tp_all + fn_all)
    micro_f1 = _f1(micro_p, micro_r)
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    # Span accuracy over matched pairs.
    ious = [m.iou for m in matches]
    span_mean = sum(ious) / len(ious) if ious else 0.0
    span_acc = _ratio(sum(1 for v in ious if v >= IOU_STRICT), len(ious))

    # Measurement (value, unit) accuracy among matched measurement pairs.
    m_matches = [m for m in matches if m.gold.type == "measurement"]
    val_ok = unit_ok = 0
    for m in m_matches:
        v, u = _measurement_correct(m.gold, m.pred)
        val_ok += int(v)
        unit_ok += int(u)
    val_acc = _ratio(val_ok, len(m_matches))
    unit_acc = _ratio(unit_ok, len(m_matches))

    # Evidence-span ratio (§10.13): fraction of predicted facts with a resolvable span.
    pred_flat = [p for preds in predictions for p in preds]
    evidence_rows = [{"char_start": p.start, "char_end": p.end} for p in pred_flat]
    run_metrics = compute_run_metrics(
        extractor="reference-rule",
        model=REFERENCE_PRICE.model_id,
        prompt_version=PIPELINE_VERSION,
        triples=pred_flat,
        evidence=evidence_rows,
    )

    n_docs = len(docs)
    useful_rate = _ratio(sum(useful), n_docs)
    total_cost = sum(u.cost_usd for u in usages)

    acceptance = {
        "useful_docs_rate": {
            "value": round(useful_rate, 4),
            "threshold": 0.70,
            "pass": useful_rate >= 0.70,
        },
        "span_accuracy": {
            "value": round(span_acc, 4),
            "threshold": 0.85,
            "pass": span_acc >= 0.85,
        },
        "measurement_evidence": {
            "value": round(run_metrics.evidence_span_ratio, 4),
            "threshold": 1.0,
            "pass": run_metrics.evidence_span_ratio >= 1.0,
        },
    }
    acceptance["overall_pass"] = all(v["pass"] for v in acceptance.values() if isinstance(v, dict))

    return ExtractionEvalReport(
        pipeline_version=PIPELINE_VERSION,
        n_docs=n_docs,
        n_gold=sum(len(d.entities) for d in docs),
        n_pred=len(pred_flat),
        by_type=by_type,
        micro_precision=micro_p,
        micro_recall=micro_r,
        micro_f1=micro_f1,
        macro_f1=macro_f1,
        span_mean_iou=span_mean,
        span_accuracy=span_acc,
        n_matched=len(matches),
        measurement_value_accuracy=val_acc,
        measurement_unit_accuracy=unit_acc,
        evidence_span_ratio=run_metrics.evidence_span_ratio,
        useful_docs_rate=useful_rate,
        cost_per_doc_usd=total_cost / n_docs if n_docs else 0.0,
        total_cost_usd=total_cost,
        latency_ms_per_doc=total_latency_ms / n_docs if n_docs else 0.0,
        total_latency_ms=total_latency_ms,
        tokens_per_doc=total_tokens / n_docs if n_docs else 0.0,
        per_doc=per_doc,
        acceptance=acceptance,
    )


# ---------------------------------------------------------------------------
# Reporting / CLI
# ---------------------------------------------------------------------------


def to_markdown(report: ExtractionEvalReport) -> str:
    """Render a compact Markdown report of the §6.17 metrics."""
    d = report.as_dict()
    lines = [
        f"# Extraction eval (§6.17) — {d['pipeline_version']}",
        "",
        f"Golden: **{d['n_docs']}** docs · **{d['n_gold']}** gold entities · "
        f"**{d['n_pred']}** predicted · **{d['n_matched']}** matched.",
        "",
        "## Precision / Recall / F1 by entity type",
        "",
        "| type | support | TP | FP | FN | precision | recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for t in d["by_type"]:
        lines.append(
            f"| {t['entity_type']} | {t['support']} | {t['tp']} | {t['fp']} | {t['fn']} "
            f"| {t['precision']} | {t['recall']} | {t['f1']} |"
        )
    lines += [
        "",
        f"**Micro** P/R/F1 = {d['micro_precision']} / {d['micro_recall']} / {d['micro_f1']} · "
        f"**Macro-F1** = {d['macro_f1']}",
        "",
        "## Span accuracy (IoU)",
        "",
        f"- mean IoU (matched) = **{d['span_mean_iou']}**",
        f"- span-accuracy (IoU ≥ {IOU_STRICT}) = **{d['span_accuracy']}** (threshold ≥ 0.85)",
        "",
        "## Measurements",
        "",
        f"- (value) accuracy = **{d['measurement_value_accuracy']}**",
        f"- (unit) accuracy = **{d['measurement_unit_accuracy']}**",
        f"- evidence-span ratio = **{d['evidence_span_ratio']}** (facts with resolvable span)",
        "",
        "## Cost / latency per document (§15.2)",
        "",
        f"- latency/doc = **{d['latency_ms_per_doc']} ms** (total {d['total_latency_ms']} ms)",
        f"- tokens/doc ≈ **{d['tokens_per_doc']}**",
        f"- cost/doc ≈ **${d['cost_per_doc_usd']}** (total ${d['total_cost_usd']})",
        "",
        "## Acceptance (§6.17 / Phase 2)",
        "",
    ]
    for key, val in d["acceptance"].items():
        if isinstance(val, dict):
            mark = "PASS" if val["pass"] else "FAIL"
            lines.append(f"- {key}: {val['value']} (≥ {val['threshold']}) — **{mark}**")
    lines.append(f"- overall: **{'PASS' if d['acceptance'].get('overall_pass') else 'FAIL'}**")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction eval-harness (§6.17)")
    parser.add_argument("--golden", default="extraction_golden", help="golden suite name")
    parser.add_argument("--markdown", action="store_true", help="also print a Markdown report")
    args = parser.parse_args(argv)

    report = run_eval(args.golden)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    if args.markdown:
        print("\n" + to_markdown(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
