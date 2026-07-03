"""Tests for inter-configuration absence verdict agreement (§25.15).

Hand-checkable cases: perfect agreement, ignored A-only keys, a single genuine flip,
3-of-4 agreement, the degenerate ``1 - pe == 0`` branch, empty overlap, and dict shape.
"""

from __future__ import annotations

from kg_eval.absence_verdict_agreement import VerdictAgreement, verdict_agreement


def _cell(material_id: str, property_name: str, verdict: str) -> dict:
    """Build a minimal absence-map cell (компактная ячейка absence-карты)."""
    return {
        "material_id": material_id,
        "property_name": property_name,
        "absence_verdict": verdict,
    }


def test_identical_five_cells_perfect_agreement() -> None:
    """Пять совпадающих ячеек: raw_agreement == 1.0 и cohen_kappa == 1.0."""
    cells = [
        _cell(f"m{i}", "band_gap", "genuine_gap" if i % 2 else "possible_miss") for i in range(5)
    ]
    result = verdict_agreement(cells, cells)
    assert result.n == 5
    assert result.n_agree == 5
    assert result.raw_agreement == 1.0
    assert result.cohen_kappa == 1.0


def test_a_only_key_ignored() -> None:
    """Ключ, присутствующий только в A, игнорируется — n считает только общие ячейки."""
    cells_a = [_cell("m1", "band_gap", "genuine_gap"), _cell("m2", "density", "abstain")]
    cells_b = [_cell("m1", "band_gap", "genuine_gap")]
    result = verdict_agreement(cells_a, cells_b)
    assert result.n == 1
    assert result.n_agree == 1
    assert result.raw_agreement == 1.0


def test_single_flip_recorded() -> None:
    """Один переход genuine_gap->possible_miss фиксируется во flip_matrix."""
    cells_a = [_cell("m1", "band_gap", "genuine_gap")]
    cells_b = [_cell("m1", "band_gap", "possible_miss")]
    result = verdict_agreement(cells_a, cells_b)
    assert result.n == 1
    assert result.n_agree == 0
    assert result.flip_matrix["genuine_gap->possible_miss"] == 1


def test_three_of_four_agree() -> None:
    """Совпадение 3 из 4 общих ячеек даёт raw_agreement == 0.75."""
    cells_a = [
        _cell("m1", "band_gap", "genuine_gap"),
        _cell("m2", "band_gap", "possible_miss"),
        _cell("m3", "band_gap", "retracted"),
        _cell("m4", "band_gap", "abstain"),
    ]
    cells_b = [
        _cell("m1", "band_gap", "genuine_gap"),
        _cell("m2", "band_gap", "possible_miss"),
        _cell("m3", "band_gap", "retracted"),
        _cell("m4", "band_gap", "genuine_gap"),
    ]
    result = verdict_agreement(cells_a, cells_b)
    assert result.n == 4
    assert result.n_agree == 3
    assert result.raw_agreement == 0.75


def test_all_same_verdict_kappa_one() -> None:
    """Одинаковый verdict со всех сторон (1 - pe == 0) даёт cohen_kappa == 1.0."""
    cells_a = [_cell(f"m{i}", "band_gap", "genuine_gap") for i in range(3)]
    cells_b = [_cell(f"m{i}", "band_gap", "genuine_gap") for i in range(3)]
    result = verdict_agreement(cells_a, cells_b)
    assert result.n == 3
    assert result.raw_agreement == 1.0
    assert result.cohen_kappa == 1.0


def test_no_overlap() -> None:
    """Отсутствие общих ключей: n == 0 и cohen_kappa == 0.0."""
    cells_a = [_cell("m1", "band_gap", "genuine_gap")]
    cells_b = [_cell("m2", "density", "abstain")]
    result = verdict_agreement(cells_a, cells_b)
    assert result.n == 0
    assert result.cohen_kappa == 0.0
    assert result.flip_matrix == {}


def test_as_dict_flip_matrix_is_dict() -> None:
    """as_dict()['flip_matrix'] — обычный dict; тип результата — VerdictAgreement."""
    cells_a = [_cell("m1", "band_gap", "genuine_gap")]
    cells_b = [_cell("m1", "band_gap", "possible_miss")]
    result = verdict_agreement(cells_a, cells_b)
    assert isinstance(result, VerdictAgreement)
    payload = result.as_dict()
    assert isinstance(payload["flip_matrix"], dict)
    assert payload["flip_matrix"]["genuine_gap->possible_miss"] == 1
