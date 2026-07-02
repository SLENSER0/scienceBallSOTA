"""Dagster orchestration definitions load + wire correctly (§9/§10).

infra/dagster/definitions.py lives outside the package tree, so it is loaded by
path here. This guards against the regression where `from __future__ import
annotations` stringized the asset `context` type and Dagster rejected the whole
Definitions at import (DagsterInvalidDefinitionError).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("dagster")

DEFS_PATH = Path(__file__).resolve().parents[3] / "infra" / "dagster" / "definitions.py"


def _load_defs():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("kg_dagster_defs", DEFS_PATH)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.defs


def test_definitions_resolve_all_assets() -> None:
    ag = _load_defs().resolve_asset_graph()
    keys = {k.to_user_string() for k in ag.get_all_asset_keys()}
    assert keys == {"corpus_graph", "search_index", "gap_scan"}


def test_downstream_assets_depend_on_corpus_graph() -> None:
    from dagster import AssetKey

    ag = _load_defs().resolve_asset_graph()
    for downstream in ("search_index", "gap_scan"):
        parents = ag.get(AssetKey(downstream)).parent_keys
        assert AssetKey("corpus_graph") in parents


def test_weekly_refresh_schedule() -> None:
    sched = _load_defs().resolve_schedule_def("corpus_refresh_schedule")
    assert sched.cron_schedule == "0 3 * * 1"  # Monday 03:00


def test_refresh_job_resolves() -> None:
    job = _load_defs().resolve_job_def("corpus_refresh")
    assert job.name == "corpus_refresh"
