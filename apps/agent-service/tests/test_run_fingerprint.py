"""Тесты §13.23 run fingerprint / hand-checkable reproducibility tests (§7.1)."""

from __future__ import annotations

import re

from agent_service.run_fingerprint import (
    RunFingerprint,
    compute_fingerprint,
    same_run,
)

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


def _state() -> dict:
    """Базовое состояние агента / a base agent state for a run."""
    return {
        "normalized_question": "какие материалы твёрже стали 45",
        "intent": "compare_materials",
        "query_plan": {
            "mode": "hybrid",
            "top_k": 10,
            "filters": {"quantity": "hardness"},
        },
        "cypher_queries": [
            "MATCH (m:Material) RETURN m",
            "MATCH (m:Material)-[:HAS]->(p:Property) RETURN p",
        ],
    }


def test_identical_inputs_identical_digest() -> None:
    """(1) один вход → один digest / identical state+prompt+seed → identical digest."""
    a = compute_fingerprint(_state(), "prompt-v1", 42)
    b = compute_fingerprint(_state(), "prompt-v1", 42)
    assert a.digest == b.digest
    assert a.plan_hash == b.plan_hash
    assert a.cypher_hash == b.cypher_hash


def test_digest_is_64_lower_hex() -> None:
    """(2) digest = 64 строчных hex / digest is 64 lowercase hex chars."""
    fp = compute_fingerprint(_state(), "prompt-v1", 42)
    assert _HEX64.match(fp.digest)
    assert _HEX64.match(fp.plan_hash)
    assert _HEX64.match(fp.cypher_hash)


def test_reorder_cypher_stable() -> None:
    """(3) перестановка cypher не меняет hash/digest / reorder is a no-op (sorted)."""
    base = compute_fingerprint(_state(), "prompt-v1", 42)
    reordered = _state()
    reordered["cypher_queries"] = list(reversed(reordered["cypher_queries"]))
    fp = compute_fingerprint(reordered, "prompt-v1", 42)
    assert fp.cypher_hash == base.cypher_hash
    assert fp.digest == base.digest


def test_seed_changes_digest() -> None:
    """(4) смена seed меняет digest / changing seed changes digest."""
    a = compute_fingerprint(_state(), "prompt-v1", 42)
    b = compute_fingerprint(_state(), "prompt-v1", 43)
    assert a.digest != b.digest


def test_plan_value_change_changes_plan_hash_and_digest() -> None:
    """(5) изменение значения в query_plan меняет plan_hash и digest."""
    base = compute_fingerprint(_state(), "prompt-v1", 42)
    mutated = _state()
    mutated["query_plan"]["top_k"] = 25
    fp = compute_fingerprint(mutated, "prompt-v1", 42)
    assert fp.plan_hash != base.plan_hash
    assert fp.digest != base.digest
    # cypher untouched → its hash is unchanged / cypher-хеш не меняется.
    assert fp.cypher_hash == base.cypher_hash


def test_same_run_true_and_false() -> None:
    """(6) same_run: True для равных, False при разных intent."""
    a = compute_fingerprint(_state(), "prompt-v1", 42)
    b = compute_fingerprint(_state(), "prompt-v1", 42)
    assert same_run(a, b) is True

    other = _state()
    other["intent"] = "find_labs"
    c = compute_fingerprint(other, "prompt-v1", 42)
    assert c.intent != a.intent
    assert same_run(a, c) is False


def test_as_dict_exposes_all_six_fields() -> None:
    """(7) as_dict отдаёт все шесть полей / as_dict exposes all six fields."""
    fp = compute_fingerprint(_state(), "prompt-v1", 42)
    d = fp.as_dict()
    assert set(d) == {
        "intent",
        "prompt_version",
        "seed",
        "plan_hash",
        "cypher_hash",
        "digest",
    }
    assert d["intent"] == "compare_materials"
    assert d["prompt_version"] == "prompt-v1"
    assert d["seed"] == 42
    assert d["digest"] == fp.digest


def test_frozen_dataclass_immutable() -> None:
    """Frozen: попытка мутации падает / mutation raises on the frozen dataclass."""
    fp = compute_fingerprint(_state(), "prompt-v1", 42)
    assert isinstance(fp, RunFingerprint)
    try:
        fp.seed = 7  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("RunFingerprint must be immutable")
