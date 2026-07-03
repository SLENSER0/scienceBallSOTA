"""Asset materialization metadata — метаданные материализации ассета (§9.8).

When a data asset is (re)materialised, the run emits a small bundle of facts a
catalog or observability layer can attach to that materialisation: which asset
it was, how many rows/nodes/edges it produced, where the artifacts live, and the
provenance handles (extraction run, schema version, partition key). This module
models that bundle as a frozen, JSON-serialisable value with no store or
scheduler dependency.

* :class:`MaterializationMetadata` — the immutable record with
  :meth:`MaterializationMetadata.as_dict` emitting namespaced keys and omitting
  ``None`` provenance fields («пустые поля не публикуем»).
* :func:`build_metadata` — keyword-friendly constructor with safe defaults.
* :func:`merge_counts` — sum two count maps, adding overlapping keys.
* :func:`total_count` — sum of all count values in a record.

Everything is a pure function of its inputs and side-effect free.

Public API:

* :class:`MaterializationMetadata` — frozen record with
  :meth:`MaterializationMetadata.as_dict`.
* :func:`build_metadata` — build a :class:`MaterializationMetadata`.
* :func:`merge_counts` — additive merge of two count maps.
* :func:`total_count` — total of all counts in a record.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

__all__ = [
    "MaterializationMetadata",
    "build_metadata",
    "merge_counts",
    "total_count",
]


@dataclass(frozen=True, slots=True)
class MaterializationMetadata:
    """Immutable materialization record — неизменяемая запись материализации (§9.8).

    ``counts`` maps a named quantity (``"nodes"``, ``"edges"``, ``"rows"``, ...)
    to a non-negative integer produced by the run. ``artifact_uris`` lists where
    the outputs landed. The remaining fields are optional provenance handles;
    when ``None`` they are omitted from :meth:`as_dict` output.
    """

    asset_key: str
    counts: Mapping[str, int] = field(default_factory=dict)
    artifact_uris: tuple[str, ...] = ()
    extraction_run_id: str | None = None
    schema_version: str | None = None
    partition_key: str | None = None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — запись как словарь (§9.8).

        The always-present fields (``asset_key``, ``counts``, ``artifact_uris``)
        are emitted under their own namespaced field keys; ``None`` provenance
        fields are omitted entirely, never emitted as ``null``.
        """
        out: dict[str, object] = {
            "asset_key": self.asset_key,
            "counts": dict(self.counts),
            "artifact_uris": list(self.artifact_uris),
        }
        optional: dict[str, str | None] = {
            "extraction_run_id": self.extraction_run_id,
            "schema_version": self.schema_version,
            "partition_key": self.partition_key,
        }
        for key, value in optional.items():
            if value is not None:
                out[key] = value
        return out


def build_metadata(
    asset_key: str,
    *,
    counts: Mapping[str, int] | None = None,
    artifact_uris: tuple[str, ...] = (),
    extraction_run_id: str | None = None,
    schema_version: str | None = None,
    partition_key: str | None = None,
) -> MaterializationMetadata:
    """Build a materialization record — собрать запись материализации (§9.8).

    ``counts`` defaults to an empty map. All values are copied defensively so
    the returned record does not alias the caller's inputs.
    """
    return MaterializationMetadata(
        asset_key=asset_key,
        counts=dict(counts) if counts is not None else {},
        artifact_uris=tuple(artifact_uris),
        extraction_run_id=extraction_run_id,
        schema_version=schema_version,
        partition_key=partition_key,
    )


def merge_counts(a: Mapping[str, int], b: Mapping[str, int]) -> dict[str, int]:
    """Additively merge two count maps — сложить две карты счётчиков (§9.8).

    Overlapping keys are summed; keys unique to either side are carried through.
    Neither input is mutated.
    """
    merged: dict[str, int] = dict(a)
    for key, value in b.items():
        merged[key] = merged.get(key, 0) + value
    return merged


def total_count(md: MaterializationMetadata) -> int:
    """Sum of all counts — суммарное число по всем счётчикам (§9.8)."""
    return sum(md.counts.values())
