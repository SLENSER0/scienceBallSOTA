"""§18.9 RAGAS + DeepEval RAG-checks: faithfulness / hallucination / citation-groundedness.

Отраслевые RAG-метрики (RAGAS + DeepEval) поверх evidence-first ответа агента —
измеримое доказательство «нет галлюцинаций». Оба фреймворка штатно требуют
**закрытого LLM-судью**; в OSS-профиле (§23.33) он заменён детерминированной
open-weight-free эвристикой, переиспользующей уже готовые чекеры пакета:

* :func:`kg_eval.faithjudge_lite.split_claims` / ``salient_tokens`` — разбиение
  ответа на claims и извлечение чисел + содержательных слов
  (FaithJudge/HHEM-стиль, arXiv:2505.04847);
* :func:`kg_eval.claim_support.label_claims` — «claim подтверждён только с
  резолвимой цитатой и совпадением чисел» (§18.10);
* :func:`kg_eval.citation_check.check_citations` — фантомные цитаты = hard fail.

Ничего нового про «верность» не изобретается: модуль лишь *маппит* вход в
RAGAS-формат (``question``/``answer``/``contexts``/``ground_truth``) и в
DeepEval ``LLMTestCase`` и агрегирует пять RAGAS-метрик + четыре DeepEval-метрики
+ кастомную GEval-метрику «citation groundedness» под evidence-first модель.
Судья зафиксирован (:data:`JUDGE_MODEL`) — записывается в MLflow-теги роутером
для воспроизводимости. Чистый python, детерминизм: тот же вход → тот же выход.

Industry RAG metrics (RAGAS + DeepEval) over the agent's evidence-first answer.
Both frameworks normally need a closed LLM judge; here it is swapped for a
deterministic, open-weight-free judge (§23.33) that reuses this package's
shipped checkers. The module maps the input into the RAGAS format
(``question``/``answer``/``contexts``/``ground_truth``) and a DeepEval
``LLMTestCase`` and aggregates the five RAGAS metrics, four DeepEval metrics and
a custom GEval «citation groundedness» metric. The judge is fixed
(:data:`JUDGE_MODEL`) so the router can pin it in MLflow tags.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from kg_eval.citation_check import check_citations
from kg_eval.claim_support import label_claims
from kg_eval.faithjudge_lite import salient_tokens, split_claims

__all__ = [
    "DEEPEVAL_METRICS",
    "DEFAULT_THRESHOLDS",
    "HIGHER_IS_WORSE",
    "JUDGE_MODEL",
    "RAGAS_METRICS",
    "AggregateReport",
    "RagCheckReport",
    "RagSample",
    "evaluate_batch",
    "evaluate_sample",
    "to_deepeval_testcase",
    "to_ragas_format",
]

#: Fixed judge identity, pinned in MLflow tags for reproducibility (§18.9/§23.33).
#: No closed o3-mini judge (as in upstream FaithJudge/RAGAS) — an open, weight-free
#: deterministic heuristic instead.
JUDGE_MODEL: str = "deterministic-open-judge/faithjudge-lite@v1"

#: RAGAS metric surface logged to the ``answer`` MLflow experiment (§18.9).
RAGAS_METRICS: tuple[str, ...] = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
)

#: DeepEval metric surface (``FaithfulnessMetric`` / ``AnswerRelevancyMetric`` /
#: ``ContextualPrecisionMetric`` / ``HallucinationMetric`` + custom GEval).
DEEPEVAL_METRICS: tuple[str, ...] = (
    "faithfulness",
    "answer_relevancy",
    "contextual_precision",
    "hallucination",
    "citation_groundedness",
)

#: Acceptance thresholds — the DeepEval ``assert_test`` gate (§18.9). All metrics
#: are higher-is-better except those in :data:`HIGHER_IS_WORSE`.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.90,
    "answer_relevancy": 0.30,
    "context_precision": 0.50,
    "context_recall": 0.60,
    "answer_correctness": 0.35,
    "citation_groundedness": 0.90,
    "hallucination": 0.10,
}

# Инлайновый маркер цитаты вида ``[e1]`` / ``[1]`` — вырезается перед разбором,
# чтобы id-токены не попадали в «содержательные» токены claim (§18.10).
_CITE_RE = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")

#: Metrics where a *lower* value is better (gate uses ``value <= threshold``).
HIGHER_IS_WORSE: frozenset[str] = frozenset({"hallucination"})


def _strip_markers(text: str) -> str:
    """Убрать инлайновые маркеры цитат ``[e1]`` перед токенизацией (§18.10)."""
    return _CITE_RE.sub(" ", text)


# Длина префикса для лёгкого стемминга RU-словоформ (осмоса/осмос → осмос).
# A light prefix stem collapses Russian inflections for the *lexical* proxies
# (relevancy / correctness / context precision); numeric faithfulness stays exact.
_STEM_LEN = 5


def _stem(word: str) -> str:
    """Prefix stem — первые ``_STEM_LEN`` символов (склонения → общий корень)."""
    return word[:_STEM_LEN]


def _content_tokens(text: str) -> frozenset[str]:
    """Значимые токены: стеммированные слова + числа как строки (RU/EN).

    Reuses :func:`kg_eval.faithjudge_lite.salient_tokens` (stopword-filtered
    content words + parsed numbers) and flattens to a comparable string set.
    Citation markers are stripped first so ``[e1]`` ids never leak in; content
    words are prefix-stemmed so declension noise does not deflate overlap.
    """
    numbers, words = salient_tokens(_strip_markers(text))
    return frozenset(_fmt_num(n) for n in numbers) | frozenset(_stem(w) for w in words)


def _fmt_num(value: float) -> str:
    """Stable string form of a number (``42.0`` → ``"42"``) for token matching."""
    return str(int(value)) if float(value).is_integer() else repr(value)


def _dice(a: frozenset[str], b: frozenset[str]) -> float:
    """Sørensen–Dice overlap of two token sets (F1-стиль, симметрично).

    ``1.0`` when both empty, ``0.0`` when exactly one is empty.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """Asymmetric coverage ``|a ∩ b| / |a|`` — доля токенов ``a`` покрытых ``b``.

    ``1.0`` when ``a`` is empty (nothing to cover).
    """
    return 1.0 if not a else len(a & b) / len(a)


