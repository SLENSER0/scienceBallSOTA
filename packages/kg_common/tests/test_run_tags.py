"""Tests for run tags — тесты меток прогонов (§9.8)."""

from __future__ import annotations

from kg_common.run_tags import (
    DEFAULT_RUN_TYPE,
    DOC_ID_KEY,
    RUN_TYPE_KEY,
    SCHEDULE_NAME_KEY,
    SOURCE_ID_KEY,
    RunTags,
    build_run_tags,
    filter_runs,
    matches_tags,
)

# --------------------------------------------------------------------------- #
# build_run_tags — spec assertions                                            #
# --------------------------------------------------------------------------- #


def test_doc_id_and_run_type_emitted() -> None:
    result = build_run_tags(doc_id="doc:1", run_type="scheduled")
    assert result["kg/doc_id"] == "doc:1"
    assert result["kg/run_type"] == "scheduled"


def test_schedule_name_uses_dagster_namespace() -> None:
    assert build_run_tags(schedule_name="nightly")["dagster/schedule_name"] == "nightly"


def test_none_fields_are_omitted() -> None:
    assert "kg/source_id" not in build_run_tags(doc_id="doc:1")


def test_run_type_defaults_to_manual() -> None:
    assert build_run_tags()["kg/run_type"] == "manual"
    assert DEFAULT_RUN_TYPE == "manual"


def test_empty_build_only_has_run_type() -> None:
    # Nothing else supplied → the only key is the always-present run_type.
    assert build_run_tags() == {RUN_TYPE_KEY: "manual"}


def test_all_fields_present_when_supplied() -> None:
    result = build_run_tags(
        doc_id="doc:1",
        source_id="src:9",
        ingest_job_id="job:7",
        run_type="scheduled",
        partition_key="2026-07-03",
        schedule_name="nightly",
    )
    assert result == {
        DOC_ID_KEY: "doc:1",
        SOURCE_ID_KEY: "src:9",
        "kg/ingest_job_id": "job:7",
        RUN_TYPE_KEY: "scheduled",
        "dagster/partition": "2026-07-03",
        SCHEDULE_NAME_KEY: "nightly",
    }


def test_values_are_str_coerced() -> None:
    # A non-string source_id is coerced to str in the emitted mapping.
    result = build_run_tags(source_id=42)  # type: ignore[arg-type]
    assert result[SOURCE_ID_KEY] == "42"
    assert isinstance(result[SOURCE_ID_KEY], str)


def test_result_is_plain_str_dict() -> None:
    result = build_run_tags(doc_id="doc:1", partition_key="p")
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())


# --------------------------------------------------------------------------- #
# RunTags record — as_dict parity                                             #
# --------------------------------------------------------------------------- #


def test_run_tags_as_dict_matches_builder() -> None:
    record = RunTags(run_type="scheduled", doc_id="doc:1", schedule_name="nightly")
    assert record.as_dict() == build_run_tags(
        doc_id="doc:1", run_type="scheduled", schedule_name="nightly"
    )


def test_run_tags_is_frozen() -> None:
    import dataclasses

    record = RunTags(doc_id="doc:1")
    try:
        record.doc_id = "doc:2"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RunTags should be frozen")


# --------------------------------------------------------------------------- #
# matches_tags — spec assertions                                              #
# --------------------------------------------------------------------------- #


def test_matches_subset_is_true() -> None:
    assert (
        matches_tags({"kg/doc_id": "d", "kg/run_type": "manual"}, {"kg/run_type": "manual"}) is True
    )


def test_matches_missing_key_is_false() -> None:
    assert matches_tags({"kg/run_type": "manual"}, {"kg/doc_id": "d"}) is False


def test_matches_wrong_value_is_false() -> None:
    assert matches_tags({"kg/run_type": "manual"}, {"kg/run_type": "scheduled"}) is False


def test_empty_query_matches_anything() -> None:
    assert matches_tags({"kg/run_type": "manual"}, {}) is True
    assert matches_tags({}, {}) is True


def test_multi_key_query_needs_all() -> None:
    tags = {"kg/doc_id": "d", "kg/run_type": "manual", "kg/source_id": "s"}
    assert matches_tags(tags, {"kg/doc_id": "d", "kg/source_id": "s"}) is True
    assert matches_tags(tags, {"kg/doc_id": "d", "kg/source_id": "x"}) is False


# --------------------------------------------------------------------------- #
# filter_runs — spec assertion                                                #
# --------------------------------------------------------------------------- #


def test_filter_runs_keeps_only_matches() -> None:
    runs = [{"kg/run_type": "scheduled"}, {"kg/run_type": "manual"}]
    kept = filter_runs(runs, {"kg/run_type": "manual"})
    assert len(kept) == 1
    assert kept[0] == {"kg/run_type": "manual"}


def test_filter_runs_preserves_order_and_identity() -> None:
    a = {"kg/run_type": "manual", "kg/doc_id": "1"}
    b = {"kg/run_type": "manual", "kg/doc_id": "2"}
    c = {"kg/run_type": "scheduled", "kg/doc_id": "3"}
    kept = filter_runs([a, b, c], {"kg/run_type": "manual"})
    assert kept == [a, b]
    assert kept[0] is a and kept[1] is b


def test_filter_runs_empty_query_keeps_all() -> None:
    runs = [{"kg/run_type": "manual"}, {"kg/run_type": "scheduled"}]
    assert filter_runs(runs, {}) == runs


def test_filter_runs_no_match_is_empty() -> None:
    runs = [{"kg/run_type": "manual"}, {"kg/run_type": "scheduled"}]
    assert filter_runs(runs, {"kg/doc_id": "missing"}) == []
