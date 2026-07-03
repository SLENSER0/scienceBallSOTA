"""Governance tag catalog — каталог тегов управления данными (§10.3/§10.11).

Every artefact in the graph carries a small, fixed set of *governance tags* that
describe how it may be used. A tag is a ``facet:value`` pair drawn from a closed
catalog («закрытый каталог фасетов»), so the vocabulary is deterministic and
cannot drift: unknown facets or values are rejected rather than silently stored.

The catalog per §10.3/§10.11:

* ``access``  — visibility class: ``public`` / ``internal`` / ``restricted``.
* ``quality`` — curation state: ``verified`` / ``pending``.
* ``pii``     — personal-data marker: ``none`` (materials domain carries no PII).
* ``domain``  — subject domain: ``materials``.

Everything here is pure and side-effect free: no I/O, no wall-clock, no globals
mutated at call time. Tags are frozen dataclasses, so callers cannot mutate a tag
after construction.

Public API:

* :class:`GovernanceTag`  — frozen ``{facet, value}`` record.
* :data:`ACCESS_VALUES` / :data:`QUALITY_VALUES` / :data:`PII_VALUES` /
  :data:`DOMAIN_VALUES` — allowed values per facet.
* :func:`access_tag` / :func:`quality_tag` — build a tag for a facet, validated.
* :func:`parse_tag`      — parse ``"facet:value"`` → :class:`GovernanceTag`.
* :func:`is_valid_tag`   — is ``"facet:value"`` in the catalog? → ``bool``.
* :func:`normalize_tags` — dedup + sort a bag of tag strings.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "ACCESS_VALUES",
    "QUALITY_VALUES",
    "PII_VALUES",
    "DOMAIN_VALUES",
    "FACET_VALUES",
    "GovernanceTag",
    "access_tag",
    "quality_tag",
    "parse_tag",
    "is_valid_tag",
    "normalize_tags",
]


# --------------------------------------------------------------------------- #
# Catalog — каталог допустимых значений                                       #
# --------------------------------------------------------------------------- #

#: Allowed values for the ``access`` facet — класс видимости.
ACCESS_VALUES: tuple[str, ...] = ("public", "internal", "restricted")

#: Allowed values for the ``quality`` facet — состояние курирования.
QUALITY_VALUES: tuple[str, ...] = ("verified", "pending")

#: Allowed values for the ``pii`` facet — маркер персональных данных.
PII_VALUES: tuple[str, ...] = ("none",)

#: Allowed values for the ``domain`` facet — предметная область.
DOMAIN_VALUES: tuple[str, ...] = ("materials",)

#: Facet → allowed values — единая таблица «фасет → значения».
FACET_VALUES: dict[str, tuple[str, ...]] = {
    "access": ACCESS_VALUES,
    "quality": QUALITY_VALUES,
    "pii": PII_VALUES,
    "domain": DOMAIN_VALUES,
}


# --------------------------------------------------------------------------- #
# Tag record — запись тега                                                    #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class GovernanceTag:
    """A single governance tag — один тег управления (``facet:value``)."""

    facet: str
    value: str

    def as_dict(self) -> dict[str, str]:
        """Return a plain ``{facet, value}`` mapping — простое отображение."""
        return {"facet": self.facet, "value": self.value}

    def to_str(self) -> str:
        """Render as the canonical ``"facet:value"`` string — каноничная строка."""
        return f"{self.facet}:{self.value}"


# --------------------------------------------------------------------------- #
# Constructors — конструкторы тегов                                           #
# --------------------------------------------------------------------------- #


def _make_tag(facet: str, value: str) -> GovernanceTag:
    """Build a validated tag or raise :class:`ValueError` — построить с проверкой."""
    allowed = FACET_VALUES.get(facet)
    if allowed is None:
        raise ValueError(f"unknown governance facet: {facet!r}")
    if value not in allowed:
        raise ValueError(f"unknown {facet} value: {value!r} (allowed: {allowed})")
    return GovernanceTag(facet, value)


def access_tag(value: str) -> GovernanceTag:
    """Build an ``access:*`` tag — тег доступа; raises on unknown ``value``."""
    return _make_tag("access", value)


def quality_tag(value: str) -> GovernanceTag:
    """Build a ``quality:*`` tag — тег качества; raises on unknown ``value``."""
    return _make_tag("quality", value)


# --------------------------------------------------------------------------- #
# Parsing & validation — разбор и проверка                                    #
# --------------------------------------------------------------------------- #


def parse_tag(s: str) -> GovernanceTag:
    """Parse ``"facet:value"`` → :class:`GovernanceTag`, validated — разобрать строку.

    Raises :class:`ValueError` if the string is not exactly ``facet:value`` or the
    pair is not in the catalog.
    """
    facet, sep, value = s.partition(":")
    if not sep:
        raise ValueError(f"malformed governance tag (expected 'facet:value'): {s!r}")
    return _make_tag(facet, value)


def is_valid_tag(s: str) -> bool:
    """Return ``True`` iff ``s`` is a catalog ``"facet:value"`` tag — проверка тега."""
    try:
        parse_tag(s)
    except ValueError:
        return False
    return True


def normalize_tags(tags: Iterable[str]) -> tuple[GovernanceTag, ...]:
    """Dedup and sort tags by ``(facet, value)`` — нормализовать набор тегов.

    Each item must be a valid ``"facet:value"`` string; invalid items raise
    :class:`ValueError`. The result is deduplicated and sorted by facet then value.
    """
    parsed = {parse_tag(s) for s in tags}
    return tuple(sorted(parsed, key=lambda t: (t.facet, t.value)))
