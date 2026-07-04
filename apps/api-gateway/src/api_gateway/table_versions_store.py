"""§5.8 Manual table correction as a *new artifact version* (mitigation §18).

When docling (or a fallback parser) mis-reads a table, a curator can re-type the
grid by hand. Per the §5.8 acceptance criterion the correction must **create a
new version** of the parsed-table artifact — tagged ``corrected=true`` /
``parser_used="manual"`` — **without deleting the original** parser output.

Storage model (никогда не трогает исходный sidecar):

- The upload sidecar ``runtime_dir/uploads/<doc>.json`` (written by the documents
  router) holds the parser's ``tables: [{page, rows}]``. That is **version 0** —
  the immutable original, read-only here.
- Each manual correction is appended as ``vNNN.json`` under
  ``runtime_dir/uploads/table_versions/<doc>/table_<index>/`` — a monotonically
  increasing version, so the full lineage (v0 original → v1 … vN) is preserved
  and auditable. Rolling back is just reading an earlier file.

Public surface:

- :func:`base_table` / :func:`base_table_count` — read the immutable v0 grid(s).
- :func:`list_versions` — original + every correction, oldest→newest.
- :func:`current_table` — the effective (latest) grid for a table.
- :func:`append_correction` — validate + persist a new version, return its record.

Pure filesystem + JSON. No graph writes, no LLM, no network.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kg_common import get_settings

_ORIGINAL_PARSER_FALLBACK = "parser"
_VERSION_RE = re.compile(r"^v(\d{3,})\.json$")


# -- paths ---------------------------------------------------------------------
def _safe(doc_id: str) -> str:
    """Filesystem-safe token for a doc id (``Document:hash`` → ``Document_hash``)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", doc_id or "")


def _uploads_dir() -> Path:
    return Path(get_settings().runtime_dir) / "uploads"


def _sidecar_path(doc_id: str) -> Path:
    """The original upload sidecar (version 0 — read-only)."""
    return _uploads_dir() / f"{_safe(doc_id)}.json"


def _versions_dir(doc_id: str, table_index: int) -> Path:
    return _uploads_dir() / "table_versions" / _safe(doc_id) / f"table_{int(table_index)}"


# -- errors --------------------------------------------------------------------
class DocumentNotFound(Exception):
    """No upload sidecar exists for the given ``doc_id``."""


class TableNotFound(Exception):
    """The ``table_index`` is out of range for the document's parsed tables."""


class InvalidRows(Exception):
    """The submitted correction grid is empty or not a rectangular string grid."""


# -- records -------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TableVersion:
    """One version of a parsed-table artifact (v0 original, v≥1 corrections)."""

    doc_id: str
    table_index: int
    version: int
    rows: tuple[tuple[str, ...], ...]
    page: int | None
    parser_used: str
    corrected: bool
    reason: str = ""
    author: str = ""
    created_at: int = 0
    base_parser: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "docId": self.doc_id,
            "tableIndex": self.table_index,
            "version": self.version,
            "rows": [list(r) for r in self.rows],
            "nRows": len(self.rows),
            "nCols": max((len(r) for r in self.rows), default=0),
            "page": self.page,
            "parserUsed": self.parser_used,
            "corrected": self.corrected,
            "reason": self.reason,
            "author": self.author,
            "createdAt": self.created_at,
            "baseParser": self.base_parser,
        }


@dataclass(frozen=True, slots=True)
class TableLineage:
    """A table's full version lineage (original + corrections)."""

    doc_id: str
    table_index: int
    versions: tuple[TableVersion, ...] = field(default_factory=tuple)

    @property
    def current(self) -> TableVersion:
        return self.versions[-1]

    def as_dict(self) -> dict[str, Any]:
        return {
            "docId": self.doc_id,
            "tableIndex": self.table_index,
            "versionCount": len(self.versions),
            "corrected": any(v.corrected for v in self.versions),
            "current": self.current.as_dict(),
            "versions": [v.as_dict() for v in self.versions],
        }


# -- sidecar reads (version 0) -------------------------------------------------
def _load_sidecar(doc_id: str) -> dict[str, Any]:
    p = _sidecar_path(doc_id)
    if not p.exists():
        raise DocumentNotFound(doc_id)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - corrupt sidecar
        raise DocumentNotFound(doc_id) from exc


def _sidecar_tables(doc_id: str) -> list[dict[str, Any]]:
    data = _load_sidecar(doc_id)
    tables = data.get("tables")
    return [t for t in tables if isinstance(t, dict)] if isinstance(tables, list) else []


def _base_parser(doc_id: str) -> str:
    """Parser that produced the original artifact (from sidecar), best-effort."""
    with contextlib.suppress(DocumentNotFound):
        data = _load_sidecar(doc_id)
        return str(data.get("parser_used") or data.get("extractor") or _ORIGINAL_PARSER_FALLBACK)
    return _ORIGINAL_PARSER_FALLBACK


