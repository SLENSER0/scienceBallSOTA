"""Tests for catalog domains grouped by Lab — тесты доменов по лабам (§10.6)."""

from __future__ import annotations

from kg_common.metadata_domains import (
    Domain,
    assign,
    build_domains,
    domain_id_for,
    orphan_sources,
)


def test_domain_id_for_slugifies_lab_id() -> None:
    assert domain_id_for("Lab A") == "domain:lab-a"
    assert domain_id_for("L1") == "domain:l1"


def test_build_domains_collects_source_ids_sorted() -> None:
    rows = [
        {"source_id": "s2", "lab_id": "L1", "lab_name": "L1"},
        {"source_id": "s1", "lab_id": "L1", "lab_name": "L1"},
    ]
    domains = build_domains(rows)
    assert len(domains) == 1
    assert domains[0].source_ids == ("s1", "s2")
    assert domains[0].domain_id == "domain:l1"
    assert domains[0].lab_id == "L1"


def test_build_domains_groups_two_labs_into_two_domains() -> None:
    rows = [
        {"source_id": "s1", "lab_id": "L1", "lab_name": "Lab One"},
        {"source_id": "s2", "lab_id": "L2", "lab_name": "Lab Two"},
    ]
    domains = build_domains(rows)
    assert len(domains) == 2
    assert [d.domain_id for d in domains] == ["domain:l1", "domain:l2"]
    assert domains[0].name == "Lab One"
    assert domains[1].source_ids == ("s2",)


def test_build_domains_output_sorted_by_domain_id() -> None:
    rows = [
        {"source_id": "sz", "lab_id": "Zeta", "lab_name": "Zeta"},
        {"source_id": "sa", "lab_id": "Alpha", "lab_name": "Alpha"},
    ]
    domains = build_domains(rows)
    ids = [d.domain_id for d in domains]
    assert ids == sorted(ids)
    assert ids == ["domain:alpha", "domain:zeta"]


def test_build_domains_excludes_rows_missing_lab_id() -> None:
    rows = [
        {"source_id": "s1", "lab_id": "L1", "lab_name": "L1"},
        {"source_id": "s3"},
        {"source_id": "s4", "lab_id": "", "lab_name": ""},
    ]
    domains = build_domains(rows)
    assert len(domains) == 1
    assert domains[0].source_ids == ("s1",)


def test_orphan_sources_lists_sources_without_lab_id() -> None:
    assert orphan_sources([{"source_id": "s3"}]) == ["s3"]
    rows = [
        {"source_id": "s1", "lab_id": "L1", "lab_name": "L1"},
        {"source_id": "s3"},
        {"source_id": "s4", "lab_id": ""},
    ]
    assert orphan_sources(rows) == ["s3", "s4"]


def test_assign_is_idempotent_for_same_source() -> None:
    domains = assign([], "s1", "L1", "Lab One")
    assert len(domains) == 1
    assert domains[0].source_ids == ("s1",)
    again = assign(domains, "s1", "L1", "Lab One")
    assert len(again) == 1
    assert again[0].source_ids == ("s1",)


def test_assign_adds_new_source_and_new_domain() -> None:
    domains = assign([], "s1", "L1", "Lab One")
    domains = assign(domains, "s2", "L1", "Lab One")
    assert domains[0].source_ids == ("s1", "s2")
    domains = assign(domains, "s3", "L2", "Lab Two")
    assert [d.domain_id for d in domains] == ["domain:l1", "domain:l2"]
    assert domains[1].source_ids == ("s3",)


def test_domain_as_dict_source_ids_is_a_list() -> None:
    d = Domain("domain:l1", "L1", "Lab One", ("s1", "s2"))
    dumped = d.as_dict()
    assert isinstance(dumped["source_ids"], list)
    assert dumped == {
        "domain_id": "domain:l1",
        "lab_id": "L1",
        "name": "Lab One",
        "source_ids": ["s1", "s2"],
    }


def test_domain_is_frozen() -> None:
    d = Domain("domain:l1", "L1", "Lab One", ("s1",))
    try:
        d.name = "other"  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ in {"FrozenInstanceError", "AttributeError"}
    else:
        raise AssertionError("Domain should be immutable")