def _corpus_tokens(texts: Sequence[str]) -> tuple[frozenset[str], frozenset[str]]:
    """Union of ``(numbers, words)`` across ``texts`` (после снятия маркеров)."""
    nums: set[str] = set()
    words: set[str] = set()
    for text in texts:
        n, w = salient_tokens(_strip_markers(text))
        nums.update(_fmt_num(x) for x in n)
        words.update(w)
    return frozenset(nums), frozenset(words)


def _claim_faithful(
    claim: str, ctx_numbers: frozenset[str], ctx_words: frozenset[str]
) -> bool:
    """Claim верен контекстам, если его ЧИСЛА присутствуют, а темы пересекаются.

    Numbers are the falsifiable facts in a mining KG (§8): a claim is faithful
    only when **every** number it states appears in the context corpus. A
    number-free claim is faithful when it shares at least one content word with
    the corpus (topical grounding); an empty claim is vacuously faithful.
    """
    numbers, words = salient_tokens(_strip_markers(claim))
    num_strs = frozenset(_fmt_num(n) for n in numbers)
    if num_strs:
        return num_strs <= ctx_numbers and bool(not words or words & ctx_words)
    return bool(words & ctx_words) if words else True


def _faithfulness(text: str, contexts: Sequence[str]) -> float:
    """Доля claims в ``text``, верных корпусу ``contexts`` (RAGAS faithfulness)."""
    ctx_numbers, ctx_words = _corpus_tokens(contexts)
    claims = split_claims(_strip_markers(text))
    if not claims:
        return 1.0
    supported = sum(1 for c in claims if _claim_faithful(c, ctx_numbers, ctx_words))
    return supported / len(claims)


def _context_precision(contexts: Sequence[str], reference: str) -> float:
    """Доля контекстов, релевантных reference (RAGAS ``context_precision``-прокси).

    A context counts as relevant when it shares at least one content token with
    the reference (ground truth). ``1.0`` when there are no contexts.
    """
    if not contexts:
        return 1.0
    ref = _content_tokens(reference)
    if not ref:
        return 1.0
    relevant = sum(1 for c in contexts if _content_tokens(c) & ref)
    return relevant / len(contexts)


