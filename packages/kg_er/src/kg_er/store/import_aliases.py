"""Alias-dataset importer with pluggable source adapters (§8.2).

Loads the seed ``material_aliases.csv`` and provides adapter hooks for external
authorities (MatKG, Materials Project). Each adapter yields ``AliasRecord``-shaped
dicts; the importer dedupes by (alias_text, canonical_id) and returns rows ready
to upsert into the graph as canonical + alias nodes.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from kg_er.comparisons.text import clean_text

_DEFAULT_CSV = Path(__file__).resolve().parents[1] / "data" / "material_aliases.csv"


@dataclass(frozen=True)
class AliasRecord:
    alias_text: str
    canonical_id: str
    entity_type: str
    source: str
    lang: str = ""


def _norm_key(alias_text: str, canonical_id: str) -> tuple[str, str]:
    return clean_text(alias_text), canonical_id


def load_csv_aliases(path: Path | str | None = None) -> Iterator[AliasRecord]:
    p = Path(path) if path else _DEFAULT_CSV
    with p.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("alias_text") or not row.get("canonical_id"):
                continue
            yield AliasRecord(
                alias_text=row["alias_text"].strip(),
                canonical_id=row["canonical_id"].strip(),
                entity_type=row.get("entity_type", "Material").strip(),
                source=row.get("source", "seed").strip(),
                lang=row.get("lang", "").strip(),
            )


def matkg_adapter(rows: Iterable[dict]) -> Iterator[AliasRecord]:
    """Adapt MatKG-style {name, mpid|canonical} rows -> AliasRecord (§8.2)."""
    for r in rows:
        alias = r.get("name") or r.get("alias_text")
        canonical = r.get("mpid") or r.get("canonical_id") or r.get("canonical")
        if not alias or not canonical:
            continue
        yield AliasRecord(str(alias), str(canonical), "Material", "matkg", r.get("lang", ""))


def import_aliases(
    *,
    csv_path: Path | str | None = None,
    extra: Iterable[AliasRecord] = (),
) -> list[AliasRecord]:
    """Merge CSV seed + adapter rows, deduped by (clean alias, canonical)."""
    seen: set[tuple[str, str]] = set()
    out: list[AliasRecord] = []
    for rec in (*load_csv_aliases(csv_path), *extra):
        key = _norm_key(rec.alias_text, rec.canonical_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out