def _norm_grid(rows: Any) -> tuple[tuple[str, ...], ...]:
    grid: list[tuple[str, ...]] = []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, list):
                grid.append(tuple("" if c is None else str(c) for c in row))
    return tuple(grid)


def base_table_count(doc_id: str) -> int:
    """Number of parsed tables in the original artifact (raises if doc unknown)."""
    return len(_sidecar_tables(doc_id))


def base_table(doc_id: str, table_index: int) -> TableVersion:
    """Version 0 — the immutable original grid for ``table_index``."""
    tables = _sidecar_tables(doc_id)
    if table_index < 0 or table_index >= len(tables):
        raise TableNotFound(f"{doc_id}#{table_index}")
    t = tables[table_index]
    return TableVersion(
        doc_id=doc_id,
        table_index=table_index,
        version=0,
        rows=_norm_grid(t.get("rows")),
        page=int(t["page"]) if isinstance(t.get("page"), int) else t.get("page"),
        parser_used=_base_parser(doc_id),
        corrected=False,
        base_parser=_base_parser(doc_id),
        created_at=0,
    )


# -- correction versions (v≥1) -------------------------------------------------
def _read_version_file(doc_id: str, table_index: int, path: Path) -> TableVersion | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):  # pragma: no cover - skip corrupt file
        return None
    return TableVersion(
        doc_id=doc_id,
        table_index=table_index,
        version=int(d.get("version", 0)),
        rows=_norm_grid(d.get("rows")),
        page=d.get("page"),
        parser_used=str(d.get("parser_used") or "manual"),
        corrected=bool(d.get("corrected", True)),
        reason=str(d.get("reason") or ""),
        author=str(d.get("author") or ""),
        created_at=int(d.get("created_at") or 0),
        base_parser=str(d.get("base_parser") or ""),
    )


def _correction_versions(doc_id: str, table_index: int) -> list[TableVersion]:
    d = _versions_dir(doc_id, table_index)
    if not d.exists():
        return []
    out: list[TableVersion] = []
    for p in d.iterdir():
        if _VERSION_RE.match(p.name):
            v = _read_version_file(doc_id, table_index, p)
            if v is not None:
                out.append(v)
    out.sort(key=lambda v: v.version)
    return out


def list_versions(doc_id: str, table_index: int) -> TableLineage:
    """Full lineage for a table: v0 original followed by every correction."""
    original = base_table(doc_id, table_index)  # raises DocumentNotFound/TableNotFound
    versions = [original, *_correction_versions(doc_id, table_index)]
    return TableLineage(doc_id=doc_id, table_index=table_index, versions=tuple(versions))


def current_table(doc_id: str, table_index: int) -> TableVersion:
    """The effective (latest) version of a table — correction if any, else original."""
    return list_versions(doc_id, table_index).current


def _validate_rows(rows: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(rows, list) or not rows:
        raise InvalidRows("rows must be a non-empty list of rows")
    grid: list[tuple[str, ...]] = []
    for row in rows:
        if not isinstance(row, list):
            raise InvalidRows("each row must be a list of cells")
        grid.append(tuple("" if c is None else str(c) for c in row))
    if not any(any(cell.strip() for cell in r) for r in grid):
        raise InvalidRows("corrected grid is entirely empty")
    return tuple(grid)


def append_correction(
    doc_id: str,
    table_index: int,
    rows: Any,
    *,
    reason: str = "",
    author: str = "",
) -> TableVersion:
    """Persist a manual correction as a **new version** (original untouched).

    Validates the grid, computes the next version number after the highest
    existing one, and writes ``vNNN.json`` tagged ``corrected=true`` /
    ``parser_used="manual"``. Returns the new :class:`TableVersion`. Raises
    :class:`DocumentNotFound` / :class:`TableNotFound` for unknown targets and
    :class:`InvalidRows` for a malformed grid.
    """
    original = base_table(doc_id, table_index)  # validates doc + table existence
    grid = _validate_rows(rows)
    existing = _correction_versions(doc_id, table_index)
    next_version = (existing[-1].version + 1) if existing else 1

    record = TableVersion(
        doc_id=doc_id,
        table_index=table_index,
        version=next_version,
        rows=grid,
        page=original.page,
        parser_used="manual",
        corrected=True,
        reason=reason.strip(),
        author=author.strip(),
        created_at=int(time.time()),
        base_parser=original.base_parser,
    )

    out_dir = _versions_dir(doc_id, table_index)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "doc_id": doc_id,
        "table_index": table_index,
        "version": next_version,
        "rows": [list(r) for r in grid],
        "page": original.page,
        "parser_used": "manual",
        "corrected": True,
        "reason": record.reason,
        "author": record.author,
        "created_at": record.created_at,
        "base_parser": original.base_parser,
    }
    (out_dir / f"v{next_version:03d}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return record
