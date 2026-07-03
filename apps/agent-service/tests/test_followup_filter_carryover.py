"""Hand-checked tests for §13.15 follow-up filter carryover.

Pure-python, no store / no LLM: drive :func:`carry_filters` and
:func:`is_followup_filter_query` directly and assert the exact merged filters, the
sorted ``carried_keys`` audit trail, non-mutation of both inputs and
orjson-serialisability of :class:`CarriedFilters`. Every expected value is spelled out
so the test is verifiable by hand (RU + EN).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import orjson
import pytest
from agent_service.followup_filter_carryover import (
    DEFAULT_CARRY_KEYS,
    CarriedFilters,
    carry_filters,
    is_followup_filter_query,
)


# ---------------------------------------------------------------------------
# (1) prior has material, current lacks it -> material carried
# ---------------------------------------------------------------------------
def test_material_carried_when_current_lacks_it() -> None:
    prior = {"material": "Al-Cu"}
    current = {"property": "hardness"}
    res = carry_filters(current, prior)
    assert res.filters["material"] == "Al-Cu"
    assert "material" in res.carried_keys


# ---------------------------------------------------------------------------
# (2) current already has material -> prior value not applied, key not recorded
# ---------------------------------------------------------------------------
def test_current_material_not_overridden() -> None:
    prior = {"material": "Al-Cu"}
    current = {"material": "Fe-C"}
    res = carry_filters(current, prior)
    assert res.filters["material"] == "Fe-C"
    assert "material" not in res.carried_keys


# ---------------------------------------------------------------------------
# (3) a key absent in both is not added
# ---------------------------------------------------------------------------
def test_key_absent_in_both_not_added() -> None:
    res = carry_filters({"material": "Al-Cu"}, {"material": "Al-Cu"})
    assert "date_from" not in res.filters
    assert "verified_only" not in res.filters
    assert res.carried_keys == ()


# ---------------------------------------------------------------------------
# (4) carried_keys is sorted
# ---------------------------------------------------------------------------
def test_carried_keys_is_sorted() -> None:
    prior = {"verified_only": True, "min_confidence": 0.8, "date_from": "2020-01-01"}
    current: dict[str, object] = {}
    res = carry_filters(current, prior)
    assert res.carried_keys == ("date_from", "min_confidence", "verified_only")
    assert list(res.carried_keys) == sorted(res.carried_keys)


# ---------------------------------------------------------------------------
# (5) neither prior nor current dict is mutated
# ---------------------------------------------------------------------------
def test_inputs_not_mutated() -> None:
    prior = {"material": "Al-Cu", "min_confidence": 0.9}
    current = {"property": "hardness"}
    prior_before = dict(prior)
    current_before = dict(current)
    res = carry_filters(current, prior)
    assert prior == prior_before
    assert current == current_before
    # the result holds a fresh dict, distinct from the current input
    res.filters["material"] = "mutated"
    assert current == current_before


# ---------------------------------------------------------------------------
# (6) verified_only from prior is carried when current omits it
# ---------------------------------------------------------------------------
def test_verified_only_carried() -> None:
    res = carry_filters({"property": "modulus"}, {"verified_only": True})
    assert res.filters["verified_only"] is True
    assert res.carried_keys == ("verified_only",)


# ---------------------------------------------------------------------------
# (7) empty prior -> filters equal a copy of current, no carried keys
# ---------------------------------------------------------------------------
def test_empty_prior_yields_copy_of_current() -> None:
    current = {"material": "Al-Cu", "property": "hardness"}
    res = carry_filters(current, {})
    assert res.filters == current
    assert res.filters is not current
    assert res.carried_keys == ()


# ---------------------------------------------------------------------------
# is_followup_filter_query: bare follow-up detection
# ---------------------------------------------------------------------------
def test_is_followup_true_when_no_subject() -> None:
    assert is_followup_filter_query({"min_confidence": 0.8}) is True
    assert is_followup_filter_query({}) is True


def test_is_followup_false_when_material_or_property_present() -> None:
    assert is_followup_filter_query({"material": "Al-Cu"}) is False
    assert is_followup_filter_query({"property": "hardness"}) is False


# ---------------------------------------------------------------------------
# multiple keys carried at once, current-set keys preserved
# ---------------------------------------------------------------------------
def test_multiple_keys_carried_and_current_preserved() -> None:
    prior = {"min_confidence": 0.8, "verified_only": True, "material": "Al-Cu"}
    current = {"min_confidence": 0.95, "property": "hardness"}
    res = carry_filters(current, prior)
    # current's own min_confidence wins; verified_only + material carried in
    assert res.filters["min_confidence"] == 0.95
    assert res.filters["verified_only"] is True
    assert res.filters["material"] == "Al-Cu"
    assert res.filters["property"] == "hardness"
    assert res.carried_keys == ("material", "verified_only")


# ---------------------------------------------------------------------------
# custom carry_keys restricts which keys are eligible
# ---------------------------------------------------------------------------
def test_custom_carry_keys_restricts_eligibility() -> None:
    prior = {"min_confidence": 0.8, "material": "Al-Cu"}
    res = carry_filters({}, prior, carry_keys=("material",))
    assert res.carried_keys == ("material",)
    assert "min_confidence" not in res.filters


# ---------------------------------------------------------------------------
# as_dict is orjson-serialisable and round-trips
# ---------------------------------------------------------------------------
def test_as_dict_is_orjson_serialisable() -> None:
    res = carry_filters({"property": "hardness"}, {"material": "Al-Cu"})
    payload = orjson.dumps(res.as_dict())
    back = orjson.loads(payload)
    assert back == {
        "filters": {"property": "hardness", "material": "Al-Cu"},
        "carried_keys": ["material"],
    }


# ---------------------------------------------------------------------------
# CarriedFilters is frozen; DEFAULT_CARRY_KEYS spells out the five filters
# ---------------------------------------------------------------------------
def test_carried_filters_is_frozen() -> None:
    res = CarriedFilters(filters={}, carried_keys=())
    with pytest.raises(FrozenInstanceError):
        res.carried_keys = ("x",)  # type: ignore[misc]


def test_default_carry_keys_cover_the_five_filters() -> None:
    assert set(DEFAULT_CARRY_KEYS) == {
        "min_confidence",
        "verified_only",
        "date_from",
        "material",
        "property",
    }
