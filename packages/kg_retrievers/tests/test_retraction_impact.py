"""Tests for retraction evidence-collapse impact — тесты §25.12."""

from __future__ import annotations

from kg_retrievers.retraction_impact import (
    CellImpact,
    RetractionImpact,
    analyze_retraction_impact,
)


def test_cell_all_retracted_collapses() -> None:
    """(1) both measurements retracted → collapsed True, active == 0."""
    result = analyze_retraction_impact(
        [
            {"material_id": "Fe", "property_name": "Tc", "retracted": True},
            {"material_id": "Fe", "property_name": "Tc", "retracted": True},
        ]
    )
    assert len(result.cells) == 1
    cell = result.cells[0]
    assert cell.total == 2
    assert cell.retracted == 2
    assert cell.active == 0
    assert cell.collapsed is True
    assert result.n_collapsed == 1
    assert result.n_partial == 0
    assert result.affected_materials == ["Fe"]


def test_cell_mixed_is_partial_not_collapsed() -> None:
    """(2) one active + one retracted → not collapsed, counts toward n_partial."""
    result = analyze_retraction_impact(
        [
            {"material_id": "Cu", "property_name": "rho", "retracted": False},
            {"material_id": "Cu", "property_name": "rho", "retracted": True},
        ]
    )
    cell = result.cells[0]
    assert cell.total == 2
    assert cell.active == 1
    assert cell.retracted == 1
    assert cell.collapsed is False
    assert result.n_collapsed == 0
    assert result.n_partial == 1
    assert result.affected_materials == ["Cu"]


def test_cell_all_active_neither_collapsed_nor_partial() -> None:
    """(3) all-active cell → neither collapsed nor partial, unaffected."""
    result = analyze_retraction_impact(
        [
            {"material_id": "Al", "property_name": "E", "retracted": False},
            {"material_id": "Al", "property_name": "E", "retracted": False},
        ]
    )
    cell = result.cells[0]
    assert cell.active == 2
    assert cell.retracted == 0
    assert cell.collapsed is False
    assert result.n_collapsed == 0
    assert result.n_partial == 0
    assert result.affected_materials == []


def test_n_collapsed_counts_collapsed_cells() -> None:
    """(4) n_collapsed counts every fully-collapsed cell across materials."""
    result = analyze_retraction_impact(
        [
            {"material_id": "Fe", "property_name": "Tc", "retracted": True},
            {"material_id": "Ni", "property_name": "Tc", "retracted": True},
            {"material_id": "Cu", "property_name": "rho", "retracted": False},
            {"material_id": "Cu", "property_name": "rho", "retracted": True},
        ]
    )
    assert result.n_collapsed == 2
    assert result.n_partial == 1
    collapsed = {c.material_id for c in result.cells if c.collapsed}
    assert collapsed == {"Fe", "Ni"}


def test_affected_materials_deduped_and_sorted() -> None:
    """(5) affected_materials lists materials with any retraction, deduped + sorted."""
    result = analyze_retraction_impact(
        [
            {"material_id": "Zn", "property_name": "a", "retracted": True},
            {"material_id": "Zn", "property_name": "b", "retracted": True},
            {"material_id": "Ag", "property_name": "a", "retracted": False},
            {"material_id": "Ag", "property_name": "a", "retracted": True},
            {"material_id": "Au", "property_name": "a", "retracted": False},
        ]
    )
    assert result.affected_materials == ["Ag", "Zn"]


def test_empty_input() -> None:
    """(6) empty input → no cells, zero counters, no affected materials."""
    result = analyze_retraction_impact([])
    assert result.cells == []
    assert result.n_collapsed == 0
    assert result.n_partial == 0
    assert result.affected_materials == []


def test_frozen_and_as_dict_roundtrip() -> None:
    """Dataclasses are frozen and expose faithful as_dict() views."""
    result = analyze_retraction_impact(
        [{"material_id": "Fe", "property_name": "Tc", "retracted": True}]
    )
    assert isinstance(result, RetractionImpact)
    cell = result.cells[0]
    assert isinstance(cell, CellImpact)
    import dataclasses

    with_error = False
    try:
        cell.total = 5  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        with_error = True
    assert with_error

    assert cell.as_dict() == {
        "material_id": "Fe",
        "property_name": "Tc",
        "total": 1,
        "active": 0,
        "retracted": 1,
        "collapsed": True,
    }
    assert result.as_dict() == {
        "cells": [cell.as_dict()],
        "n_collapsed": 1,
        "n_partial": 0,
        "affected_materials": ["Fe"],
    }
