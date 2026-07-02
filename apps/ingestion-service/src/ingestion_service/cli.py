"""Ingestion CLI (§24.5): discover corpus files and ingest into the KG.

python -m ingestion_service.cli ingest --limit 30
python -m ingestion_service.cli ingest --limit 5 --llm
python -m ingestion_service.cli discover
"""

from __future__ import annotations

import argparse
import random
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ingestion_service.parsers import SUPPORTED, ParsedDoc, parse_document
from ingestion_service.pipeline import IngestionPipeline
from kg_common import get_logger, get_settings
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("ingest.cli")


def _parse_one(path_str: str) -> ParsedDoc | None:
    return parse_document(path_str)


def discover(data_dir: str, max_mb: float = 0) -> list[Path]:
    root = Path(data_dir)
    files = []
    for p in root.rglob("*"):
        if not (p.is_file() and p.suffix.lower() in SUPPORTED):
            continue
        if max_mb and p.stat().st_size > max_mb * 1_000_000:
            continue  # skip enormous books that dominate parse time
        files.append(p)
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
    files = discover(args.data_dir, max_mb=args.max_mb)
    if args.shuffle:
        random.Random(args.seed).shuffle(files)
    if args.limit and args.limit > 0:  # limit <= 0 means "all docs"
        files = files[: args.limit]

    # Resume: skip files already recorded as processed (fast, no re-parse).
    resume_path = Path(args.resume_log)
    done_paths: set[str] = set()
    if resume_path.exists():
        done_paths = set(resume_path.read_text(encoding="utf-8").splitlines())
        files = [f for f in files if str(f) not in done_paths]
        print(f"resume: skipping {len(done_paths)} already-processed files")
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_fh = resume_path.open("a", encoding="utf-8")

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

    def _record(path: str) -> None:
        resume_fh.write(path + "\n")
        resume_fh.flush()

    if args.workers > 1:
        # Parse in parallel with a BOUNDED in-flight window (avoids OOM from
        # holding all ParsedDocs at once); write to Kuzu serially (single writer).
        from concurrent.futures import FIRST_COMPLETED, wait

        window = args.workers * 2
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            it = iter(files)
            inflight: dict = {}
            for _ in range(window):
                f = next(it, None)
                if f is None:
                    break
                inflight[pool.submit(_parse_one, str(f))] = f
            while inflight:
                completed, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
                for fut in completed:
                    f = inflight.pop(fut)
                    try:
                        _ingest_parsed(fut.result())
                    except Exception:
                        pipe.stats.errors += 1
                    _record(str(f))
                    nf = next(it, None)
                    if nf is not None:
                        inflight[pool.submit(_parse_one, str(nf))] = nf
    else:
        for f in files:
            _ingest_parsed(_parse_one(str(f)))
            _record(str(f))
    resume_fh.close()

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


def cmd_index(args: argparse.Namespace) -> None:
    s = get_settings()
    s.ensure_runtime_dirs()
    store = KuzuGraphStore(s.kuzu_db_path, read_only=True)
    from kg_retrievers.indexer import index_graph

    counts = index_graph(store, limit=args.limit or None, vector=not args.no_vector)
    print("=== INDEX REPORT ===", counts)
    store.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="ingestion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--data-dir", default=get_settings().data_dir)
    d.set_defaults(func=cmd_discover)
    ix = sub.add_parser("index", help="build vector+keyword search indexes from the graph")
    ix.add_argument("--limit", type=int, default=0)
    ix.add_argument("--no-vector", action="store_true")
    ix.set_defaults(func=cmd_index)
    ing = sub.add_parser("ingest")
    ing.add_argument("--data-dir", default=get_settings().data_dir)
    ing.add_argument("--limit", type=int, default=20)
    ing.add_argument("--llm", action="store_true")
    ing.add_argument("--llm-chunks", type=int, default=3)
    ing.add_argument("--shuffle", action="store_true")
    ing.add_argument("--seed", type=int, default=42)
    ing.add_argument("--keep-seed", action="store_true")
    ing.add_argument("--workers", type=int, default=1)
    ing.add_argument("--max-mb", type=float, default=0, help="skip files larger than N MB")
    ing.add_argument(
        "--resume-log", default=str(Path(get_settings().runtime_dir) / "ingest_done.txt")
    )
    ing.set_defaults(func=cmd_ingest)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
