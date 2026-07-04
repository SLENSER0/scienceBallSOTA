"""Eval regression-gate + Markdown/HTML report with run-to-run diff (§18.11).

CI-ворота качества: сравнивает метрики текущего прогона с (а) baseline-порогами и
(б) предыдущим прогоном, и решает pass/fail — падение любой higher-is-better
метрики §15.2 (Recall@10/MRR/nDCG/citation-precision/…) ниже порога ИЛИ просадка
относительно прошлого прогона сверх допуска, либо рост lower-is-better метрики
(unsupported-claim-rate) — регрессия и exit-code ≠ 0. Затем рендерит читаемый
двуязычный отчёт (Markdown + автономный HTML) со сводкой по категориям §15.1 и
diff-колонками (порог, прошлый прогон, текущее, дельта, статус).

Regression gate for eval metrics: compares a current-run metrics dict against
per-metric baseline thresholds AND the previous run, then emits a pass/fail
:class:`GateResult` (exit code ≠ 0 on any below-threshold or regressed metric) plus
Markdown and self-contained HTML renderers with a per-category summary and a
run-to-run diff.

Direction-aware — каждая метрика знает, «больше == лучше» или «меньше == лучше»
(:class:`MetricSpec.higher_is_better`), так что unsupported-rate (меньше лучше)
обрабатывается без спец-кейсов на местах вызова.

Pure-python: только ``html``/``json`` из stdlib. Детерминированно — одинаковый вход
(включая переданные ``git_sha``/``dataset_version``/``generated_at``) даёт
байт-в-байт одинаковый вывод. Reuses the metric direction catalogue from
:mod:`kg_eval.metric_registry` where a metric is registered.
"""

from __future__ import annotations

import html as _html
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kg_eval.metric_registry import metric_for

# Rounding applied to a delta before a tolerance test — guards against float noise
# (e.g. ``0.62 - 0.6 == 0.020000000000000018``) at the tolerance edge (см. eval_diff).
_NDIGITS = 9

_PASS = "pass"
_FAIL = "fail"

# Per-row status codes (most-severe first — used to colour the report).
STATUS_MISSING = "missing"  # metric absent from the current run → gate fail
STATUS_BELOW = "below_threshold"  # current worse than its baseline threshold
STATUS_REGRESSED = "regressed"  # current worse than the previous run beyond tol
STATUS_IMPROVED = "improved"  # current better than the previous run beyond tol
STATUS_OK = "ok"  # passes threshold, no material change vs previous
STATUS_NEW = "new"  # passes threshold, no previous run to diff against

# Statuses that make the overall gate fail (exit code ≠ 0).
_FAILING = frozenset({STATUS_MISSING, STATUS_BELOW, STATUS_REGRESSED})


@dataclass(frozen=True)
class MetricSpec:
    """Gate configuration for one eval metric (§18.11).

    ``threshold`` is the baseline the metric must clear (compared in the metric's
    own direction); ``tol`` is the run-to-run tolerance below which a change is
    "unchanged". ``category`` groups the metric in the report (§15.1).
    """

    name: str
    category: str
    higher_is_better: bool
    threshold: float
    tol: float = 0.02
    label: str = ""

    def display(self) -> str:
        """Human label for the report (falls back to the raw metric name)."""
        return self.label or self.name


