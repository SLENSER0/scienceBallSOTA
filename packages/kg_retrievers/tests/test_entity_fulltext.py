"""Hand-checked tests for the embedded fulltext entity index (§8.4).

Every expected score is derived by hand from the tier bands in
:mod:`kg_retrievers.entity_fulltext`:

* exact  -> 1.0
* prefix -> 0.80 + 0.15 * len(query)/len(alias)
* token  -> 0.45 + 0.25 * overlap_fraction
* fuzzy  -> 0.20 + 0.20 * SequenceMatcher.ratio  (only if ratio >= 0.60)

The anchor entity is the reverse-osmosis (обратный осмос) solution; its folded
surfaces are short and unambiguous, so tiers are individually predictable.
"""

from __future__ import annotations

from kg_retrievers.entity_fulltext import EntityFulltext, EntityHit, build_from_nodes

# A small, fully controlled corpus. Query "осмос" hits each entity at a distinct
# tier: exact (ts:ro), prefix (ts:osm2), token (ts:memosm), fuzzy (mat:osmol).
RANKING_NODES = [
    {"id": "ts:ro", "type": "TechnologySolution", "name": "Осмос"},
    {"id": "ts:osm2", "type": "TechnologySolution", "name": "Осмосный процесс"},
    {"id": "ts:memosm", "type": "TechnologySolution", "name": "Мембранный осмос"},
    {"id": "mat:osmol", "type": "Material", "name": "Осмол"},
]


def test_exact_name_hit() -> None:
    idx = build_from_nodes([{"id": "ts:ro", "type": "TechnologySolution", "name": "Осмос"}])
    hits = idx.search("осмос")
    assert len(hits) == 1
    assert hits[0].id == "ts:ro"
    assert hits[0].type == "TechnologySolution"
    assert hits[0].label == "Осмос"
    assert hits[0].score == 1.0
    # The matched surface is the entity's own (case-folded) name.
    assert hits[0].matched_alias == "Осмос"


def test_alias_hit_sets_matched_alias() -> None:
    # Name differs from the queried alias, so matched_alias must be the alias.
    idx = build_from_nodes(
        [
            {
                "id": "ts:ro",
                "type": "TechnologySolution",
                "name": "Осмос",
                "aliases_text": "обратный осмос|reverse osmosis",
            }
        ]
    )
    hits = idx.search("reverse osmosis")
    assert len(hits) == 1
    assert hits[0].id == "ts:ro"
    assert hits[0].score == 1.0
    assert hits[0].matched_alias == "reverse osmosis"
    # The RU alias resolves to the same entity via its own surface.
    ru = idx.search("обратный осмос")
    assert ru and ru[0].matched_alias == "обратный осмос"


def test_type_filter() -> None:
    nodes = [
        {"id": "ts:ro", "type": "TechnologySolution", "name": "Осмос"},
        {"id": "mat:conc", "type": "Material", "name": "Осмос-концентрат"},
    ]
    idx = build_from_nodes(nodes)
    # No filter -> both types present, exact (ts:ro) ranked above token (mat:conc).
    both = idx.search("осмос")
    assert [h.id for h in both] == ["ts:ro", "mat:conc"]
    # type= restricts to a single category.
    only_mat = idx.search("осмос", type="Material")
    assert [h.id for h in only_mat] == ["mat:conc"]
    only_ts = idx.search("осмос", type="TechnologySolution")
    assert [h.id for h in only_ts] == ["ts:ro"]


def test_ru_declension_finds_stem() -> None:
    # §8.4: a declined query (осмоса) must find the nominative name (осмос) via the
    # light RU stemmer -> a token-tier hit at 0.70, not a fuzzy near-miss.
    idx = build_from_nodes([{"id": "ts:ro", "type": "T", "name": "Осмос"}])
    hits = idx.search("осмоса")
    assert len(hits) == 1
    assert hits[0].id == "ts:ro"
    assert hits[0].score == 0.7


def test_prefix_beats_fuzzy() -> None:
    # "полим" is a typeahead prefix of "Полимер" (prefix tier) but only a fuzzy
    # near-miss of "Полином" (0.8333 ratio), so the prefix entity must rank first.
    idx = build_from_nodes(
        [
            {"id": "p", "type": "X", "name": "Полимер"},
            {"id": "f", "type": "X", "name": "Полином"},
        ]
    )
    hits = idx.search("полим")
    assert [h.id for h in hits] == ["p", "f"]
    assert hits[0].score == 0.9071  # 0.80 + 0.15 * 5/7
    assert hits[1].score == 0.3667  # 0.20 + 0.20 * 0.8333
    assert hits[0].score > hits[1].score


def test_limit_respected() -> None:
    nodes = [
        {"id": "w1", "type": "Material", "name": "Шахтная вода"},
        {"id": "w2", "type": "Material", "name": "Питьевая вода"},
        {"id": "w3", "type": "Material", "name": "Морская вода"},
    ]
    idx = build_from_nodes(nodes)
    # All three token-match "вода" at 0.70; limit caps the returned list.
    assert len(idx.search("вода")) == 3
    assert len(idx.search("вода", limit=2)) == 2
    assert len(idx.search("вода", limit=1)) == 1


def test_unknown_returns_empty() -> None:
    idx = build_from_nodes(RANKING_NODES)
    # No exact/prefix/token overlap and every fuzzy ratio is below FUZZY_MIN.
    assert idx.search("квантовая криптография") == []


def test_ranking_order_across_tiers() -> None:
    idx = build_from_nodes(RANKING_NODES)
    hits = idx.search("осмос")
    assert [h.id for h in hits] == ["ts:ro", "ts:osm2", "ts:memosm", "mat:osmol"]
    scores = [h.score for h in hits]
    # exact > prefix > token > fuzzy, strictly descending.
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 1.0  # exact
    assert scores[2] == 0.7  # token overlap 1.0
    assert scores[3] == 0.36  # fuzzy, ratio 0.80
    assert 0.7 < scores[1] < 1.0  # prefix sits between token and exact


def test_empty_query_returns_empty() -> None:
    idx = build_from_nodes(RANKING_NODES)
    assert idx.search("") == []
    assert idx.search("   ") == []


def test_as_dict_shape_and_build() -> None:
    idx = EntityFulltext.build_from_nodes(RANKING_NODES)
    assert len(idx) == 4
    hit = idx.search("осмос")[0]
    assert isinstance(hit, EntityHit)
    assert hit.as_dict() == {
        "id": "ts:ro",
        "label": "Осмос",
        "type": "TechnologySolution",
        "score": 1.0,
        "matched_alias": "Осмос",
    }