@dataclass(frozen=True)
class RagSample:
    """One evaluation sample in RAGAS shape + evidence-first citation fields.

    * ``question`` / ``answer`` / ``contexts`` / ``ground_truth`` — RAGAS quadruple.
    * ``cited_ids`` — evidence ids the answer cites (для phantom-проверки).
    * ``evidence`` — ``{marker_or_id: source_text}`` для citation-groundedness.
    * ``known_ids`` — вселенная существующих evidence-id в графе (§7.4).
    """

    question: str
    answer: str
    contexts: tuple[str, ...] = ()
    ground_truth: str = ""
    cited_ids: tuple[str, ...] = ()
    evidence: Mapping[str, str] = field(default_factory=dict)
    known_ids: tuple[str, ...] = ()


def to_ragas_format(sample: RagSample) -> dict[str, object]:
    """Map a :class:`RagSample` to the RAGAS row shape (§18.9 ``ragas_runner``)."""
    return {
        "question": sample.question,
        "answer": sample.answer,
        "contexts": list(sample.contexts),
        "ground_truth": sample.ground_truth,
    }


def to_deepeval_testcase(sample: RagSample) -> dict[str, object]:
    """Map a :class:`RagSample` to a DeepEval ``LLMTestCase`` dict (§18.9)."""
    return {
        "input": sample.question,
        "actual_output": sample.answer,
        "expected_output": sample.ground_truth,
        "retrieval_context": list(sample.contexts),
        "context": list(sample.contexts),
    }


@dataclass(frozen=True)
class RagCheckReport:
    """Frozen per-sample RAGAS+DeepEval report with the gate verdict (§18.9)."""

    question: str
    ragas: dict[str, float]
    deepeval: dict[str, float]
    citation_groundedness: float
    hallucination: float
    phantom_citations: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    thresholds: dict[str, float]
    failures: tuple[str, ...]
    passed: bool

    def as_dict(self) -> dict[str, object]:
        """JSON-ready view with rounded metrics (RU: словарь)."""
        return {
            "question": self.question,
            "ragas": {k: round(v, 6) for k, v in self.ragas.items()},
            "deepeval": {k: round(v, 6) for k, v in self.deepeval.items()},
            "citation_groundedness": round(self.citation_groundedness, 6),
            "hallucination": round(self.hallucination, 6),
            "phantom_citations": list(self.phantom_citations),
            "unsupported_claims": list(self.unsupported_claims),
            "thresholds": dict(self.thresholds),
            "failures": list(self.failures),
            "passed": self.passed,
        }


def _gate(values: Mapping[str, float], thresholds: Mapping[str, float]) -> tuple[str, ...]:
    """Return the names of metrics that fail their threshold (DeepEval gate)."""
    failures: list[str] = []
    for name, thr in thresholds.items():
        if name not in values:
            continue
        value = values[name]
        ok = value <= thr if name in HIGHER_IS_WORSE else value >= thr
        if not ok:
            failures.append(name)
    return tuple(failures)


