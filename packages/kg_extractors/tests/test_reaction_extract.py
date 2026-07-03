"""Chemical-reaction extraction tests (§6.12).

Hand-checked cases for :func:`kg_extractors.reaction_extract.extract_reactions`.
"""

from __future__ import annotations

from kg_extractors.reaction_extract import Reaction, extract_reactions


def test_two_reactant_two_product_split() -> None:
    res = extract_reactions("2Cu2S + 3O2 -> 2Cu2O + 2SO2")
    assert res == [
        Reaction(
            reactants=["Cu2S", "O2"],
            products=["Cu2O", "SO2"],
            arrow="->",
            source_span="2Cu2S + 3O2 -> 2Cu2O + 2SO2",
        )
    ]


def test_arrow_variant_ascii() -> None:
    res = extract_reactions("2H2 + O2 -> 2H2O")
    assert len(res) == 1
    assert res[0].arrow == "->"


def test_arrow_variant_equals() -> None:
    res = extract_reactions("N2 + 3H2 = 2NH3")
    assert len(res) == 1
    assert res[0].arrow == "="
    assert res[0].reactants == ["N2", "H2"]
    assert res[0].products == ["NH3"]


def test_arrow_variant_unicode() -> None:
    res = extract_reactions("2H2 + O2 → 2H2O")
    assert len(res) == 1
    assert res[0].arrow == "→"
    assert res[0].source_span == "2H2 + O2 → 2H2O"


def test_single_product() -> None:
    res = extract_reactions("2H2 + O2 -> 2H2O")
    assert res[0].products == ["H2O"]
    assert len(res[0].products) == 1


def test_coefficients_stripped_from_species() -> None:
    res = extract_reactions("2Cu2S + 3O2 -> 2Cu2O + 2SO2")
    for species in res[0].reactants + res[0].products:
        assert not species[0].isdigit()  # no leading stoichiometric coefficient
    assert res[0].reactants == ["Cu2S", "O2"]  # subscripts preserved


def test_russian_notation_reaction() -> None:
    res = extract_reactions("Реакция обжига: CuFeS2 + O2 = Cu2S + SO2")
    assert res == [
        Reaction(
            reactants=["CuFeS2", "O2"],
            products=["Cu2S", "SO2"],
            arrow="=",
            source_span="CuFeS2 + O2 = Cu2S + SO2",
        )
    ]


def test_non_reaction_text_returns_empty() -> None:
    assert extract_reactions("The polished specimen was examined by microscopy.") == []
    assert extract_reactions("Металлический образец был очищен и высушен.") == []


def test_empty_text_returns_empty() -> None:
    assert extract_reactions("") == []


def test_species_trimmed_of_whitespace() -> None:
    res = extract_reactions("2Cu2S   +   3O2   ->   2Cu2O  +  2SO2")
    assert res[0].reactants == ["Cu2S", "O2"]
    assert res[0].products == ["Cu2O", "SO2"]


def test_invalid_element_token_rejected() -> None:
    # "Xx" and "Yy" are not valid element symbols — not a real reaction.
    assert extract_reactions("Xx2 + O2 -> Yy2O3") == []


def test_as_dict_shape() -> None:
    res = extract_reactions("N2 + 3H2 = 2NH3")
    assert res[0].as_dict() == {
        "reactants": ["N2", "H2"],
        "products": ["NH3"],
        "arrow": "=",
        "source_span": "N2 + 3H2 = 2NH3",
    }
