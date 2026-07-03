"""Technology-readiness (TRL) scoring over a temp Kuzu store (§24.8).

Hand-checkable end-to-end: each test builds a fresh embedded ``KuzuGraphStore``, upserts
``TechnologySolution`` nodes with a maturity signal plus linked measurements / evidence
(store API only — no seed/graph_store files are touched), and asserts the assigned TRL
lands in the band the spec prescribes (industrial 8-9, pilot 6-7, lab 3-4, concept 1-2).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.tech_readiness import ReadinessAssessment, assess_readiness


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _solution(store: KuzuGraphStore, sid: str, **props: object) -> None:
    store.upsert_node(sid, "TechnologySolution", **props)


def _measurement(store: KuzuGraphStore, mid: str, solution_id: str, **props: object) -> None:
    store.upsert_node(mid, "Measurement", **props)
    store.upsert_edge(mid, solution_id, "ABOUT_REGIME", confidence=0.8)


def _evidence(store: KuzuGraphStore, eid: str, solution_id: str, **props: object) -> None:
    store.upsert_node(eid, "Evidence", **props)
    store.upsert_edge(solution_id, eid, "SUPPORTED_BY", confidence=0.8)


def test_industrial_practice_high_trl(store: KuzuGraphStore) -> None:
    _solution(store, "sol:ind", name="Промышленная сероочистка", practice_type="industrial")
    _measurement(
        store,
        "m:ind:1",
        "sol:ind",
        property_name="removal_efficiency",
        value_normalized=95.0,
        evidence_strength="peer_reviewed",
    )
    _evidence(
        store,
        "ev:ind:1",
        "sol:ind",
        text="Промышленная эксплуатация установки на заводе",
        evidence_strength="peer_reviewed",
    )
    a = assess_readiness(store, "sol:ind")
    assert a.trl >= 8  # industrial band
    assert a.trl == 9  # strong (peer-reviewed) evidence bumps to the top of the band
    assert a.has_industrial is True
    assert a.has_pilot is False
    assert a.evidence_count == 2  # one measurement + one evidence node


def test_pilot_solution_mid_trl(store: KuzuGraphStore) -> None:
    _solution(store, "sol:pilot", name="Пилотная установка", practice_type="pilot")
    _measurement(store, "m:pilot:1", "sol:pilot", property_name="throughput", value_normalized=10.0)
    a = assess_readiness(store, "sol:pilot")
    assert a.trl in (6, 7)  # pilot band
    assert a.has_pilot is True
    assert a.has_industrial is False
    assert a.evidence_count == 1


def test_lab_only_low_trl(store: KuzuGraphStore) -> None:
    _solution(store, "sol:lab", name="Лабораторная методика", practice_type="lab")
    _measurement(store, "m:lab:1", "sol:lab", property_name="yield", value_normalized=80.0)
    a = assess_readiness(store, "sol:lab")
    assert a.trl in (3, 4)  # lab band
    assert a.has_pilot is False
    assert a.has_industrial is False


def test_concept_solution_lowest_trl(store: KuzuGraphStore) -> None:
    _solution(store, "sol:concept", name="Концепция процесса", practice_type="concept")
    a = assess_readiness(store, "sol:concept")
    assert a.trl in (1, 2)  # concept band
    assert a.has_pilot is False
    assert a.has_industrial is False


def test_no_evidence_low_trl_with_rationale(store: KuzuGraphStore) -> None:
    # no maturity signal and no linked measurements/evidence -> minimal TRL + a rationale
    _solution(store, "sol:bare", name="Deep well injection")
    a = assess_readiness(store, "sol:bare")
    assert a.trl <= 2
    assert a.evidence_count == 0
    assert a.rationale
    assert "evidence" in a.rationale.lower()


def test_evidence_bump_industrial(store: KuzuGraphStore) -> None:
    # industrial + strong (peer-reviewed) evidence -> top of the band (9)
    _solution(store, "sol:i9", name="A", practice_type="industrial")
    _evidence(store, "ev:i9", "sol:i9", text="завод", evidence_strength="peer_reviewed")
    strong = assess_readiness(store, "sol:i9")
    assert strong.trl == 9
    assert strong.evidence_count == 1
    # industrial with no supporting evidence -> base of the band (8)
    _solution(store, "sol:i8", name="B", practice_type="industrial")
    weak = assess_readiness(store, "sol:i8")
    assert weak.trl == 8
    assert weak.evidence_count == 0


def test_both_pilot_and_industrial_flags(store: KuzuGraphStore) -> None:
    _solution(store, "sol:both", name="Промышленное решение", practice_type="industrial")
    # an evidence note describing an earlier pilot -> both stages are detected
    _evidence(
        store,
        "ev:pilot",
        "sol:both",
        text="Ранее испытано на пилотной установке (pilot demonstration)",
    )
    a = assess_readiness(store, "sol:both")
    assert a.has_industrial is True
    assert a.has_pilot is True
    assert a.trl >= 8  # the highest reached stage (industrial) fixes the band


def test_trl_always_bounded(store: KuzuGraphStore) -> None:
    scenarios: list[dict[str, object]] = [
        {"practice_type": "industrial"},
        {"practice_type": "pilot"},
        {"practice_type": "lab"},
        {"practice_type": "concept"},
        {"practice_type": "some_unknown_stage"},
        {},
    ]
    for i, props in enumerate(scenarios):
        sid = f"sol:b:{i}"
        _solution(store, sid, name=f"S{i}", **props)
        a = assess_readiness(store, sid)
        assert 1 <= a.trl <= 9


def test_unknown_solution_graceful(store: KuzuGraphStore) -> None:
    a = assess_readiness(store, "sol:does-not-exist")
    assert isinstance(a, ReadinessAssessment)
    assert 1 <= a.trl <= 9
    assert a.evidence_count == 0
    assert a.has_pilot is False
    assert a.has_industrial is False
    assert "unknown" in a.rationale.lower()


def test_as_dict_shape(store: KuzuGraphStore) -> None:
    _solution(store, "sol:d", name="X", practice_type="pilot")
    a = assess_readiness(store, "sol:d")
    d = a.as_dict()
    assert set(d) == {
        "solution_id",
        "trl",
        "evidence_count",
        "has_pilot",
        "has_industrial",
        "rationale",
    }
    assert d["solution_id"] == "sol:d"
    assert d["trl"] == a.trl
    # the payload is JSON-serialisable (transport-ready)
    assert json.loads(json.dumps(d))["trl"] == a.trl
