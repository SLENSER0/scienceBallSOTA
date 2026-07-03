"""Parameterized read-only Cypher template library (§12.10).

Hand-checked: every template is guard-clean, LIMIT-bounded, and parameterized;
render binds params and refuses missing / unexpected / unknown; an injected
mutating clause is still caught by the guard.
"""

from __future__ import annotations

import re

import pytest
from graph_service.cypher_guard import CypherGuardError, guard_read_query
from graph_service.cypher_templates import (
    TEMPLATES,
    CypherTemplate,
    get_template,
    list_templates,
    render,
)

EXPECTED_PARAMS = {
    "material_regime_property": ("material_id", "property_id", "regime_id"),
    "entity_neighbors": ("entity_id",),
    "shortest_path": ("source_id", "target_id"),
    "measurements_for_material": ("material_id",),
}
_PLACEHOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def test_registry_has_the_four_named_templates() -> None:
    names = list_templates()
    assert set(names) >= set(EXPECTED_PARAMS)
    assert len(names) >= 4
    assert names  # non-empty (реестр не пуст)


@pytest.mark.parametrize("name", sorted(EXPECTED_PARAMS))
def test_every_template_is_guard_clean(name: str) -> None:
    hardened = guard_read_query(TEMPLATES[name].cypher)  # must not raise
    # guard preserves the template's own literal LIMIT (no double LIMIT appended)
    assert hardened.count("LIMIT") == 1
    assert re.search(r"\bLIMIT \d+\s*$", hardened)


@pytest.mark.parametrize("name", sorted(EXPECTED_PARAMS))
def test_every_template_has_a_literal_limit(name: str) -> None:
    assert re.search(r"\bLIMIT \d+\b", TEMPLATES[name].cypher)


@pytest.mark.parametrize("name", sorted(EXPECTED_PARAMS))
def test_params_tuple_matches_placeholders(name: str) -> None:
    template = TEMPLATES[name]
    parsed = tuple(dict.fromkeys(_PLACEHOLDER.findall(template.cypher)))
    assert template.params == parsed
    assert template.params == EXPECTED_PARAMS[name]


def test_render_fills_params_and_keeps_them_separate() -> None:
    cypher, params = render(
        "material_regime_property",
        material_id="mat-1",
        property_id="prop-hardness",
        regime_id="reg-T6",
    )
    # params are bound, NOT interpolated: placeholders survive in the query text
    assert "$material_id" in cypher and "$property_id" in cypher and "$regime_id" in cypher
    assert params == {
        "material_id": "mat-1",
        "property_id": "prop-hardness",
        "regime_id": "reg-T6",
    }
    assert cypher.strip().endswith("LIMIT 200")


def test_render_single_param_template() -> None:
    cypher, params = render("entity_neighbors", entity_id="ent-42")
    assert params == {"entity_id": "ent-42"}
    assert cypher.count("LIMIT") == 1
    assert cypher.strip().endswith("LIMIT 100")


def test_render_missing_param_raises() -> None:
    with pytest.raises(ValueError, match="missing params"):
        render("material_regime_property", material_id="mat-1")


def test_render_unexpected_param_raises() -> None:
    with pytest.raises(ValueError, match="unexpected params"):
        render("entity_neighbors", entity_id="ent-1", bogus="x")


def test_render_unknown_template_raises() -> None:
    with pytest.raises(KeyError, match="unknown template"):
        render("delete_everything", x=1)
    with pytest.raises(KeyError, match="unknown template"):
        get_template("nope")


def test_injected_mutating_clause_is_rejected_by_guard() -> None:
    # A tampered template body with an appended write clause must be refused.
    tampered = TEMPLATES["entity_neighbors"].cypher + "\nDETACH DELETE nbr"
    with pytest.raises(CypherGuardError):
        guard_read_query(tampered)


def test_no_template_contains_a_mutating_keyword() -> None:
    mutating = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|FOREACH)\b", re.IGNORECASE)
    for template in TEMPLATES.values():
        # keywords only ever appear inside quoted rel-type literals, never as clauses
        stripped = re.sub(r"'[^']*'", "''", template.cypher)
        assert not mutating.search(stripped), template.name


def test_as_dict_shape() -> None:
    template = get_template("shortest_path")
    assert template.as_dict() == {
        "name": "shortest_path",
        "cypher": template.cypher,
        "params": ["source_id", "target_id"],
    }
    assert isinstance(template, CypherTemplate)
