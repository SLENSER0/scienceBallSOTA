"""Claim → about-target linking tests (§6.9)."""

from __future__ import annotations

from kg_extractors.claim_target_linker import ClaimLink, link_claim_targets


def test_basic_material_and_property_regime_none() -> None:
    # material to the left (dist 5), property to the right (dist 10); no regime.
    link = link_claim_targets(
        (10, 20),
        [
            {"type": "material", "text": "Al-Cu", "char_start": 0, "char_end": 5},
            {"type": "property", "text": "hardness", "char_start": 30, "char_end": 38},
        ],
    )
    assert link.about_material == "Al-Cu"
    assert link.about_property == "hardness"
    assert link.about_regime is None


def test_nearer_material_wins() -> None:
    # "A" edge dist = 100-91 = 9; "B" edge dist = 100-1 = 99 → nearer "A" wins.
    link = link_claim_targets(
        (100, 110),
        [
            {"type": "material", "text": "A", "char_start": 90, "char_end": 91},
            {"type": "material", "text": "B", "char_start": 0, "char_end": 1},
        ],
    )
    assert link.about_material == "A"


def test_empty_mentions_all_none() -> None:
    link = link_claim_targets((5, 10), [])
    assert link.about_material is None
    assert link.about_property is None
    assert link.about_regime is None


def test_regime_mention_linked() -> None:
    link = link_claim_targets(
        (50, 60),
        [{"type": "regime", "text": "quenched", "char_start": 40, "char_end": 48}],
    )
    assert link.about_regime == "quenched"
    assert link.about_material is None
    assert link.about_property is None


def test_tie_picks_earliest_start() -> None:
    # Both mentions equidistant (edge dist 5) → earliest char_start wins.
    # left mention: char_end 5, claim start 10 → dist 5 (start 3).
    # right mention: char_start 25, claim end 20 → dist 5 (start 25).
    link = link_claim_targets(
        (10, 20),
        [
            {"type": "material", "text": "right", "char_start": 25, "char_end": 30},
            {"type": "material", "text": "left", "char_start": 3, "char_end": 5},
        ],
    )
    assert link.about_material == "left"


def test_as_dict_keys() -> None:
    link = link_claim_targets((0, 1), [])
    assert set(link.as_dict()) == {"about_material", "about_property", "about_regime"}


def test_as_dict_values_roundtrip() -> None:
    link = link_claim_targets(
        (10, 20),
        [{"type": "material", "text": "Ti-6Al-4V", "char_start": 0, "char_end": 9}],
    )
    assert link.as_dict() == {
        "about_material": "Ti-6Al-4V",
        "about_property": None,
        "about_regime": None,
    }
    assert isinstance(link, ClaimLink)


def test_overlapping_mention_is_zero_distance() -> None:
    # Overlapping property (dist 0) beats a far one (dist large).
    link = link_claim_targets(
        (10, 20),
        [
            {"type": "property", "text": "near", "char_start": 12, "char_end": 18},
            {"type": "property", "text": "far", "char_start": 200, "char_end": 210},
        ],
    )
    assert link.about_property == "near"


def test_unknown_type_ignored() -> None:
    link = link_claim_targets(
        (10, 20),
        [{"type": "device", "text": "sensor", "char_start": 0, "char_end": 6}],
    )
    assert link.about_material is None
    assert link.about_property is None
    assert link.about_regime is None
