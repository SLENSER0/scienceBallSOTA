"""Parallel agent fan-out with HONEST streaming progress.

Many product features run one LLM/agent call per item (per candidate technology, per
knowledge gap, per benchmark system…). This helper runs them concurrently on a bounded
pool and yields a progress event the instant EACH one finishes — so the UI can draw a
progress bar that reflects real completions (done/total), never a fake timer.

Usage:
    for ev, data in stream_fanout(items, worker, max_workers=10, label="gap"):
        # ev in {"start","item","done"}; data carries done/total (+ result on "item")

The bar is honest by construction: `done` only advances when a worker's future resolves.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from kg_common import get_logger

_log = get_logger("fanout")

# Product default: fan out up to 10 agents at once (user-requested). Bounded so a big
# batch can't exhaust the OpenRouter connection pool.
DEFAULT_MAX_WORKERS = 10


def stream_fanout(
    items: Sequence[Any],
    worker: Callable[[Any], Any],
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
    label: str = "agent",
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (event, data) as each parallel worker finishes.

    Events: ``start`` {total,label,workers} → ``item`` {done,total,result} per completion
    → ``done`` {total,done}. A worker that raises yields ``result={"error": ...}`` and
    still advances the counter (the run never stalls on one failure).
    """
    total = len(items)
    workers = max(1, min(max_workers, total or 1))
    yield "start", {"total": total, "label": label, "workers": workers}
    if total == 0:
        yield "done", {"total": 0, "done": 0}
        return

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, it) for it in items]
        for fut in as_completed(futures):
            done += 1
            try:
                result = fut.result()
            except Exception as exc:  # one bad item must not sink the whole run
                _log.warning("fanout.worker_failed", label=label, error=str(exc)[:120])
                result = {"error": str(exc)[:150]}
            yield "item", {"done": done, "total": total, "result": result}
    yield "done", {"total": total, "done": done}


def run_fanout(
    items: Sequence[Any],
    worker: Callable[[Any], Any],
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[Any]:
    """Non-streaming variant — run all workers concurrently, return results (order-agnostic)."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(items)))) as pool:
        return list(pool.map(worker, items))
