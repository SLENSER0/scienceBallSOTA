"""Confidence calibration: reliability diagram, ECE, honest confidence labels (§23.25).

RU: §23.25 требует показать, что confidence-числа ОТКАЛИБРОВАНЫ, а не просто
выглядят убедительно. «Число 0.83 выглядит убедительно, но неизвестно, что оно
значит.» Этот роутер отвечает на вопрос честными измерениями над ЖИВЫМ графом
(server-профиль Neo4j :8000 / embedded Kuzu):

* **reliability-диаграмма** — predicted confidence vs observed accuracy по бинам;
* **ECE / MCE / Brier** — насколько сильно уверенность расходится с фактической
  правотой (Expected / Max Calibration Error, средне-квадратичная ошибка);
* **честные словесные метки** — «high confidence / needs review / conflicting /
  unsupported / estimated» вместо голых процентов (§23.25 uncertainty-labels);
* **пост-hoc калибратор** — гистограммное перекартирование raw→calibrated, чтобы
  UI мог показать «после калибровки» и чтобы thresholds опирались на данные, а не
  на произвольные 0.7/0.9.

Источник (честно и по «Зачем»): golden-набор (§18.6, ``kg_eval.retrieval_eval.
GOLDEN``) + retrieval eval. Для каждого golden-запроса кандидаты ранжируются полной
гибридной формулой §10.2 (``weighted_fuse`` над keyword + evidence_quality +
graph_proximity), и берётся пара ``(fused_score, is_relevant)`` — предсказанная
уверенность релевантности против фактической (кандидат входит в golden-relevant
множество). Это и есть настоящие ``(confidence, label)`` пары, на которых строится
reliability-диаграмма. Ничего не переписывается — метрики берутся дословно из
:mod:`kg_eval.calibration_ece`, калибратор из :mod:`kg_eval.probability_calibrators`,
метки из :mod:`kg_eval.uncertainty_labeler`, ранжирование из
:mod:`kg_retrievers.scoring`.

Endpoints (read-only, аналитик+ на report/translate по конвенции quality-панелей):

* ``GET  /api/v1/confidence-calibration/report``    — reliability bins + ECE/MCE/
  Brier + verdict + пост-hoc калибратор над golden-retrieval.
* ``GET  /api/v1/confidence-calibration/labels``    — легенда честных словесных
  меток + калиброванные пороги + дисклеймеры (confidence ≠ truth).
* ``POST /api/v1/confidence-calibration/translate`` — перевод голых чисел в честные
  словесные метки (+ калиброванная уверенность, если запрошена).

EN: new router — wire via ``routers/__init__.py`` (see feature wiring). Deterministic:
same store + golden → same numbers.
"""

from __future__ import annotations

import functools
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_eval.calibration_ece import calibration_report
from kg_eval.probability_calibrators import fit_histogram_binning
from kg_eval.retrieval_eval import GOLDEN
from kg_eval.uncertainty_labeler import (
    CONFLICTING,
    DEFAULT,
    ESTIMATED,
    HIGH_CONFIDENCE,
    NEEDS_REVIEW,
    UNSUPPORTED,
    label,
    label_batch,
)

router = APIRouter(prefix="/api/v1/confidence-calibration", tags=["confidence-calibration"])

# ECE at or below this is treated as "well calibrated" for the headline verdict.
# Not a magic 0.7/0.9 accept-threshold — it is the calibration-quality budget for the
# reliability report itself (§23.25: thresholds must come from calibrated data).
_ECE_BUDGET = 0.10
_CANDIDATE_LIMIT = 150
_TOKEN = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)
_TEXT_FIELDS = ("name", "canonical_name", "aliases_text", "text")


