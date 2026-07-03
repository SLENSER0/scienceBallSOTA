"""Practice-geography analysis over a temp Kuzu store (§24.23).

Hand-checkable end-to-end: each test builds a fresh embedded ``KuzuGraphStore``, upserts
a solution node plus linked ``Country`` / ``Geography`` nodes (store API only — no
seed/graph_store files are touched), and asserts :func:`geography_for` returns the exact
de-duplicated, sorted country / region / climate-zone / practice-type lists prescribed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.practice_geography import PracticeGeography, geography_for


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _solution(store: KuzuGraphStore, sid: str, **props: object) -> None:
    store.upsert_node(sid, "TechnologySolution", **props)


def _country(store: KuzuGraphStore, cid: str, solution_id: str, **props: object) -> None:
    store.upsert_node(cid, "Country", **props)
    store.upsert_edge(solution_id, cid, "APPLIED_IN", confidence=0.9)


def _geography(store: KuzuGraphStore, gid: str, solution_id: str, **props: object) -> None:
    store.upsert_node(gid, "Geography", **props)
    store.upsert_edge(solution_id, gid, "PRACTICED_IN", confidence=0.9)


def test_countries_listed(store: KuzuGraphStore) -> None:
    _solution(store, "sol:c", country="russia", practice_type="russia")
    _country(store, "geo:ca", "sol:c", name="canada")
    _country(store, "geo:no", "sol:c", name="norway")
    pg = geography_for(store, "sol:c")
    # own column "russia" + two linked Country names, sorted, no dupes.
    assert pg.countries == ["canada", "norway", "russia"]
    assert pg.solution_id == "sol:c"


def test_regions_listed(store: KuzuGraphStore) -> None:
    _solution(store, "sol:r", region="siberia")
    _geography(store, "geo:g1", "sol:r", region="kola peninsula")
    _geography(store, "geo:g2", "sol:r", region="ural")
    pg = geography_for(store, "sol:r")
    assert pg.regions == ["kola peninsula", "siberia", "ural"]
    assert pg.countries == []  # no country stated anywhere


def test_practice_types(store: KuzuGraphStore) -> None:
    _solution(store, "sol:p", practice_type="russia")
    _country(store, "geo:x", "sol:p", name="canada", practice_type="foreign")
    pg = geography_for(store, "sol:p")
    assert pg.practice_types == ["foreign", "russia"]
    assert pg.countries == ["canada"]


def test_climate_zones(store: KuzuGraphStore) -> None:
    _solution(store, "sol:cz", climate_zone="cold")
    _geography(store, "geo:t", "sol:cz", region="taimyr", climate_zone="arctic")
    _country(store, "geo:ru", "sol:cz", name="russia", climate_zone="continental")
    pg = geography_for(store, "sol:cz")
    assert pg.climate_zones == ["arctic", "cold", "continental"]
    assert pg.regions == ["taimyr"]
    assert pg.countries == ["russia"]


def test_unknown_solution_empty(store: KuzuGraphStore) -> None:
    pg = geography_for(store, "sol:missing")
    assert isinstance(pg, PracticeGeography)
    assert pg.solution_id == "sol:missing"
    assert pg.countries == []
    assert pg.regions == []
    assert pg.climate_zones == []
    assert pg.practice_types == []


def test_dedup_and_non_geo_ignored(store: KuzuGraphStore) -> None:
    _solution(store, "sol:d", country="russia")
    # A linked Country repeating the solution's own country -> de-duplicated to one.
    _country(store, "geo:ru", "sol:d", name="russia")
    # A linked non-geo node (Paper) carrying a country must be ignored.
    store.upsert_node("pap:1", "Paper", country="usa", region="texas")
    store.upsert_edge("sol:d", "pap:1", "SUPPORTED_BY", confidence=0.8)
    pg = geography_for(store, "sol:d")
    assert pg.countries == ["russia"]  # deduped, Paper's "usa" excluded
    assert pg.regions == []  # Paper's "texas" excluded (not Country/Geography)


def test_as_dict(store: KuzuGraphStore) -> None:
    _solution(
        store, "sol:a", country="russia", region="kola", climate_zone="cold", practice_type="russia"
    )
    _country(store, "geo:ca", "sol:a", name="canada", practice_type="foreign")
    _geography(store, "geo:arc", "sol:a", region="arctic zone", climate_zone="arctic")
    pg = geography_for(store, "sol:a")
    assert pg.as_dict() == {
        "solution_id": "sol:a",
        "countries": ["canada", "russia"],
        "regions": ["arctic zone", "kola"],
        "climate_zones": ["arctic", "cold"],
        "practice_types": ["foreign", "russia"],
    }
