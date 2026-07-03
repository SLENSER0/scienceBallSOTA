"""Hand-checkable tests for the §16.6 ``alias_add`` planner (RU/EN)."""

from __future__ import annotations

from kg_common.storage.alias_add_plan import AliasAddPlan, _norm, plan_alias_add


def _entity() -> dict:
    """Return a small entity fixture (id, name, one existing alias)."""
    return {"id": "E1", "name": "Acme Corp", "aliases": ["ACME Corporation"]}


def test_norm_strip_casefold_collapse() -> None:
    assert _norm("  Foo   Bar ") == "foo bar"


def test_brand_new_alias_added() -> None:
    # (1) a fresh normalized candidate becomes the sole add and shows up.
    plan = plan_alias_add(_entity(), ["acme inc"], {})
    assert plan.added == ["acme inc"]
    assert "acme inc" in plan.aliases
    assert plan.noop is False
    assert plan.collision is False


def test_alias_equal_to_name_is_noop() -> None:
    # (2) candidate equal to the entity name (different case) is skipped.
    plan = plan_alias_add(_entity(), ["ACME CORP"], {})
    assert plan.added == []
    assert plan.noop is True


def test_existing_alias_not_readded() -> None:
    # (3) candidate matching an existing alias case-insensitively is skipped.
    plan = plan_alias_add(_entity(), ["acme corporation"], {})
    assert plan.added == []
    assert plan.noop is True
    # Existing alias survives (normalized) in the merged list.
    assert "acme corporation" in plan.aliases


def test_collision_with_other_entity_canonical() -> None:
    # (4) candidate is another entity's canonical name → collision.
    canon = {"globex": "E2"}
    plan = plan_alias_add(_entity(), ["Globex"], canon)
    assert plan.collision is True
    assert plan.collision_owner == "E2"
    assert plan.added == []


def test_own_canonical_name_no_collision() -> None:
    # (5) matching THIS entity's own canonical name does not collide.
    canon = {"acme corp": "E1"}
    plan = plan_alias_add(_entity(), ["Acme Corp"], canon)
    assert plan.collision is False
    assert plan.collision_owner is None
    assert plan.added == []  # equals the name → skipped anyway


def test_variants_dedupe_to_one_add() -> None:
    # (6) whitespace/case variants of one candidate collapse to a single add.
    plan = plan_alias_add(_entity(), ["Beta Labs", "  beta   labs "], {})
    assert plan.added == ["beta labs"]


def test_as_dict_round_trips_collision_fields() -> None:
    # (7) as_dict carries collision / collision_owner faithfully.
    plan = plan_alias_add(_entity(), ["Globex"], {"globex": "E2"})
    d = plan.as_dict()
    assert d["collision"] is True
    assert d["collision_owner"] == "E2"
    assert d["entity_id"] == "E1"
    assert d["added"] == []
    assert isinstance(plan, AliasAddPlan)


def test_multiple_candidates_merged_sorted() -> None:
    # Merged alias list is sorted and includes existing + new normalized ones.
    plan = plan_alias_add(_entity(), ["Zeta", "alpha"], {})
    assert plan.aliases == sorted(plan.aliases)
    assert "alpha" in plan.aliases
    assert "zeta" in plan.aliases
    assert "acme corporation" in plan.aliases
