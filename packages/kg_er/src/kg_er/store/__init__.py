"""Alias + property-vocab loaders for ER (§8.2)."""

from __future__ import annotations

from kg_er.store.import_aliases import (
    AliasRecord,
    import_aliases,
    load_csv_aliases,
    matkg_adapter,
)
from kg_er.store.property_vocab import (
    PropertyTerm,
    PropertyVocabulary,
    default_vocabulary,
)

__all__ = [
    "AliasRecord",
    "load_csv_aliases",
    "matkg_adapter",
    "import_aliases",
    "PropertyTerm",
    "PropertyVocabulary",
    "default_vocabulary",
]
