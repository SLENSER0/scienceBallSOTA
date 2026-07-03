"""Tests for the temper-designation decoder (§6.4 / §6.5)."""

from __future__ import annotations

from kg_extractors.temper_decode import TemperMeaning, decode_temper


def test_t6_solution_then_artificial_aging() -> None:
    assert decode_temper("T6").operations == ("solution_treatment", "artificial_aging")


def test_t4_solution_then_natural_aging() -> None:
    assert decode_temper("T4").operations == ("solution_treatment", "natural_aging")


def test_o_is_annealing() -> None:
    assert decode_temper("O").operations == ("annealing",)


def test_t651_appends_stress_relief_after_t6_ops() -> None:
    ops = decode_temper("T651").operations
    assert ops == ("solution_treatment", "artificial_aging", "stress_relief")
    assert len(ops) == 3
    # stress_relief comes AFTER the two T6 operations.
    assert ops[:2] == decode_temper("T6").operations
    assert ops[-1] == "stress_relief"


def test_h14_is_strain_hardening() -> None:
    assert decode_temper("H14").operations == ("strain_hardening",)


def test_f_is_as_fabricated_no_operations() -> None:
    meaning = decode_temper("F")
    assert meaning is not None
    assert "as-fabricated" in meaning.description
    assert meaning.operations == ()


def test_unknown_temper_is_none() -> None:
    assert decode_temper("Z9") is None


def test_as_dict_operations_is_a_list() -> None:
    d = decode_temper("T6").as_dict()
    assert isinstance(d["operations"], list)
    assert d["operations"] == ["solution_treatment", "artificial_aging"]
    assert d["code"] == "T6"


def test_w_is_solution_treatment() -> None:
    assert decode_temper("W").operations == ("solution_treatment",)


def test_t3_full_sequence_solution_strain_natural() -> None:
    assert decode_temper("T3").operations == (
        "solution_treatment",
        "strain_hardening",
        "natural_aging",
    )


def test_case_and_whitespace_insensitive() -> None:
    assert decode_temper("  t6  ").operations == decode_temper("T6").operations


def test_empty_and_none_like_return_none() -> None:
    assert decode_temper("") is None
    assert decode_temper("   ") is None


def test_temper_meaning_is_frozen() -> None:
    m = decode_temper("T6")
    assert isinstance(m, TemperMeaning)
    try:
        m.code = "X"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - dataclass(frozen=True) must forbid assignment
        raise AssertionError("TemperMeaning must be frozen")


def test_h2_adds_partial_annealing() -> None:
    assert decode_temper("H24").operations == ("strain_hardening", "annealing")
