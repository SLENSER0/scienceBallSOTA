"""Property physical-range catalog YAML loader (§7.13).

Loads the externalized property range catalog
(``resources/property_ranges.yaml``) — canonical ``property_id`` ->
``hard_min`` / ``hard_max`` (absolute physical bounds) + ``typical_min`` /
``typical_max`` (ordinary engineering band) + canonical ``unit`` — and exposes
range lookup and a hard-range membership test. A value outside the hard range
is non-physical (extraction or unit error); a value inside the hard range but
outside the typical band is plausible-but-flaggable. ``property_id`` values
mirror :mod:`kg_extractors.property_vocab`, keeping extraction, unit-gating,
and range-checking aligned.

Каталог физических диапазонов свойств: жёсткие границы + типичная полоса (§7.13).

Pure python + PyYAML — no other dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "resources" / "property_ranges.yaml"


@dataclass(frozen=True)
class PropertyRange:
    """One property's physical range (§7.13): hard bounds + typical band + unit."""

    property_id: str
    hard_min: float
    hard_max: float
    typical_min: float
    typical_max: float
    unit: str

    def as_dict(self) -> dict[str, object]:
        return {
            "property_id": self.property_id,
            "hard_min": self.hard_min,
            "hard_max": self.hard_max,
            "typical_min": self.typical_min,
            "typical_max": self.typical_max,
            "unit": self.unit,
        }

    def hard_range(self) -> tuple[float, float]:
        """``(hard_min, hard_max)`` — absolute physical bounds."""
        return (self.hard_min, self.hard_max)

    def typical_band(self) -> tuple[float, float]:
        """``(typical_min, typical_max)`` — ordinary engineering band."""
        return (self.typical_min, self.typical_max)

    def contains(self, value: float) -> bool:
        """True iff *value* lies within the inclusive hard range."""
        return self.hard_min <= float(value) <= self.hard_max


@dataclass(frozen=True)
class PropertyRanges:
    """Immutable property physical-range catalog with range lookup (§7.13)."""

    ranges: tuple[PropertyRange, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for r in self.ranges:
            if not r.property_id:
                raise ValueError("property ranges: empty property_id")
            if r.property_id in seen:
                raise ValueError(f"property ranges: duplicate property_id {r.property_id!r}")
            if r.hard_min > r.hard_max:
                raise ValueError(f"property ranges: hard_min > hard_max for {r.property_id!r}")
            seen.add(r.property_id)
        # Build id -> entry index without breaking frozen semantics.
        object.__setattr__(self, "_by_id", {r.property_id: r for r in self.ranges})

    def __len__(self) -> int:
        return len(self.ranges)

    def all_ids(self) -> tuple[str, ...]:
        """Canonical ``property_id`` values in file order (§7.13)."""
        return tuple(r.property_id for r in self.ranges)

    def entry(self, property_id: str) -> PropertyRange | None:
        """Return the :class:`PropertyRange` for *property_id*, or ``None``."""
        return self._by_id.get(property_id)  # type: ignore[attr-defined]

    def range_for(self, property_id: str) -> tuple[float, float] | None:
        """Hard ``(min, max)`` for *property_id*, or ``None`` for an unknown id."""
        entry = self.entry(property_id)
        return entry.hard_range() if entry is not None else None

    def typical_for(self, property_id: str) -> tuple[float, float] | None:
        """Typical ``(min, max)`` band for *property_id*, or ``None`` if unknown."""
        entry = self.entry(property_id)
        return entry.typical_band() if entry is not None else None

    def unit_for(self, property_id: str) -> str | None:
        """Canonical unit for *property_id*, or ``None`` for an unknown id."""
        entry = self.entry(property_id)
        return entry.unit if entry is not None else None

    def in_hard_range(self, property_id: str, value: float) -> bool:
        """True iff *value* is within the inclusive hard range of *property_id*.

        Returns ``False`` for an unknown *property_id* (no bounds to satisfy).
        """
        entry = self.entry(property_id)
        return entry.contains(value) if entry is not None else False

    def in_typical_band(self, property_id: str, value: float) -> bool:
        """True iff *value* is within the inclusive typical band of *property_id*."""
        entry = self.entry(property_id)
        if entry is None:
            return False
        return entry.typical_min <= float(value) <= entry.typical_max

    def as_dict(self) -> dict[str, object]:
        return {"ranges": [r.as_dict() for r in self.ranges]}


def load_property_ranges(path: Path | str | None = None) -> PropertyRanges:
    """Load the property range catalog from YAML (§7.13).

    *path* defaults to ``resources/property_ranges.yaml`` next to this module.
    The YAML is a mapping of ``property_id`` -> range fields; file order is
    preserved so the catalog is deterministic.
    """
    p = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"property ranges: expected a mapping, got {type(raw).__name__}")
    ranges = tuple(
        PropertyRange(
            property_id=str(pid),
            hard_min=float(rec["hard_min"]),
            hard_max=float(rec["hard_max"]),
            typical_min=float(rec["typical_min"]),
            typical_max=float(rec["typical_max"]),
            unit=str(rec["unit"]),
        )
        for pid, rec in raw.items()
    )
    return PropertyRanges(ranges)


@lru_cache(maxsize=1)
def default_property_ranges() -> PropertyRanges:
    """Cached default property range catalog from the packaged YAML (§7.13)."""
    return load_property_ranges()


def range_for(property_id: str) -> tuple[float, float] | None:
    """Module-level hard ``(min, max)`` lookup on the default catalog (§7.13)."""
    return default_property_ranges().range_for(property_id)


def in_hard_range(property_id: str, value: float) -> bool:
    """Module-level hard-range membership test on the default catalog (§7.13)."""
    return default_property_ranges().in_hard_range(property_id, value)
