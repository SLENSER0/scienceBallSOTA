"""Ingestion CLI (§24.5): discover corpus files and ingest into the KG.

python -m ingestion_service.cli ingest --limit 30
python -m ingestion_service.cli ingest --limit 5 --llm
python -m ingestion_service.cli discover
"""

from __future__ import annotations

import argparse
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ingestion_service.parsers import SUPPORTED, ParsedDoc, parse_document
from ingestion_service.pipeline import IngestionPipeline
from kg_common import get_logger, get_settings
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("ingest.cli")


def _parse_one(path_str: str) -> ParsedDoc | None:
    return parse_document(path_str)


def discover(data_dir: str) -> list[Path]:
    root = Path(data_dir)
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED]
    files.sort()
    return files


def cmd_discover(args: argparse.Namespace) -> None:
    files = discover(args.data_dir)
    by_ext: dict[str, int] = {}
    for f in files:
        by_ext[f.suffix.lower()] = by_ext.get(f.suffix.lower(), 0) + 1
    print(f"discoverable files: {len(files)}")
    for ext, n in sorted(by_ext.items(), key=lambda kv: -kv[1]):
        print(f"  {ext}: {n}")


def cmd_ingest(args: argparse.Namespace) -> None:
    s = get_settings()
    s.ensure_runtime_dirs()
    files = discover(args.data_dir)
    if args.shuffle:
        random.Random(args.seed).shuffle(files)
    if args.limit and args.limit > 0:  # limit <= 0 means "all docs"
        files = files[: args.limit]

    store = KuzuGraphStore(s.kuzu_db_path)
    if not args.keep_seed and store.counts()["nodes"] == 0:
        from kg_retrievers.seed import build_seed_graph

        build_seed_graph(store)

    pipe = IngestionPipeline(store, use_llm=args.llm, llm_max_chunks=args.llm_chunks)
    t0 = time.time()
    done = 0

    def _ingest_parsed(parsed: ParsedDoc | None) -> None:
        nonlocal done
        done += 1
        if parsed is None:
            pipe.stats.errors += 1
            return
        try:
            res = pipe.ingest(parsed)
            if done % 10 == 0 or res.get("status") == "ok":
                print(
                    f"[{done}/{len(files)}] {res['status']}: {res.get('title', '')[:55]}"
                    f"  (nodes={pipe.store.counts()['nodes']})",
                    flush=True,
                )
        except Exception as exc:
            pipe.stats.errors += 1
            _log.warning("ingest.doc_failed", title=parsed.title, error=str(exc)[:120])

    if args.workers > 1:
        # Parse in parallel across processes; write to Kuzu serially (single writer).
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_parse_one, str(f)): f for f in files}
            for fut in as_completed(futures):
                try:
                    _ingest_parsed(fut.result())
                except Exception:
                    pipe.stats.errors += 1
    else:
        for f in files:
            _ingest_parsed(_parse_one(str(f)))

    dt = time.time() - t0
    counts = store.counts()
    print("\n=== INGESTION REPORT ===")
    print(f"  files seen:   {len(files)}")
    for k, v in pipe.stats.as_dict().items():
        if k != "by_label":
            print(f"  {k}: {v}")
    print(f"  graph totals: {counts}")
    print(f"  elapsed:      {dt:.1f}s")
    store.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="ingestion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--data-dir", default=get_settings().data_dir)
    d.set_defaults(func=cmd_discover)
    ing = sub.add_parser("ingest")
    ing.add_argument("--data-dir", default=get_settings().data_dir)
    ing.add_argument("--limit", type=int, default=20)
    ing.add_argument("--llm", action="store_true")
    ing.add_argument("--llm-chunks", type=int, default=3)
    ing.add_argument("--shuffle", action="store_true")
    ing.add_argument("--seed", type=int, default=42)
    ing.add_argument("--keep-seed", action="store_true")
    ing.add_argument("--workers", type=int, default=1)
    ing.set_defaults(func=cmd_ingest)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
