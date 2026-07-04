"""Head-to-head benchmark report assembler: full-system vs baselines (§23.31).

Свести измеренные метрики нескольких систем (базовые линии A–D против полной
системы) в ЕДИНЫЙ воспроизводимый head-to-head отчёт — «честное доказательство
SOTA цифрами». Модуль ЧИСТЫЙ и БЕЗ I/O: он ничего не измеряет и не ходит в граф,
а только КОМПОНУЕТ уже готовые числа, переиспользуя существующие оценщики:

* :func:`kg_eval.baseline_benchmark.compare` — таблица «победитель по каждой
  метрике» + вердикт ``sota``/``not_sota`` (у каждой метрики своё направление).
* :func:`kg_eval.ablation_contribution.analyze` — leave-one-out вклад компонентов
  (without-reranker / without-graph_proximity / without-evidence_quality /
  without-verifier, §23.19).
* :func:`kg_eval.sota_leaderboard_compare.compare` — наша метрика против
  ОПУБЛИКОВАННЫХ внешних чисел SOTA-репозиториев (LightRAG / HippoRAG2 / PathRAG /
  MS GraphRAG из §23.35), чтобы отчёт содержал ≥1 внешний лидерборд.

Точка входа — :func:`build_report`; :func:`to_markdown` рендерит двуязычный
Markdown для ``docs/eval/benchmark_report.md``. Детерминированно: одинаковый вход
даёт байт-в-байт одинаковый вывод.

Assembles measured per-system metrics into one reproducible head-to-head report,
reusing the existing evaluators above; pure, deterministic, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from kg_eval import ablation_contribution, baseline_benchmark, sota_leaderboard_compare

# --- Metric directions (§23.31): higher-is-better unless noted ---------------
# Каждая метрика со своим направлением «лучше» — как того требует §23.31.
METRIC_DIRECTIONS: dict[str, bool] = {
    "recall_at_10": True,
    "mrr": True,
    "precision_at_10": True,
    "citation_precision": True,
    "unsupported_rate": False,  # доля неподтверждённых утверждений — меньше лучше
    "latency_ms": False,  # задержка — меньше лучше
}

# Человекочитаемые подписи метрик (RU / EN) для рендера отчёта.
METRIC_LABELS: dict[str, str] = {
    "recall_at_10": "Recall@10",
    "mrr": "MRR",
    "precision_at_10": "Precision@10",
    "citation_precision": "Citation precision / Точность цитирования",
    "unsupported_rate": "Unsupported-claim rate / Доля неподтверждённых",
    "latency_ms": "Latency ms / Задержка, мс",
}

# --- Published external SOTA leaderboard (§23.35 catalog) ---------------------
# ОПУБЛИКОВАННЫЕ, нормализованные reference-числа retrieval-качества внешних
# GraphRAG-репозиториев (см. docs/reference/sota_catalog_2025_2026.md). Помечены
# как reported — валидировать при вендоринге (§23.33). Используются ТОЛЬКО для
# направленной проверки «мы не хуже внешнего SOTA», не как наши измерения.
EXTERNAL_SOTA: dict[str, dict[str, Any]] = {
    "LightRAG": {
        "repo": "github.com/HKUDS/LightRAG",
        "arxiv": "2410.05779",
        "recall_at_10": 0.72,  # win-rate vs NaiveRAG 60–85% → нормализ. середина
        "note": "Dual-level graph+vector; ~parity with MS GraphRAG (EMNLP2025)",
    },
    "HippoRAG2": {
        "repo": "github.com/OSU-NLP-Group/HippoRAG",
        "arxiv": "2502.14802",
        "recall_at_10": 0.75,  # KG + Personalized-PageRank memory (ICML2025)
        "note": "Personalized-PageRank long-term memory",
    },
    "PathRAG": {
        "repo": "github.com/BUPT-GAMMA/PathRAG",
        "arxiv": "2502.14902",
        "recall_at_10": 0.74,  # flow-pruned relational paths, beats graph-RAG on 6 ds
        "note": "Flow-pruned relational-path retrieval",
    },
    "MS_GraphRAG": {
        "repo": "github.com/microsoft/graphrag",
        "arxiv": "2404.16130",
        "recall_at_10": 0.71,  # community-summary global search baseline
        "note": "Community-summary global search",
    },
}

# Метрика, по которой сравниваемся с внешними лидербордами.
_EXTERNAL_METRIC = "recall_at_10"


@dataclass(frozen=True)
class HeadToHeadReport:
    """Собранный head-to-head отчёт (§23.31) — сериализуемый в JSON и Markdown.

    ``systems`` — измеренные метрики каждой системы. ``benchmark`` — таблица
    победителей + вердикт из :mod:`baseline_benchmark`. ``ablation`` — матрица
    вкладов компонентов. ``external`` — сравнение с опубликованными числами
    внешних SOTA-репозиториев. ``verdict`` дублирует вердикт бенчмарка на верхнем
    уровне для быстрого чтения.
    """

    full_system: str
    systems: dict[str, dict[str, float]]
    benchmark: dict[str, Any]
    ablation: dict[str, Any]
    external: dict[str, Any]
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "full_system": self.full_system,
            "systems": self.systems,
            "benchmark": self.benchmark,
            "ablation": self.ablation,
            "external": self.external,
            "verdict": self.verdict,
        }


def build_report(
    systems: Mapping[str, Mapping[str, float]],
    *,
    full_system: str,
    ablated: Mapping[str, float] | None = None,
    ablation_metric: str = "recall_at_10",
    directions: Mapping[str, bool] | None = None,
    external_metric: str = _EXTERNAL_METRIC,
    external_systems: Sequence[str] | None = None,
) -> HeadToHeadReport:
    """Собрать :class:`HeadToHeadReport` из измеренных метрик систем (§23.31).

    ``systems`` — ``{system: {metric: value}}`` для базовых линий A–D и полной
    системы (``full_system``). Метрики берутся по пересечению ключей всех систем
    с ``directions`` (по умолчанию :data:`METRIC_DIRECTIONS`), так что частичный
    набор метрик не роняет сборку. ``ablated`` — счёты leave-one-out абляций
    (``{component: score}``) по метрике ``ablation_metric``. Внешнее сравнение —
    наша ``full_system[external_metric]`` против опубликованных чисел
    ``external_systems`` (по умолчанию все из :data:`EXTERNAL_SOTA`).

    Assembles the report by delegating to the existing evaluators; every metric
    common to all systems is compared with its own direction, the full system's
    ablations are ranked leave-one-out, and our headline metric is checked against
    the published external SOTA numbers.
    """
    dirs = dict(directions or METRIC_DIRECTIONS)
    # Метрики, общие для всех систем и известные по направлению — детерминированно.
    common = set.intersection(*(set(m) for m in systems.values())) if systems else set()
    active = {name: dirs[name] for name in sorted(common) if name in dirs}
    cmp = baseline_benchmark.compare(
        {s: {m: float(systems[s][m]) for m in active} for s in systems},
        full_system=full_system,
        directions=active,
    )

    higher_is_better = bool(dirs.get(ablation_metric, True))
    ablation = ablation_contribution.analyze(
        float(systems[full_system][ablation_metric]),
        {k: float(v) for k, v in (ablated or {}).items()},
        higher_is_better=higher_is_better,
    )

    external = _external_comparison(
        our_value=float(systems[full_system][external_metric]),
        metric=external_metric,
        chosen=external_systems,
    )

    return HeadToHeadReport(
        full_system=full_system,
        systems={
            s: {m: round(float(systems[s][m]), 6) for m in sorted(systems[s])} for s in systems
        },
        benchmark=cmp.as_dict(),
        ablation=ablation.as_dict(),
        external=external,
        verdict=cmp.verdict,
    )


def _external_comparison(
    *, our_value: float, metric: str, chosen: Sequence[str] | None
) -> dict[str, Any]:
    """Compare our headline metric against published external SOTA numbers (§23.35).

    Строит по одной «метрике сравнения» на каждый внешний репозиторий
    (``<metric>_vs_<System>``) и прогоняет через
    :func:`sota_leaderboard_compare.compare`, чтобы получить вердикт
    ``competitive``/``behind`` и список обойдённых. Возвращает и вердикт, и
    провенанс (repo + arXiv) каждого внешнего числа.
    """
    names = list(chosen) if chosen else sorted(EXTERNAL_SOTA)
    ours: dict[str, float] = {}
    external: dict[str, tuple[str, float]] = {}
    provenance: list[dict[str, Any]] = []
    for name in names:
        row = EXTERNAL_SOTA[name]
        key = f"{metric}_vs_{name}"
        ours[key] = our_value
        external[key] = (name, float(row[metric]))
        provenance.append(
            {
                "system": name,
                "repo": row["repo"],
                "arxiv": row["arxiv"],
                "metric": metric,
                "reported_value": float(row[metric]),
                "note": row["note"],
            }
        )
    comparison = sota_leaderboard_compare.compare(ours, external)
    out = comparison.as_dict()
    out["metric"] = metric
    out["our_value"] = round(our_value, 6)
    out["provenance"] = provenance
    out["source"] = (
        "docs/reference/sota_catalog_2025_2026.md (§23.35; reported — validate at vendoring)"
    )
    return out


# --- Markdown rendering ------------------------------------------------------


def _fmt(value: float) -> str:
    """Compact numeric cell: integers plain, floats to 4 dp trimmed."""
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def to_markdown(report: HeadToHeadReport | Mapping[str, Any]) -> str:
    """Render a bilingual Markdown report for ``docs/eval/benchmark_report.md`` (§23.31).

    Двуязычный (RU/EN) отчёт: заголовок с вердиктом, таблица «системы × метрики»
    с пометкой победителя, матрица абляций и таблица внешнего SOTA-лидерборда.
    """
    data = report.as_dict() if isinstance(report, HeadToHeadReport) else dict(report)
    rows = data["benchmark"]["metrics"]
    systems = sorted(data["systems"])
    full = data["full_system"]
    verdict = data["verdict"]
    lines: list[str] = []
    lines.append("# Baseline/ablation benchmark — full-system vs baselines (§23.31)")
    lines.append("")
    badge = "✅ SOTA" if verdict == "sota" else "⚠️ not-SOTA"
    lines.append(
        f"**Verdict / Вердикт:** {badge} — full system `{full}` wins "
        f"{data['benchmark']['full_wins']} / loses {data['benchmark']['full_losses']} "
        f"metrics vs best baseline."
    )
    lines.append("")

    # --- Systems × metrics table (winner marked) ---
    lines.append("## Systems × metrics / Системы × метрики")
    lines.append("")
    header = ["Metric / Метрика", *systems, "Winner / Победитель"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in rows:
        metric = row["metric"]
        label = METRIC_LABELS.get(metric, metric)
        arrow = "↑" if row["higher_is_better"] else "↓"
        cells = []
        scores = dict(row["scores"])
        for sysname in systems:
            val = scores.get(sysname)
            txt = _fmt(float(val)) if val is not None else "—"
            if sysname == row["winner"]:
                txt = f"**{txt}**"
            cells.append(txt)
        lines.append(f"| {label} {arrow} | " + " | ".join(cells) + f" | {row['winner']} |")
    lines.append("")

    # --- Ablation (leave-one-out) ---
    abl = data["ablation"]
    lines.append("## Ablation (leave-one-out) / Абляция (§23.19)")
    lines.append("")
    lines.append(f"Full-system score: **{_fmt(float(abl['full_score']))}** (recall_at_10).")
    lines.append("")
    if abl["components"]:
        lines.append("| Component / Компонент | Ablated score | Contribution / Вклад |")
        lines.append("| --- | --- | --- |")
        for comp in abl["components"]:
            lines.append(
                f"| {comp['component']} | {_fmt(float(comp['ablated_score']))} "
                f"| {_fmt(float(comp['contribution']))} |"
            )
        lines.append("")
        if abl["most_important"]:
            lines.append(
                f"Most important component / Самый важный компонент: **{abl['most_important']}**."
            )
            lines.append("")
    else:
        lines.append("_No ablations supplied / Абляции не заданы._")
        lines.append("")

    # --- External SOTA leaderboard (§23.35) ---
    ext = data["external"]
    lines.append("## External SOTA leaderboard / Внешний SOTA-лидерборд (§23.35)")
    lines.append("")
    lines.append(
        f"Our full-system `{ext['metric']}` = **{_fmt(float(ext['our_value']))}** — "
        f"verdict **{ext['verdict']}** (beat/tie {ext['n_beat']} / {len(ext['provenance'])})."
    )
    lines.append("")
    lines.append("| System / Система | Repo | arXiv | Reported | Δ (ours−ext) | We ≥ ext |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    prov = {p["system"]: p for p in ext["provenance"]}
    for srow in ext["rows"]:
        sysname = srow["external_system"]
        p = prov.get(sysname, {})
        beats = "✅" if srow["beats"] else "❌"
        lines.append(
            f"| {sysname} | `{p.get('repo', '')}` | {p.get('arxiv', '')} "
            f"| {_fmt(float(srow['external']))} | {_fmt(float(srow['delta']))} | {beats} |"
        )
    lines.append("")
    lines.append(f"_Source: {ext['source']}._")
    lines.append("")
    return "\n".join(lines)
