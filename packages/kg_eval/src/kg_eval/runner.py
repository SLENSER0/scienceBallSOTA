"""Eval runner (§24.18/§24.22): run golden cases end-to-end through the agent.

    python -m kg_eval.runner --suite domain_science_ball           # deterministic
    python -m kg_eval.runner --suite domain_science_ball --llm     # with OSS LLM synth

Builds a seeded temp graph, runs each case through the LangGraph agent, scores it,
prints a report, and (optionally) checks RU/EN parity. Writes a Markdown report.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from kg_common import get_logger
from kg_eval.golden import load_cases
from kg_eval.metrics import CaseResult, score_case
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph

_log = get_logger("eval")


def run_suite(
    suite: str = "domain_science_ball",
    *,
    use_llm: bool = False,
    store_path: str | None = None,
    check_parity: bool = True,
) -> list[CaseResult]:
    from agent_service.agent import answer_query

    if store_path:
        store = KuzuGraphStore(store_path, read_only=True)
        owned = False
    else:
        d = tempfile.mkdtemp()
        store = KuzuGraphStore(str(Path(d) / "g"))
        build_seed_graph(store)
        owned = True

    cases = load_cases(suite)
    results: list[CaseResult] = []
    for case in cases:
        ans = answer_query(case.query, store, use_llm=use_llm)
        res = score_case(case, ans)
        # RU/EN parity: EN query should recover comparable entities
        if check_parity and case.query_en:
            ans_en = answer_query(case.query_en, store, use_llm=False)
            en_ids = {e.get("id") for e in (ans_en.parsed_query or {}).get("entities", [])}
            ru_ids = {e.get("id") for e in (ans.parsed_query or {}).get("entities", [])}
            parity = len(en_ids & ru_ids) / max(1, len(ru_ids)) if ru_ids else 1.0
            res.checks["ru_en_parity"] = parity >= 0.5
            res.notes.append(f"ru/en entity overlap: {parity:.0%}")
        res.passed = all(res.checks.values()) if res.checks else False
        results.append(res)
    if owned:
        store.close()
    return results


def print_report(results: list[CaseResult], *, use_llm: bool) -> str:
    lines = ["# Domain eval — «Научный клубок»", ""]
    lines.append(f"Synthesis: {'OSS LLM' if use_llm else 'deterministic'}")
    passed = sum(r.passed for r in results)
    lines.append(f"**{passed}/{len(results)} cases passed**")
    lines.append("")
    for r in results:
        mark = "✅" if r.passed else "⚠️"
        lines.append(f"## {mark} {r.id} — {r.title}")
        lines.append(f"- score: {r.score:.0%} · entity recall: {r.entity_recall:.0%}")
        for name, ok in r.checks.items():
            lines.append(f"  - {'✓' if ok else '✗'} {name}")
        for n in r.notes:
            lines.append(f"  - _{n}_")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(prog="kg-eval")
    ap.add_argument("--suite", default="domain_science_ball")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--store", default=None, help="use an existing Kuzu store (read-only)")
    ap.add_argument("--no-parity", action="store_true")
    args = ap.parse_args()

    results = run_suite(
        args.suite, use_llm=args.llm, store_path=args.store, check_parity=not args.no_parity
    )
    report = print_report(results, use_llm=args.llm)
    print(report)

    out = Path(__file__).resolve().parents[4] / "docs" / "eval" / f"{args.suite}_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nreport → {out}")
    passed = sum(r.passed for r in results)
    if passed < len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