# Canonical §15.2 gate metrics grouped by §15.1 category. Thresholds are the
# baseline a run must clear; edit here (or pass ``specs=``) to retune the gate.
DEFAULT_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("recall_at_10", "Retrieval / Поиск", True, 0.60, 0.02, "Recall@10"),
    MetricSpec("mrr", "Retrieval / Поиск", True, 0.50, 0.02, "MRR"),
    MetricSpec("ndcg_at_10", "Retrieval / Поиск", True, 0.55, 0.02, "nDCG@10"),
    MetricSpec("precision_at_10", "Retrieval / Поиск", True, 0.30, 0.02, "Precision@10"),
    MetricSpec("citation_precision", "Grounding / Обоснование", True, 0.70, 0.03, "Citation prec."),
    MetricSpec(
        "unsupported_rate", "Grounding / Обоснование", False, 0.20, 0.03, "Unsupported-rate"
    ),
    MetricSpec("extraction_f1", "Extraction / Извлечение", True, 0.70, 0.02, "Extraction F1"),
    MetricSpec("er_f1", "Extraction / Извлечение", True, 0.70, 0.02, "ER F1"),
    MetricSpec(
        "graph_path_correctness", "Reasoning / Рассуждение", True, 0.75, 0.02, "Graph-path corr."
    ),
    MetricSpec(
        "contradiction_recall", "Reasoning / Рассуждение", True, 0.60, 0.03, "Contradiction rec."
    ),
    MetricSpec("gap_precision", "Reasoning / Рассуждение", True, 0.60, 0.03, "Gap precision"),
    MetricSpec("ragas_faithfulness", "Answer / Ответ", True, 0.80, 0.03, "RAGAS faithfulness"),
)


def _round(value: float) -> float:
    return round(float(value), _NDIGITS)


@dataclass(frozen=True)
class MetricRow:
    """One metric compared against its threshold and the previous run (§18.11).

    ``delta`` is ``current - previous`` (raw, direction-agnostic) or ``None`` when
    there is no previous run. ``gate_pass`` is threshold conformance;
    ``regressed`` / ``improved`` are run-to-run verdicts. ``status`` is the single
    most-severe label (see the ``STATUS_*`` constants).
    """

    metric: str
    label: str
    category: str
    higher_is_better: bool
    threshold: float
    previous: float | None
    current: float | None
    delta: float | None
    gate_pass: bool
    regressed: bool
    improved: bool
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "label": self.label,
            "category": self.category,
            "higher_is_better": self.higher_is_better,
            "threshold": self.threshold,
            "previous": self.previous,
            "current": self.current,
            "delta": self.delta,
            "gate_pass": self.gate_pass,
            "regressed": self.regressed,
            "improved": self.improved,
            "status": self.status,
        }


@dataclass(frozen=True)
class CategorySummary:
    """Per-category (§15.1) pass/fail roll-up for the report header."""

    category: str
    total: int
    passed: int
    failed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
        }


@dataclass(frozen=True)
class GateResult:
    """Regression-gate verdict + full diff, ready to render or serialize (§18.11).

    ``verdict`` is ``"fail"`` iff any row is below threshold, regressed, or missing;
    ``exit_code`` mirrors it (``1`` on fail, ``0`` on pass) for CI. ``rows`` is the
    per-metric diff; ``categories`` the §15.1 roll-up; ``failures`` the failing
    metric names (sorted).
    """

    verdict: str
    exit_code: int
    rows: tuple[MetricRow, ...]
    categories: tuple[CategorySummary, ...]
    failures: tuple[str, ...]
    regressions: tuple[str, ...]
    improvements: tuple[str, ...]
    generated_from: str = ""
    generated_at: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == _PASS

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "rows": [r.as_dict() for r in self.rows],
            "categories": [c.as_dict() for c in self.categories],
            "failures": list(self.failures),
            "regressions": list(self.regressions),
            "improvements": list(self.improvements),
            "generated_from": self.generated_from,
            "generated_at": self.generated_at,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Deterministic JSON (``sort_keys``) of :meth:`as_dict`."""
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    def to_markdown(self) -> str:
        """Bilingual Markdown report with a diff table grouped by category (§18.11)."""
        return _render_markdown(self)

    def to_html(self) -> str:
        """Self-contained HTML report (inline CSS, colour-coded diff) (§18.11)."""
        return _render_html(self)


def _clears_threshold(value: float, threshold: float, higher_is_better: bool) -> bool:
    """Does ``value`` meet ``threshold`` in the metric's own direction?"""
    if higher_is_better:
        return _round(value) >= _round(threshold)
    return _round(value) <= _round(threshold)


