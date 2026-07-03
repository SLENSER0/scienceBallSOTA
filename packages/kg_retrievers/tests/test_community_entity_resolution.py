"""§11.5 — tests for GraphRAG entity -> canonical id resolution (pure mapper)."""

from __future__ import annotations

from kg_retrievers.community_entity_resolution import (
    ResolutionResult,
    ResolvedEntity,
    resolve_entities,
)


def test_exact_lowercase_key_match() -> None:
    """'Iron' resolves to 'M1' via alias key 'iron' (casefold match)."""
    result = resolve_entities(["Iron"], {"iron": "M1"})
    assert result.entries[0].canonical_id == "M1"
    assert result.entries[0].matched is True
    assert result.match_rate == 1.0


def test_strip_and_casefold_matches_key() -> None:
    """' STEEL ' matches alias key 'steel' after strip + casefold."""
    result = resolve_entities([" STEEL "], {"steel": "M2"})
    entry = result.entries[0]
    assert entry.raw == " STEEL "  # original preserved verbatim
    assert entry.canonical_id == "M2"
    assert entry.matched is True


def test_unknown_name_is_unmatched() -> None:
    """An unknown name yields canonical_id None and matched False."""
    result = resolve_entities(["Vibranium"], {"iron": "M1"})
    entry = result.entries[0]
    assert entry.canonical_id is None
    assert entry.matched is False


def test_match_rate_half_for_one_of_two() -> None:
    """One hit out of two names gives match_rate 0.5."""
    result = resolve_entities(["Iron", "Vibranium"], {"iron": "M1"})
    assert result.match_rate == 0.5
    assert [e.matched for e in result.entries] == [True, False]


def test_empty_input() -> None:
    """Empty input -> match_rate 0.0 and no entries."""
    result = resolve_entities([], {"iron": "M1"})
    assert result.match_rate == 0.0
    assert result.entries == ()


def test_duplicate_names_resolve_independently() -> None:
    """Duplicate raw names each resolve independently (identical results)."""
    result = resolve_entities(["Iron", "Iron"], {"iron": "M1"})
    assert len(result.entries) == 2
    assert all(e.canonical_id == "M1" and e.matched for e in result.entries)
    assert result.match_rate == 1.0


def test_as_dict_of_matched_entry() -> None:
    """as_dict() of a matched entry reports matched True and its canonical id."""
    entry = resolve_entities(["Iron"], {"iron": "M1"}).entries[0]
    d = entry.as_dict()
    assert d == {"raw": "Iron", "canonical_id": "M1", "matched": True}


def test_result_as_dict_shape() -> None:
    """ResolutionResult.as_dict() nests entry dicts and the match_rate."""
    result = resolve_entities(["Iron", "Gold"], {"iron": "M1"})
    d = result.as_dict()
    assert d["match_rate"] == 0.5
    assert d["entries"] == [
        {"raw": "Iron", "canonical_id": "M1", "matched": True},
        {"raw": "Gold", "canonical_id": None, "matched": False},
    ]


def test_alias_keys_are_normalized() -> None:
    """Alias keys are normalized too: a ' Iron ' key matches an 'iron' name."""
    result = resolve_entities(["iron"], {" IRON ": "M1"})
    assert result.entries[0].canonical_id == "M1"


def test_frozen_dataclasses() -> None:
    """ResolvedEntity / ResolutionResult are frozen (immutable)."""
    entry = ResolvedEntity(raw="Iron", canonical_id="M1", matched=True)
    result = ResolutionResult(entries=(entry,), match_rate=1.0)
    for obj, attr, val in ((entry, "raw", "X"), (result, "match_rate", 0.0)):
        try:
            setattr(obj, attr, val)
        except AttributeError:
            continue
        raise AssertionError("expected frozen dataclass to reject mutation")
