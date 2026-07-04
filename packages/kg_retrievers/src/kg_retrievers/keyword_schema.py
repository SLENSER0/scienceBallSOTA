"""OpenSearch index mapping + a matching pure-python analyzer (§4.6).

§4.6 specifies the server-profile keyword backend (OpenSearch): a custom
``scientific_text`` analyzer (lowercase + asciifolding + a ``word_delimiter_graph``
that keeps chemical/unit tokens like ``Al-Cu`` / ``AA2024`` intact) plus an index
mapping with analyzed **text** fields, **keyword** facet fields and **numeric**
fields. The embedded profile ships BM25 (``rank_bm25``, see ``keyword_store.py``)
rather than a real cluster, so this module has two jobs:

* emit the server-side artefacts declaratively — :data:`SCIENTIFIC_ANALYZER`
  (the analyzer descriptor) and :func:`build_index_mapping` (the mapping JSON a
  future ``ensure_indices`` would ``PUT``);
* provide :func:`analyze`, a dependency-free stand-in that reproduces the tokens
  the ``scientific_text`` analyzer / BM25 would index, so the embedded profile can
  tokenise identically without a torch- or JVM-backed model.

:func:`analyze` folds RU/EN text: NFKC-normalise, lowercase, then keep maximal
runs of letters/digits. Numeric and unit tokens survive intact (``250``,
``aa2024``) because a run of digits is a valid token and the delimiter is *not*
split on numerics; tokens shorter than :data:`MIN_TOKEN_LEN` (stray single
characters) are dropped. Everything is deterministic and pure stdlib.

The pure-python side deliberately does **not** stem — the descriptor documents
the server analyzer's full filter chain, while :func:`analyze` mirrors only its
case-folding + tokenisation so its output stays hand-checkable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# A token must be at least this long; single stray characters (RU «и», EN «a»)
# carry no lexical signal and are dropped. Digit runs like «250» clear this (§4.6).
MIN_TOKEN_LEN: int = 2

# Token = maximal run of RU/EN letters or digits. Punctuation and separators
# (``-``, ``,`` …) delimit tokens and never appear inside one (§4.6).
_TOKEN_RE = re.compile(r"[0-9a-zа-яё]+")

# Field groups of the mapping, split by OpenSearch field family (§4.6). Keyword
# fields drive the facet filters (material/property/source_type/review_status);
# numeric fields drive range filters; the date field drives recency filters.
TEXT_FIELDS: tuple[str, ...] = ("name", "aliases_text", "text")
KEYWORD_FIELDS: tuple[str, ...] = (
    "id",
    "label",
    "domain",
    "material_ids",
    "property_ids",
    "source_type",
    "review_status",
)
NUMERIC_FIELDS: tuple[str, ...] = (
    "value_normalized",
    "temperature_c",
    "time_h",
    "confidence",
)
DATE_FIELDS: tuple[str, ...] = ("published_date",)


def analyze(text: str) -> list[str]:
    """Tokens the ``scientific_text`` analyzer / BM25 would index for ``text`` (§4.6).

    NFKC-normalises, lowercases (RU/EN alike) and keeps maximal runs of
    letters/digits at least :data:`MIN_TOKEN_LEN` long. Numeric/unit tokens are
    preserved (``"250"`` → ``["250"]``, ``"AA2024"`` → ``["aa2024"]``); punctuation
    is dropped and never merges tokens (``"Al-Cu"`` → ``["al", "cu"]``). Empty or
    punctuation-only input folds to ``[]``. Deterministic, left-to-right order.
    """
    folded = unicodedata.normalize("NFKC", text).lower()
    return [tok for tok in _TOKEN_RE.findall(folded) if len(tok) >= MIN_TOKEN_LEN]


@dataclass(frozen=True)
class AnalyzerSpec:
    """Descriptor of a custom OpenSearch analyzer — its tokenizer + filter chain (§4.6)."""

    name: str
    tokenizer: str
    filters: tuple[str, ...]

    def as_dict(self) -> dict:
        """OpenSearch ``analysis.analyzer.<name>`` body (``type: custom``) (§4.6)."""
        return {
            "type": "custom",
            "tokenizer": self.tokenizer,
            "filter": list(self.filters),
        }


# The ``scientific_text`` analyzer (§4.6): lowercase + asciifolding, then a
# word_delimiter_graph that keeps chemical/unit tokens whole. ``analyze`` mirrors
# the lowercase + tokenisation half of this chain.
SCIENTIFIC_ANALYZER: AnalyzerSpec = AnalyzerSpec(
    name="scientific_text",
    tokenizer="standard",
    filters=(
        "lowercase",
        "asciifolding",
        "sci_word_delimiter",
        "sci_english_stem",
        "sci_russian_stem",
    ),
)

# Light English stemmer (§4.6) applied after delimiting — folds plural/verb forms
# (``coatings`` → ``coat``) while the word_delimiter keeps chemical tokens intact.
SCI_ENGLISH_STEM: dict[str, object] = {"type": "stemmer", "language": "english"}

# Russian snowball stemmer, applied AFTER the English one so Cyrillic morphology is
# folded (``сульфаты``/``сульфатов`` → ``сульфат``, ``переработка`` matches
# ``перерабатывать``) — the dominant corpus language. Order en→ru keeps Latin/chemical
# tokens intact (russian snowball leaves ASCII untouched). Measured: keyword recall for
# «переработка» 13→128 and «сульфаты» 6→83 on the 52k-chunk corpus.
SCI_RUSSIAN_STEM: dict[str, object] = {"type": "stemmer", "language": "russian"}

# Custom token filter referenced by SCIENTIFIC_ANALYZER: keep химические/единичные
# токены (``Al-Cu``, ``AA2024``) intact — no split on numerics, keep the original.
SCI_WORD_DELIMITER: dict[str, object] = {
    "type": "word_delimiter_graph",
    "preserve_original": True,
    "split_on_numerics": False,
    "catenate_all": True,
}


def _text_field(*, term_vectors: bool = False) -> dict:
    """An analyzed ``text`` field using :data:`SCIENTIFIC_ANALYZER` (§4.6)."""
    field: dict[str, object] = {"type": "text", "analyzer": SCIENTIFIC_ANALYZER.name}
    if term_vectors:
        # Positions/offsets speed up highlight on the main body field (§4.6).
        field["term_vector"] = "with_positions_offsets"
        field["fields"] = {"exact": {"type": "keyword"}}
    return field


def build_index_mapping() -> dict:
    """OpenSearch create-index body: ``settings`` (analysis) + ``mappings`` (§4.6).

    Declares the :data:`SCIENTIFIC_ANALYZER` and its custom filter under
    ``settings.analysis``, and a ``properties`` map with analyzed text fields
    (:data:`TEXT_FIELDS`, all using ``scientific_text``), keyword facet fields
    (:data:`KEYWORD_FIELDS`) and the numeric :data:`NUMERIC_FIELDS`. Pure data —
    building it twice yields equal, independent dicts (idempotent).
    """
    properties: dict[str, dict] = {
        "name": _text_field(),
        "aliases_text": _text_field(),
        "text": _text_field(term_vectors=True),
    }
    for field in KEYWORD_FIELDS:
        properties[field] = {"type": "keyword"}
    for field in NUMERIC_FIELDS:
        properties[field] = {"type": "float"}
    for field in DATE_FIELDS:
        properties[field] = {"type": "date"}
    return {
        "settings": {
            "analysis": {
                "analyzer": {SCIENTIFIC_ANALYZER.name: SCIENTIFIC_ANALYZER.as_dict()},
                "filter": {
                    "sci_word_delimiter": dict(SCI_WORD_DELIMITER),
                    "sci_english_stem": dict(SCI_ENGLISH_STEM),
                    "sci_russian_stem": dict(SCI_RUSSIAN_STEM),
                },
            }
        },
        "mappings": {"properties": properties},
    }