def _direction_of(spec: MetricSpec) -> bool:
    """Metric direction — the registry wins when the metric is registered (§18.10)."""
    reg = metric_for(spec.name)
    return reg.higher_is_better if reg is not None else spec.higher_is_better


def _row_for(
    spec: MetricSpec,
    current: Mapping[str, float],
    previous: Mapping[str, float] | None,
) -> MetricRow:
    hib = _direction_of(spec)
    cur = current.get(spec.name)
    prev = None if previous is None else previous.get(spec.name)

    if cur is None:
        # Metric absent from the current run → cannot confirm the gate; treat as fail.
        return MetricRow(
            metric=spec.name,
            label=spec.display(),
            category=spec.category,
            higher_is_better=hib,
            threshold=spec.threshold,
            previous=None if prev is None else _round(prev),
            current=None,
            delta=None,
            gate_pass=False,
            regressed=False,
            improved=False,
            status=STATUS_MISSING,
        )

    cur_v = _round(cur)
    gate_pass = _clears_threshold(cur_v, spec.threshold, hib)

    delta: float | None = None
    regressed = False
    improved = False
    if prev is not None:
        prev_v = _round(prev)
        delta = _round(cur_v - prev_v)
        # Signed improvement in the metric's own direction (positive == better).
        gain = delta if hib else -delta
        if gain < -spec.tol:
            regressed = True
        elif gain > spec.tol:
            improved = True

    if not gate_pass:
        status = STATUS_BELOW
    elif regressed:
        status = STATUS_REGRESSED
    elif improved:
        status = STATUS_IMPROVED
    elif prev is None:
        status = STATUS_NEW
    else:
        status = STATUS_OK

    return MetricRow(
        metric=spec.name,
        label=spec.display(),
        category=spec.category,
        higher_is_better=hib,
        threshold=spec.threshold,
        previous=None if prev is None else _round(prev),
        current=cur_v,
        delta=delta,
        gate_pass=gate_pass,
        regressed=regressed,
        improved=improved,
        status=status,
    )


def evaluate_gate(
    current: Mapping[str, float],
    *,
    previous: Mapping[str, float] | None = None,
    specs: tuple[MetricSpec, ...] | None = None,
    git_sha: str = "",
    dataset_version: str = "",
    generated_at: str = "",
) -> GateResult:
    """Compare ``current`` vs baseline thresholds + ``previous`` run → :class:`GateResult`.

    Для каждой метрики из ``specs`` (по умолчанию :data:`DEFAULT_SPECS`) считается
    строка diff: проходит ли порог и как изменилась относительно прошлого прогона.
    Метрики без спецификации во входных данных игнорируются; спецификация без
    значения в ``current`` — провал (``missing``). Вердикт ``"fail"``, если есть
    хотя бы один провал порога / регрессия / отсутствие. ``exit_code`` = 1 при fail.

    Only metrics with a spec are gated; extra keys in ``current`` are ignored, and a
    spec absent from ``current`` fails as ``missing``. Deterministic for a fixed
    input (including the passed provenance strings).
    """
    active = DEFAULT_SPECS if specs is None else specs
    rows = tuple(_row_for(spec, current, previous) for spec in active)

    failures = sorted(r.metric for r in rows if r.status in _FAILING)
    regressions = sorted(r.metric for r in rows if r.regressed)
    improvements = sorted(r.metric for r in rows if r.improved)

    # Per-category roll-up (§15.1), preserving spec order of first appearance.
    order: list[str] = []
    buckets: dict[str, list[MetricRow]] = {}
    for r in rows:
        if r.category not in buckets:
            buckets[r.category] = []
            order.append(r.category)
        buckets[r.category].append(r)
    categories = tuple(
        CategorySummary(
            category=cat,
            total=len(buckets[cat]),
            passed=sum(1 for r in buckets[cat] if r.status not in _FAILING),
            failed=sum(1 for r in buckets[cat] if r.status in _FAILING),
        )
        for cat in order
    )

    verdict = _FAIL if failures else _PASS
    generated_from = f"git_sha={git_sha}; dataset_version={dataset_version}"
    return GateResult(
        verdict=verdict,
        exit_code=1 if verdict == _FAIL else 0,
        rows=rows,
        categories=categories,
        failures=tuple(failures),
        regressions=tuple(regressions),
        improvements=tuple(improvements),
        generated_from=generated_from,
        generated_at=generated_at,
    )


