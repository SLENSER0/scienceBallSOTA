"""Quench / cooling-medium classifier (§6.5)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from kg_extractors.cooling_medium import CoolingMedium, classify_cooling


def test_water_quench_is_fast() -> None:
    cm = classify_cooling("water quench")
    assert cm.medium == "water"
    assert cm.severity_class == "fast"


def test_furnace_cool_is_slow() -> None:
    cm = classify_cooling("furnace cool")
    assert cm.medium == "furnace"
    assert cm.severity_class == "slow"


def test_air_cooled_is_slow() -> None:
    cm = classify_cooling("air cooled")
    assert cm.medium == "air"
    assert cm.severity_class == "slow"


def test_russian_oil_is_moderate() -> None:
    cm = classify_cooling("охлаждение в масле")
    assert cm.medium == "oil"
    assert cm.severity_class == "moderate"


def test_russian_water_cue() -> None:
    cm = classify_cooling("закалка в воде")
    assert cm.medium == "water"
    assert cm.severity_class == "fast"


def test_brine_ranks_above_water_and_oil() -> None:
    brine = classify_cooling("brine")
    water = classify_cooling("water quench")
    oil = classify_cooling("oil quench")
    # brine >= water (brine is not slower than water), and strictly > oil (§6.5).
    assert brine.severity_rank >= water.severity_rank
    assert brine.severity_rank > oil.severity_rank


def test_full_heat_transfer_order() -> None:
    ranks = [classify_cooling(m).severity_rank for m in ("brine", "water", "oil", "air", "furnace")]
    assert ranks == sorted(ranks, reverse=True)
    assert len(set(ranks)) == 5


def test_unknown_medium() -> None:
    cm = classify_cooling("quenched somehow")
    assert cm.medium == "unknown"
    assert cm.severity_class == "unknown"
    assert cm.severity_rank == 0


def test_as_dict_has_all_four_keys() -> None:
    cm = classify_cooling("water quench")
    d = cm.as_dict()
    assert set(d) == {"raw", "medium", "severity_class", "severity_rank"}
    assert d["medium"] == "water"


def test_empty_text_is_unknown() -> None:
    assert classify_cooling("").medium == "unknown"


def test_dataclass_is_frozen() -> None:
    cm = classify_cooling("brine")
    with pytest.raises(FrozenInstanceError):
        cm.medium = "water"  # type: ignore[misc]


def test_construct_directly() -> None:
    cm = CoolingMedium(raw="x", medium="oil", severity_class="moderate", severity_rank=3)
    assert cm.as_dict()["severity_rank"] == 3
