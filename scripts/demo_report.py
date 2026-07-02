#!/usr/bin/env python3
"""Run the 4 mandatory acceptance queries with the OSS LLM and write a report.

    python scripts/demo_report.py            # against the live store (KUZU_DB_PATH)
    python scripts/demo_report.py --seed     # against a fresh seeded temp store

Produces docs/eval/demo_report.md with full grounded answers, citations, graph
size, gaps/contradictions and the OSS models used — the end-to-end demonstration.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from kg_common import get_settings
from kg_retrievers.graph_store import KuzuGraphStore

ROOT = Path(__file__).resolve().parent.parent

QUERIES = [
    ("Обессоливание воды обогатительной фабрики",
     "Какие методы обессоливания воды подходят для обогатительной фабрики, если "
     "исходная вода содержит сульфаты, хлориды, Ca, Mg, Na по 200–300 мг/л, а "
     "требуемый сухой остаток — ≤1000 мг/дм³?"),
    ("Циркуляция католита при электроэкстракции никеля",
     "Какие технические решения организации циркуляции католита при электроэкстракции "
     "никеля описаны в мировой практике, и какая скорость потока считается оптимальной?"),
    ("Распределение Au/Ag/МПГ между штейном и шлаком",
     "Покажите все эксперименты и публикации по распределению Au, Ag и МПГ между "
     "медным и никелевым штейном и шлаком за последние 5 лет"),
    ("Закачка шахтных вод в глубокие горизонты (РФ vs зарубеж)",
     "Какие способы закачки шахтных вод в глубокие горизонты применялись в России и "
     "за рубежом, и каковы их технико-экономические показатели?"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="use a fresh seeded temp store")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    if args.seed:
        from kg_retrievers.seed import build_seed_graph

        d = tempfile.mkdtemp()
        store = KuzuGraphStore(str(Path(d) / "g"))
        build_seed_graph(store)
    else:
        store = KuzuGraphStore(get_settings().kuzu_db_path, read_only=True)

    from agent_service.agent import answer_query

    counts = store.counts()
    lines = [
        "# Демо «Научный клубок» — 4 обязательных запроса",
        "",
        f"Граф: **{counts['nodes']} узлов / {counts['rels']} связей**. "
        f"Синтез: {'детерминированный' if args.no_llm else 'OSS LLM'}.",
        "",
    ]
    for i, (title, q) in enumerate(QUERIES, start=1):
        t0 = time.time()
        ans = answer_query(q, store, use_llm=not args.no_llm)
        dt = time.time() - t0
        lines += [
            f"## {i}. {title}",
            "",
            f"> {q}",
            "",
            f"- достоверность: **{ans.confidence}** · {len(ans.citations)} источник(ов) · "
            f"граф {len(ans.graph.nodes) if ans.graph else 0} узлов · "
            f"{len(ans.contradictions)} противоречий · {len(ans.gaps)} пробелов · "
            f"{dt:.1f}s · модели: {', '.join(ans.used_models) or '—'}",
            "",
            ans.answer_markdown,
            "",
            "---",
            "",
        ]
        print(f"[{i}/4] {title}: conf={ans.confidence} cites={len(ans.citations)} "
              f"nodes={len(ans.graph.nodes) if ans.graph else 0} {dt:.1f}s")

    out = ROOT / "docs" / "eval" / "demo_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport → {out}")


if __name__ == "__main__":
    main()