# --- Rendering ---------------------------------------------------------------

# Arrow + word per status, reused by both renderers (EN/RU).
_STATUS_TEXT: dict[str, str] = {
    STATUS_MISSING: "—  missing / нет данных",
    STATUS_BELOW: "✗  below threshold / ниже порога",
    STATUS_REGRESSED: "▼  regressed / регрессия",
    STATUS_IMPROVED: "▲  improved / улучшение",
    STATUS_OK: "✓  ok / без изменений",
    STATUS_NEW: "•  new / новый",
}


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "—"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _fmt_delta(row: MetricRow) -> str:
    if row.delta is None:
        return "—"
    sign = "+" if row.delta > 0 else ""
    return f"{sign}{_fmt_num(row.delta)}"


def _render_markdown(result: GateResult) -> str:
    badge = "PASS ✓" if result.passed else "FAIL ✗"
    lines: list[str] = [
        "# Eval Regression Gate / Регрессионный gate оценки",
        "",
        f"**Verdict / Вердикт: {badge}**  (exit code {result.exit_code})",
        "",
        f"_Generated from / Сформировано из: {result.generated_from}_",
    ]
    if result.generated_at:
        lines.append(f"_At / Время: {result.generated_at}_")
    lines.append("")

    # Category summary.
    lines.append("## Summary by category / Сводка по категориям (§15.1)")
    lines.append("")
    lines.append("| Category / Категория | Passed / Прошло | Failed / Провал |")
    lines.append("| --- | --- | --- |")
    for c in result.categories:
        lines.append(f"| {c.category} | {c.passed}/{c.total} | {c.failed} |")
    lines.append("")

    if result.failures:
        lines.append(f"**Failing / Провалившиеся: {', '.join(result.failures)}**")
        lines.append("")

    # Per-metric diff table.
    lines.append("## Metric diff / Диф метрик (§15.2)")
    lines.append("")
    lines.append(
        "| Metric / Метрика | Category | Threshold / Порог | Previous / Прошлое "
        "| Current / Текущее | Δ | Status / Статус |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in result.rows:
        arrow = "↑" if r.higher_is_better else "↓"
        lines.append(
            f"| {r.label} {arrow} | {r.category} | {_fmt_num(r.threshold)} "
            f"| {_fmt_num(r.previous)} | {_fmt_num(r.current)} | {_fmt_delta(r)} "
            f"| {_STATUS_TEXT.get(r.status, r.status)} |"
        )
    lines.append("")
    return "\n".join(lines)


# Status → (background, text) colour for the HTML report (light-scheme friendly).
_STATUS_COLOR: dict[str, tuple[str, str]] = {
    STATUS_MISSING: ("#fde2e2", "#7f1d1d"),
    STATUS_BELOW: ("#fde2e2", "#7f1d1d"),
    STATUS_REGRESSED: ("#fde0d5", "#9a3412"),
    STATUS_IMPROVED: ("#dcfce7", "#166534"),
    STATUS_OK: ("#eef2f7", "#334155"),
    STATUS_NEW: ("#e0eefe", "#1e40af"),
}


def _esc(text: str) -> str:
    return _html.escape(text, quote=True)


def _render_html(result: GateResult) -> str:
    ok = result.passed
    banner_bg = "#166534" if ok else "#991b1b"
    badge = "PASS ✓" if ok else "FAIL ✗"

    cat_rows = "".join(
        f"<tr><td>{_esc(c.category)}</td>"
        f"<td style='text-align:center'>{c.passed}/{c.total}</td>"
        f"<td style='text-align:center;color:{'#166534' if c.failed == 0 else '#991b1b'}'>"
        f"{c.failed}</td></tr>"
        for c in result.categories
    )

    metric_rows = []
    for r in result.rows:
        bg, fg = _STATUS_COLOR.get(r.status, ("#eef2f7", "#334155"))
        arrow = "↑" if r.higher_is_better else "↓"
        metric_rows.append(
            "<tr>"
            f"<td><strong>{_esc(r.label)}</strong> "
            f"<span style='color:#94a3b8'>{arrow}</span></td>"
            f"<td>{_esc(r.category)}</td>"
            f"<td style='text-align:right'>{_esc(_fmt_num(r.threshold))}</td>"
            f"<td style='text-align:right'>{_esc(_fmt_num(r.previous))}</td>"
            f"<td style='text-align:right'><strong>{_esc(_fmt_num(r.current))}</strong></td>"
            f"<td style='text-align:right'>{_esc(_fmt_delta(r))}</td>"
            f"<td style='background:{bg};color:{fg};font-weight:600'>"
            f"{_esc(_STATUS_TEXT.get(r.status, r.status))}</td>"
            "</tr>"
        )
    metric_body = "".join(metric_rows)

    fail_note = ""
    if result.failures:
        fail_note = (
            "<p class='fail'>Failing / Провалившиеся: "
            f"<code>{_esc(', '.join(result.failures))}</code></p>"
        )

    prov = _esc(result.generated_from)
    at = f"<span class='prov'>{_esc(result.generated_at)}</span>" if result.generated_at else ""

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval Regression Gate — {badge}</title>
<style>
 :root {{ color-scheme: light; }}
 body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        margin: 0; background: #f8fafc; color: #0f172a; }}
 .wrap {{ max-width: 960px; margin: 0 auto; padding: 24px 20px 48px; }}
 .banner {{ background: {banner_bg}; color: #fff; border-radius: 12px;
           padding: 18px 22px; display: flex; align-items: baseline;
           justify-content: space-between; gap: 12px; }}
 .banner h1 {{ font-size: 20px; margin: 0; font-weight: 700; }}
 .banner .badge {{ font-size: 22px; font-weight: 800; letter-spacing: .5px; }}
 .prov {{ color: #64748b; font-size: 13px; }}
 h2 {{ font-size: 15px; margin: 28px 0 10px; color: #334155;
       text-transform: uppercase; letter-spacing: .04em; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 14px;
          background: #fff; border-radius: 10px; overflow: hidden;
          box-shadow: 0 1px 2px rgba(15,23,42,.06); }}
 th, td {{ padding: 8px 12px; border-bottom: 1px solid #eef2f7; text-align: left; }}
 th {{ background: #f1f5f9; font-weight: 600; color: #475569; }}
 tr:last-child td {{ border-bottom: none; }}
 .scroll {{ overflow-x: auto; }}
 .fail {{ color: #991b1b; font-weight: 600; }}
 code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 5px; }}
 .exit {{ font-size: 13px; opacity: .85; }}
</style></head>
<body><div class="wrap">
 <div class="banner">
   <div><h1>Eval Regression Gate · Регрессионный gate (§18.11)</h1>
   <div class="exit">exit code {result.exit_code}</div></div>
   <div class="badge">{badge}</div>
 </div>
 <p class="prov">{prov} {at}</p>
 {fail_note}
 <h2>Summary by category / Сводка по категориям</h2>
 <div class="scroll"><table>
  <thead><tr><th>Category / Категория</th><th>Passed / Прошло</th>
  <th>Failed / Провал</th></tr></thead>
  <tbody>{cat_rows}</tbody>
 </table></div>
 <h2>Metric diff / Диф метрик</h2>
 <div class="scroll"><table>
  <thead><tr><th>Metric / Метрика</th><th>Category</th><th>Threshold</th>
  <th>Previous</th><th>Current</th><th>Δ</th><th>Status / Статус</th></tr></thead>
  <tbody>{metric_body}</tbody>
 </table></div>
</div></body></html>"""