def evaluate_sample(
    sample: RagSample,
    *,
    thresholds: Mapping[str, float] | None = None,
) -> RagCheckReport:
    """Compute all RAGAS + DeepEval metrics for one sample and gate them (§18.9).

    RAGAS: ``faithfulness`` (claim-coverage of contexts), ``answer_relevancy``
    (question↔answer token alignment), ``context_precision`` (relevant contexts
    vs ground truth), ``context_recall`` (ground-truth claims covered by
    contexts), ``answer_correctness`` (answer↔ground-truth token F1). DeepEval
    mirrors these plus ``hallucination`` (``1 − faithfulness``) and the custom
    GEval ``citation_groundedness`` (share of claims with a resolvable citation
    whose numbers are supported; **any phantom citation ⇒ 0.0**, evidence-first
    hard fail). ``passed`` is the DeepEval ``assert_test`` gate over the
    thresholds.
    """
    thr = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    contexts = list(sample.contexts)
    gt = sample.ground_truth

    faithfulness = _faithfulness(sample.answer, contexts)
    hallucination = 1.0 - faithfulness

    q_tok = _content_tokens(sample.question)
    a_tok = _content_tokens(sample.answer)
    answer_relevancy = _overlap(q_tok, a_tok)

    reference = gt or sample.answer
    context_precision = _context_precision(contexts, reference)
    context_recall = _faithfulness(gt, contexts) if gt else faithfulness
    answer_correctness = _dice(a_tok, _content_tokens(gt)) if gt else answer_relevancy

    # Custom GEval «citation groundedness» под evidence-first модель (§18.10).
    support = label_claims(sample.answer, dict(sample.evidence))
    citation = check_citations(sample.cited_ids, sample.known_ids)
    groundedness = 1.0 - support.unsupported_claim_rate
    if citation.phantom:  # фантомная цитата = жёсткий провал.
        groundedness = 0.0
    unsupported_claims = tuple(c.text for c in support.claims if not c.supported)

    ragas = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
        "answer_correctness": answer_correctness,
    }
    deepeval = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "contextual_precision": context_precision,
        "hallucination": hallucination,
        "citation_groundedness": groundedness,
    }

    # Gate over the union surface (RAGAS + DeepEval names, both directions).
    gate_values = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
        "answer_correctness": answer_correctness,
        "citation_groundedness": groundedness,
        "hallucination": hallucination,
    }
    failures = _gate(gate_values, thr)

    return RagCheckReport(
        question=sample.question,
        ragas=ragas,
        deepeval=deepeval,
        citation_groundedness=groundedness,
        hallucination=hallucination,
        phantom_citations=citation.phantom,
        unsupported_claims=unsupported_claims,
        thresholds=thr,
        failures=failures,
        passed=not failures,
    )


@dataclass(frozen=True)
class AggregateReport:
    """Macro-averaged RAGAS+DeepEval report over a batch (§18.9 ``--suite ragas``)."""

    n: int
    ragas: dict[str, float]
    deepeval: dict[str, float]
    n_passed: int
    n_phantom: int
    judge_model: str
    thresholds: dict[str, float]
    failures: tuple[str, ...]
    passed: bool
    per_sample: tuple[RagCheckReport, ...]

    def as_dict(self) -> dict[str, object]:
        """JSON-ready aggregate view (RU: словарь)."""
        return {
            "n": self.n,
            "ragas": {k: round(v, 6) for k, v in self.ragas.items()},
            "deepeval": {k: round(v, 6) for k, v in self.deepeval.items()},
            "n_passed": self.n_passed,
            "n_phantom": self.n_phantom,
            "judge_model": self.judge_model,
            "thresholds": dict(self.thresholds),
            "failures": list(self.failures),
            "passed": self.passed,
            "per_sample": [r.as_dict() for r in self.per_sample],
        }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_batch(
    samples: Iterable[RagSample],
    *,
    thresholds: Mapping[str, float] | None = None,
) -> AggregateReport:
    """Evaluate a batch and macro-average the metrics with a single gate (§18.9).

    The batch gate fails when the **mean** of any gated metric misses its
    threshold (RAGAS ``faithfulness`` regression / hallucination growth act as a
    regression gate — §18.11). ``per_sample`` keeps every individual report so a
    single failing question is still visible.
    """
    thr = dict(DEFAULT_THRESHOLDS if thresholds is None else thresholds)
    reports = [evaluate_sample(s, thresholds=thr) for s in samples]
    if not reports:
        raise ValueError("samples must be non-empty (RU: пустой набор)")

    ragas = {m: _mean([r.ragas[m] for r in reports]) for m in RAGAS_METRICS}
    deepeval = {
        m: _mean([r.deepeval[m] for r in reports]) for m in DEEPEVAL_METRICS
    }
    gate_values = dict(ragas)
    gate_values["citation_groundedness"] = deepeval["citation_groundedness"]
    gate_values["hallucination"] = deepeval["hallucination"]
    failures = _gate(gate_values, thr)

    return AggregateReport(
        n=len(reports),
        ragas=ragas,
        deepeval=deepeval,
        n_passed=sum(1 for r in reports if r.passed),
        n_phantom=sum(1 for r in reports if r.phantom_citations),
        judge_model=JUDGE_MODEL,
        thresholds=thr,
        failures=failures,
        passed=not failures,
        per_sample=tuple(reports),
    )