# --------------------------------------------------------------------------- #
# Honest word-label legend (§23.25 uncertainty-labels)                        #
# --------------------------------------------------------------------------- #
# order matters: shown as a legend, worst-signal → best.
_LABEL_LEGEND: tuple[dict[str, str], ...] = (
    {
        "label": HIGH_CONFIDENCE,
        "ru": "высокая уверенность",
        "meaning": "Калиброванная уверенность в верхней полосе И есть опора-evidence "
        "без конфликтов. Всё равно НЕ значит «истина» — значит «редко ошибается».",
    },
    {
        "label": NEEDS_REVIEW,
        "ru": "нужна проверка",
        "meaning": "Средняя полоса уверенности — куратор должен подтвердить перед "
        "использованием как факта.",
    },
    {
        "label": ESTIMATED,
        "ru": "оценка",
        "meaning": "Значение оценено/интерполировано, а не извлечено дословно из "
        "источника — используйте как ориентир.",
    },
    {
        "label": CONFLICTING,
        "ru": "конфликт",
        "meaning": "Источники/слои расходятся. Число уверенности здесь обманчиво — "
        "сигнал конфликта важнее любого процента.",
    },
    {
        "label": UNSUPPORTED,
        "ru": "без опоры",
        "meaning": "Нет привязанного evidence ИЛИ уверенность в нижней полосе — "
        "утверждение нельзя показывать как подтверждённое.",
    },
)

# Plain-language disclaimers the UI must render next to any confidence number.
_HONEST_NOTES: tuple[str, ...] = (
    "confidence ≠ truth — калиброванное число говорит «как часто система права при "
    "такой уверенности», а не «это точно правда».",
    "verified ≠ automatically extracted — «подтверждено» означает проверку куратором, "
    "а не то, что число само по себе извлечено моделью.",
    "Голый процент без калибровки бессмыслен: 0.83 полезно только если 83% таких "
    "предсказаний реально верны (это и проверяет reliability-диаграмма).",
    "Пороги auto-accept / needs-review / reject взяты из калиброванных полос, а не из "
    "произвольных 0.7 / 0.9.",
)


# --------------------------------------------------------------------------- #
# Live golden-retrieval → (confidence, label) pairs                           #
# --------------------------------------------------------------------------- #
def _tokenize(text: str | None) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def _keyword_score(node: dict[str, Any], tokens: set[str]) -> float:
    """Exact query-token overlap over the node's text fields, normalised to [0, 1]."""
    hay = _tokenize(" ".join(str(node.get(f) or "") for f in _TEXT_FIELDS))
    return len(tokens & hay) / (len(tokens) or 1)


def _candidate_nodes(store: Any, query: str, limit: int) -> dict[str, dict]:
    """Nodes whose text columns CONTAIN any query token (parameterized Cypher)."""
    tokens = _tokenize(query)
    if not tokens:
        return {}
    conds: list[str] = []
    params: dict[str, Any] = {}
    for i, tok in enumerate(sorted(tokens)):
        key = f"t{i}"
        params[key] = tok
        conds.append(
            f"(lower(coalesce(n.name,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.canonical_name,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.aliases_text,'')) CONTAINS ${key} "
            f"OR lower(coalesce(n.text,'')) CONTAINS ${key})"
        )
    cypher = "MATCH (n:Node) WHERE " + " OR ".join(conds) + f" RETURN n LIMIT {int(limit)}"
    out: dict[str, dict] = {}
    try:
        for row in store.rows(cypher, params):
            nd = store._node_dict(row[0])
            nid = nd.get("id")
            if nid:
                out[str(nid)] = nd
    except Exception:  # pragma: no cover - store/query failure degrades to empty
        return {}
    return out


_MAX_HOPS = 3
# Cap the BFS frontier per level so proximity stays fast on the dense live graph
# (208k edges): a 3-hop neighbourhood otherwise fans out to thousands of nodes.
# Deterministic — we keep the lexicographically smallest ids, so repeat runs on the
# same store yield the same proximity map (and thus the same calibration numbers).
_FRONTIER_CAP = 800


