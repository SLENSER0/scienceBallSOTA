"""[DE] Isolated benchmark loader (spec §33.6 reproducibility).

Stands up a fully isolated Kuzu store in its own temp dir, seeds a freshly
generated synthetic corpus, applies corruptions, and returns a context manager
carrying ``(store, manifest)`` plus a reproducibility envelope — **without ever
touching a production graph**. On success the temp dir lives until ``close()``; on
any failure it is torn down before the exception propagates.

SOTA note: because the synthetic generator seeds the graph directly (no ingestion
pipeline, no env-var-selected service), isolation here is simply a throwaway temp
store, far lighter than the ``science_ball`` original's ``MKG_DATA_DIR`` dance.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kg_eval.datasets import corruptions, synthetic
from kg_eval.schemas import DatasetManifest
from kg_retrievers.absence_signals import GENUINE_GAP_AT, POSSIBLE_MISS_AT
from kg_retrievers.graph_store import KuzuGraphStore

_VALID_PROFILES = ("offline", "live-llm")


@dataclass
class BenchmarkContext:
    """Live isolated benchmark store + its ground truth. Safe to close twice."""

    store: KuzuGraphStore
    manifest: DatasetManifest
    profile: str
    prose_extraction_enabled: bool
    provenance: dict[str, Any] = field(default_factory=dict)
    _tmp_dir: str | None = None

    def close(self) -> None:
        if self._tmp_dir is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            self.store.close()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self._tmp_dir = None

    def __enter__(self) -> BenchmarkContext:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[5],
            timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("kg-eval")
    except Exception:
        return "unknown"


def load_synthetic(
    *,
    n_materials: int = 12,
    seed: int = 20260701,
    profile: str = "offline",
    name: str = "synthetic_v1",
) -> BenchmarkContext:
    """Build an isolated, corrupted synthetic corpus and return its context."""
    if profile not in _VALID_PROFILES:
        raise ValueError(f"Unknown/unimplemented benchmark profile: {profile!r}")

    tmp_dir = tempfile.mkdtemp(prefix="kg_bench_")
    try:
        store = KuzuGraphStore(str(Path(tmp_dir) / "g"))
        manifest = synthetic.build_synthetic(
            store, n_materials=n_materials, seed=seed, name=name, profile=profile
        )
        # Realise the 'retracted' reality via the corruption op (idempotent: the
        # generator already retracts, so this is a verified no-op re-run).
        corruptions.retract_cells(store, manifest)
        prose_on = profile != "offline"
        provenance = {
            "git_commit": _git_commit(),
            "package_version": _package_version(),
            "python": sys.version.split()[0],
            "backend": "embedded",
            "profile": profile,
            "prose_extraction_enabled": prose_on,
            "n_materials": n_materials,
            "seed": seed,
            "dataset": name,
            "thresholds": {
                "possible_miss_at": POSSIBLE_MISS_AT,
                "genuine_gap_at": GENUINE_GAP_AT,
            },
        }
        return BenchmarkContext(
            store=store,
            manifest=manifest,
            profile=profile,
            prose_extraction_enabled=prose_on,
            provenance=provenance,
            _tmp_dir=tmp_dir,
        )
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
