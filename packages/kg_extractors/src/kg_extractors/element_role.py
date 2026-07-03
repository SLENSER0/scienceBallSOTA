"""Element role classification for compositions (§6.4).

:mod:`composition_extractor` yields per-element fractions and a *base* element,
but downstream typing needs each element bucketed into a **role** — is it the
matrix (``base``), an alloying element (``major``), a minor addition
(``minor``), or an incidental impurity (``trace``)? This module supplies that
banding.

- :class:`ElementRole` — one element's ``(element, fraction, role)`` with
  :meth:`~ElementRole.as_dict`; ``role`` is one of ``base``/``major``/``minor``
  /``trace``.
- :func:`classify_roles` — band a ``{element: fraction}`` mapping. The explicit
  *base* (or, absent that, the max-fraction element) is tagged ``base``; every
  other element is banded by fraction against ``major_min`` / ``minor_min``.
  Entries come back sorted by fraction descending, with the base first.

Классификация роли элемента в составе: база/основной/малый/следовой (§6.4).

Pure python — no external dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# Role band labels, richest → poorest.
ROLE_BASE = "base"
ROLE_MAJOR = "major"
ROLE_MINOR = "minor"
ROLE_TRACE = "trace"

# Default banding thresholds (percent): >= major_min → major, >= minor_min →
# minor, otherwise trace. The base element is exempt from these bands.
DEFAULT_MAJOR_MIN: float = 1.0
DEFAULT_MINOR_MIN: float = 0.1


@dataclass(frozen=True)
class ElementRole:
    """One element's classified role within a composition (§6.4).

    ``role`` is one of ``base`` / ``major`` / ``minor`` / ``trace``.
    """

    element: str
    fraction: float
    role: str

    def as_dict(self) -> dict[str, object]:
        return {
            "element": self.element,
            "fraction": self.fraction,
            "role": self.role,
        }


def _band(fraction: float, major_min: float, minor_min: float) -> str:
    """Band a non-base element's fraction into major/minor/trace (§6.4)."""
    if fraction >= major_min:
        return ROLE_MAJOR
    if fraction >= minor_min:
        return ROLE_MINOR
    return ROLE_TRACE


def classify_roles(
    fractions: Mapping[str, float],
    base: str | None = None,
    major_min: float = DEFAULT_MAJOR_MIN,
    minor_min: float = DEFAULT_MINOR_MIN,
) -> list[ElementRole]:
    """Classify each element's role in a composition (§6.4).

    The base element — *base* when given (and present), otherwise the element
    with the greatest fraction — is tagged ``base`` regardless of its fraction.
    Every other element is banded: ``>= major_min`` → ``major``,
    ``>= minor_min`` → ``minor``, else ``trace``. The returned list is sorted by
    fraction descending, but the base element is always placed first.

    An empty mapping yields an empty list.
    """
    if not fractions:
        return []
    # Coerce to floats once and rank by fraction descending (stable on ties).
    items = sorted(
        ((str(el), float(frac)) for el, frac in fractions.items()),
        key=lambda pair: pair[1],
        reverse=True,
    )
    # Resolve the base element: explicit choice wins when it exists, else the
    # max-fraction element (first after the descending sort).
    known = {el for el, _ in items}
    base_element = base if (base is not None and base in known) else items[0][0]
    # Emit the base first, then the remaining elements in fraction order.
    ordered: list[tuple[str, float]] = [p for p in items if p[0] == base_element]
    ordered += [p for p in items if p[0] != base_element]
    roles: list[ElementRole] = []
    for element, fraction in ordered:
        role = ROLE_BASE if element == base_element else _band(fraction, major_min, minor_min)
        roles.append(ElementRole(element=element, fraction=fraction, role=role))
    return roles