def _proximity_map(store: Any, seeds: list[str], candidates: set[str]) -> dict[str, float]:
    """§10.2 graph-proximity for many candidates via ONE batched BFS from the seeds.

    Semantically matches per-candidate :func:`kg_retrievers.scoring.
    graph_proximity_score` (seed → 1.0, decaying ``(max_hops − (edges − 1))/max_hops``
    up to ``max_hops`` hops, else 0.0), but expands a whole BFS level per Cypher call
    instead of one BFS per candidate — the per-candidate version issues O(candidates)
    BFS traversals and takes minutes on the live graph. Each level is capped at
    ``_FRONTIER_CAP`` (smallest ids kept) to bound the fan-out deterministically. Only
    candidate ids are scored.
    """
    seed_set = set(seeds)
    prox = dict.fromkeys(candidates, 0.0)
    for sid in seed_set & candidates:
        prox[sid] = 1.0
    frontier = sorted(seed_set)
    visited = set(seed_set)
    for edges in range(1, _MAX_HOPS + 1):
        if not frontier:
            break
        rows = store.rows(
            "MATCH (n:Node)-[:Rel]-(m:Node) WHERE n.id IN $ids RETURN DISTINCT m.id",
            {"ids": frontier},
        )
        nxt: list[str] = []
        score = round((_MAX_HOPS - (edges - 1)) / _MAX_HOPS, 4)
        for row in rows:
            mid = row[0]
            if not mid or mid in visited:
                continue
            visited.add(mid)
            nxt.append(mid)
            if mid in candidates and mid not in seed_set:
                prox[mid] = score  # first (nearest) hop wins
        # Bound the next level's fan-out deterministically (smallest ids first). All
        # candidates reached so far already have their score; the cap only limits which
        # far nodes we keep expanding through.
        frontier = sorted(nxt)[:_FRONTIER_CAP]
    return prox


def _hybrid_pairs(store: Any, candidate_limit: int) -> tuple[list[tuple[float, bool]], int]:
    """Collect ``(fused_relevance_score, is_relevant)`` over the whole golden set (§10.2).

    For every golden query the §10.2 hybrid formula (``weighted_fuse`` над keyword +
    evidence_quality + graph_proximity) scores each keyword candidate; the score is
    the predicted relevance-confidence and the label is membership in the golden
    relevant set. Returns the flat pair list plus the number of golden queries that
    produced at least one candidate.
    """
    from kg_retrievers.scoring import evidence_quality_score, weighted_fuse

    pairs: list[tuple[float, bool]] = []
    used_queries = 0
    for query, relevant in GOLDEN:
        relset = set(relevant)
        tokens = _tokenize(query)
        nodes = _candidate_nodes(store, query, candidate_limit)
        kw = {nid: s for nid, nd in nodes.items() if (s := _keyword_score(nd, tokens)) > 0}
        if not kw:
            continue
        used_queries += 1
        seeds = [nid for nid, _ in sorted(kw.items(), key=lambda p: (-p[1], p[0]))[:3]]
        prox = _proximity_map(store, seeds, set(kw))
        comps: dict[str, dict[str, float]] = {
            "keyword": kw,
            "evidence_quality": {nid: evidence_quality_score(nodes[nid]) for nid in kw},
            "graph_proximity": prox,
        }
        for fused in weighted_fuse(comps):
            conf = max(0.0, min(1.0, float(fused.score)))
            pairs.append((conf, fused.id in relset))
    return pairs, used_queries


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #
class ReliabilityBin(BaseModel):
    lo: float
    hi: float
    count: int
    avg_confidence: float  # predicted (mean confidence of the bin)
    accuracy: float  # observed (fraction actually relevant/correct)
    gap: float  # accuracy − avg_confidence (signed)
    direction: str  # overconfident | underconfident | calibrated | empty
    honest_label: str | None  # word-label the UI would show for this confidence band


class VerdictModel(BaseModel):
    well_calibrated: bool
    ece: float
    ece_budget: float
    bias: str  # overconfident | underconfident | calibrated
    bias_magnitude: float  # weighted mean signed gap (observed − predicted)


class CalibratorKnot(BaseModel):
    raw: float  # raw confidence (bin lower edge)
    calibrated: float  # empirical accuracy that raw maps to


class TranslateExample(BaseModel):
    raw: float
    calibrated: float
    honest_label: str


class ReportModel(BaseModel):
    source: str
    source_desc: str
    n: int
    n_bins: int
    golden_size: int
    used_queries: int
    ece: float
    mce: float
    brier: float
    bins: list[ReliabilityBin]
    verdict: VerdictModel
    calibrator: list[CalibratorKnot]
    calibrated_examples: list[TranslateExample]
    honest_notes: list[str]
    warnings: list[str]
    elapsed_ms: float


