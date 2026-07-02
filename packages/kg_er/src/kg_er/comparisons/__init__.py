"""Comparison + cleaning primitives for entity resolution (§8.3)."""

from __future__ import annotations

from kg_er.comparisons.composition import (
    NormalizedComposition,
    composition_distance,
    element_jaccard,
    normalize_formula,
)
from kg_er.comparisons.embed import cosine, embed_text
from kg_er.comparisons.text import (
    clean_text,
    designation_code,
    email_domain,
    jaccard,
    split_person_name,
    token_set,
)

__all__ = [
    "clean_text",
    "token_set",
    "jaccard",
    "split_person_name",
    "email_domain",
    "designation_code",
    "normalize_formula",
    "NormalizedComposition",
    "composition_distance",
    "element_jaccard",
    "embed_text",
    "cosine",
]
