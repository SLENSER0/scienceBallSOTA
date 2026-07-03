"""Per-field source provenance for the §6.13 rules+ML+LLM merge.

RU: слияние rules+ML+LLM с записью источника каждого поля — EN: rules+ML+LLM
merge with per-field source provenance.

``merge_extractions`` fuses facts and preserves evidence, but it does not record
*which* extraction layer supplied each field, nor does it flag when two layers
disagree.  §6.13 requires "запись источника каждого поля" (recording the source
of every field).  This module resolves each field to the highest-priority layer
that offered a value, keeps the losing candidates as ``alternatives`` and raises
a ``conflict`` flag when the layers proposed *distinct* values.

Priority is layer-name based (default ``('rule', 'llm', 'ml')``): a rule beats an
LLM which beats an ML guess.  Unknown layer names rank *after* every named layer
so an unexpected producer never silently overrides a trusted one (§6.13).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Default cross-layer priority — rule wins over LLM wins over ML (§6.13).
DEFAULT_PRIORITY: tuple[str, ...] = ("rule", "llm", "ml")


def _rank(layer: str, priority: tuple[str, ...]) -> int:
    """Rank ``layer`` by ``priority``; unknown layers sort last (§6.13).

    Named layers keep their position in ``priority``; any layer absent from the
    tuple is pushed past every named one so an unexpected producer cannot outrank
    a trusted layer.
    """
    try:
        return priority.index(layer)
    except ValueError:
        return len(priority)


@dataclass(frozen=True)
class FieldProvenance:
    """Provenance of a single resolved field (§6.13).

    RU: происхождение поля — EN: field provenance.

    Attributes
    ----------
    field:
        Name of the resolved field.
    value:
        The winning value, taken from ``source_layer``.
    source_layer:
        Layer that supplied ``value`` (the highest-priority contributor).
    conflict:
        ``True`` when the layers proposed at least two *distinct* values.
    alternatives:
        Losing ``(layer, value)`` pairs, in the order they were supplied.
    """

    field: str
    value: object
    source_layer: str
    conflict: bool
    alternatives: tuple[tuple[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        """Return a plain, JSON-friendly mapping of this provenance (§6.13)."""
        return {
            "field": self.field,
            "value": self.value,
            "source_layer": self.source_layer,
            "conflict": self.conflict,
            "alternatives": self.alternatives,
        }


def resolve_field(
    field: str,
    layer_values: list[tuple[str, object]],
    priority: tuple[str, ...] = DEFAULT_PRIORITY,
) -> FieldProvenance:
    """Resolve one field across layers, recording its source (§6.13).

    RU: разрешение поля по слоям — EN: resolve a field across layers.

    The highest-priority layer wins (``priority``; unknown layers rank last).
    ``conflict`` is ``True`` when the supplied values are not all equal.  Every
    ``(layer, value)`` pair other than the winning one is kept in
    ``alternatives``, preserving the input order.

    Parameters
    ----------
    field:
        Name of the field being resolved.
    layer_values:
        ``(layer, value)`` pairs, one per layer that proposed a value.  Must be
        non-empty.
    priority:
        Layer-name priority, most trusted first.

    Raises
    ------
    ValueError:
        If ``layer_values`` is empty — there is nothing to resolve.
    """
    if not layer_values:
        raise ValueError(f"no layer values supplied for field {field!r}")

    # Stable, priority-then-input-order selection of the winner.
    winner_index = min(
        range(len(layer_values)),
        key=lambda i: (_rank(layer_values[i][0], priority), i),
    )
    win_layer, win_value = layer_values[winner_index]

    distinct_values = {value for _layer, value in layer_values}
    conflict = len(distinct_values) > 1

    alternatives = tuple(pair for i, pair in enumerate(layer_values) if i != winner_index)
    return FieldProvenance(
        field=field,
        value=win_value,
        source_layer=win_layer,
        conflict=conflict,
        alternatives=alternatives,
    )


def track_provenance(
    candidates: Mapping[str, list[tuple[str, object]]],
    priority: tuple[str, ...] = DEFAULT_PRIORITY,
) -> dict[str, FieldProvenance]:
    """Resolve every field's provenance for the §6.13 merge.

    RU: отслеживание источника всех полей — EN: track provenance of all fields.

    Applies :func:`resolve_field` to each ``field -> [(layer, value), ...]``
    entry, returning a mapping from field name to its :class:`FieldProvenance`.
    """
    return {
        field: resolve_field(field, layer_values, priority)
        for field, layer_values in candidates.items()
    }