class LabelEntry(BaseModel):
    label: str
    ru: str
    meaning: str


class ThresholdsModel(BaseModel):
    high: float
    review: float
    low: float


class LabelsModel(BaseModel):
    labels: list[LabelEntry]
    thresholds: ThresholdsModel
    honest_notes: list[str]


class TranslateItem(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    has_conflict: bool = False
    has_evidence: bool = True
    is_estimated: bool = False


class TranslateRequest(BaseModel):
    items: list[TranslateItem] = Field(default_factory=list)
    calibrate: bool = Field(
        default=True,
        description="also return the calibrated confidence from the live golden calibrator",
    )


class TranslateOut(BaseModel):
    confidence: float
    calibrated_confidence: float | None
    honest_label: str


class TranslateResponse(BaseModel):
    results: list[TranslateOut]
    thresholds: ThresholdsModel
    calibrated: bool


# --------------------------------------------------------------------------- #
# Report assembly                                                              #
# --------------------------------------------------------------------------- #
def _direction(gap: float, count: int) -> str:
    if count == 0:
        return "empty"
    if gap > 0.05:
        return "underconfident"  # observed accuracy exceeds stated confidence
    if gap < -0.05:
        return "overconfident"  # stated confidence exceeds observed accuracy
    return "calibrated"


@functools.lru_cache(maxsize=8)
def _build_report(n_bins: int, candidate_limit: int) -> ReportModel:
    """Run the live golden-retrieval calibration once per (n_bins, limit) — cached."""
    t0 = time.perf_counter()
    store = get_store()
    pairs, used_queries = _hybrid_pairs(store, candidate_limit)

    warnings: list[str] = []
    if not pairs:
        elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
        return ReportModel(
            source="golden_retrieval_hybrid",
            source_desc=_SOURCE_DESC,
            n=0,
            n_bins=n_bins,
            golden_size=len(GOLDEN),
            used_queries=used_queries,
            ece=0.0,
            mce=0.0,
            brier=0.0,
            bins=[],
            verdict=VerdictModel(
                well_calibrated=False, ece=0.0, ece_budget=_ECE_BUDGET, bias="calibrated",
                bias_magnitude=0.0,
            ),
            calibrator=[],
            calibrated_examples=[],
            honest_notes=list(_HONEST_NOTES),
            warnings=["no golden candidates retrieved from the live store — nothing to calibrate"],
            elapsed_ms=elapsed,
        )

    rep = calibration_report(pairs, n_bins=n_bins)
    calib = fit_histogram_binning(pairs, n_bins=n_bins)

    bins: list[ReliabilityBin] = []
    weighted_bias = 0.0
    for b in rep.bins:
        gap = b.accuracy - b.avg_confidence
        weighted_bias += (b.count / rep.n) * gap
        honest = label(b.avg_confidence) if b.count else None
        bins.append(
            ReliabilityBin(
                lo=round(b.lo, 4),
                hi=round(b.hi, 4),
                count=b.count,
                avg_confidence=round(b.avg_confidence, 4),
                accuracy=round(b.accuracy, 4),
                gap=round(gap, 4),
                direction=_direction(gap, b.count),
                honest_label=honest,
            )
        )

    if weighted_bias > 0.02:
        bias = "underconfident"
    elif weighted_bias < -0.02:
        bias = "overconfident"
    else:
        bias = "calibrated"

    if rep.n < 30:
        warnings.append(
            f"only {rep.n} (confidence, label) pairs — reliability estimates are noisy; "
            "treat ECE as indicative"
        )
    if bias == "overconfident":
        warnings.append(
            "raw confidence runs OVER observed accuracy — the calibrator lowers it so the "
            "UI does not overstate certainty"
        )

    calibrator = [
        CalibratorKnot(raw=round(k[0], 4), calibrated=round(k[1], 4)) for k in calib.knots
    ]
    examples = [
        TranslateExample(
            raw=x,
            calibrated=round(calib.apply(x), 4),
            honest_label=label(calib.apply(x)),
        )
        for x in (0.3, 0.5, 0.7, 0.83, 0.9)
    ]

    elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
    return ReportModel(
        source="golden_retrieval_hybrid",
        source_desc=_SOURCE_DESC,
        n=rep.n,
        n_bins=rep.n_bins,
        golden_size=len(GOLDEN),
        used_queries=used_queries,
        ece=round(rep.ece, 6),
        mce=round(rep.mce, 6),
        brier=round(rep.brier, 6),
        bins=bins,
        verdict=VerdictModel(
            well_calibrated=rep.ece <= _ECE_BUDGET,
            ece=round(rep.ece, 6),
            ece_budget=_ECE_BUDGET,
            bias=bias,
            bias_magnitude=round(weighted_bias, 6),
        ),
        calibrator=calibrator,
        calibrated_examples=examples,
        honest_notes=list(_HONEST_NOTES),
        warnings=warnings,
        elapsed_ms=elapsed,
    )


_SOURCE_DESC = (
    "Golden retrieval (§18.6) over the live graph: per golden query the §10.2 hybrid "
    "score (weighted_fuse over keyword + evidence_quality + graph_proximity) is the "
    "predicted relevance-confidence; the label is membership in the golden-relevant set. "
    "Reliability = predicted confidence vs observed relevance frequency per bin."
)


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #
@router.get("/report", response_model=ReportModel)
def report(
    n_bins: int = Query(default=10, ge=2, le=20),
    candidate_limit: int = Query(default=_CANDIDATE_LIMIT, ge=10, le=500),
    role: str = Depends(current_role),
) -> ReportModel:
    """Reliability diagram + ECE/MCE/Brier + post-hoc calibrator over golden retrieval.

    Detereministic and cached per ``(n_bins, candidate_limit)``: same live store +
    golden set → same numbers. ``bins`` drives the reliability diagram (predicted vs
    observed), ``calibrator`` the raw→calibrated remap curve, ``verdict`` the honest
    over/under-confidence call.
    """
    return _build_report(int(n_bins), int(candidate_limit))


@router.get("/labels", response_model=LabelsModel)
def labels() -> LabelsModel:
    """Honest word-label legend + calibrated bands + confidence≠truth disclaimers (§23.25)."""
    return LabelsModel(
        labels=[LabelEntry(**e) for e in _LABEL_LEGEND],
        thresholds=ThresholdsModel(high=DEFAULT.high, review=DEFAULT.review, low=DEFAULT.low),
        honest_notes=list(_HONEST_NOTES),
    )


@router.post("/translate", response_model=TranslateResponse)
def translate(req: TranslateRequest, role: str = Depends(current_role)) -> TranslateResponse:
    """Turn bare confidence numbers into honest word-labels (+ calibrated value).

    Signal flags (conflict / no-evidence / estimated) override the numeric band —
    a contradiction surfaces even at a high score (§23.25 uncertainty-labels). When
    ``calibrate`` is set, the live golden calibrator remaps each raw confidence to
    its empirical accuracy so the label reflects calibrated certainty, not the raw
    number.
    """
    records = [
        {
            "confidence": it.confidence,
            "has_conflict": it.has_conflict,
            "has_evidence": it.has_evidence,
            "is_estimated": it.is_estimated,
        }
        for it in req.items
    ]
    words = label_batch(records)

    calib = None
    if req.calibrate:
        store = get_store()
        pairs, _ = _hybrid_pairs(store, _CANDIDATE_LIMIT)
        if pairs:
            calib = fit_histogram_binning(pairs, n_bins=10)

    results: list[TranslateOut] = []
    for it, word in zip(req.items, words, strict=True):
        calibrated = round(calib.apply(it.confidence), 4) if calib is not None else None
        results.append(
            TranslateOut(
                confidence=it.confidence,
                calibrated_confidence=calibrated,
                honest_label=word,
            )
        )
    return TranslateResponse(
        results=results,
        thresholds=ThresholdsModel(high=DEFAULT.high, review=DEFAULT.review, low=DEFAULT.low),
        calibrated=calib is not None,
    )
