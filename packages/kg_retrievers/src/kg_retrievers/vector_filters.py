"""Qdrant-style payload filters — embedded, pure-python (§4.5).

§4.5 specifies structured **payload filters** (фильтры по полезной нагрузке) over
vector hits so a search can be constrained by scalar metadata (year, material,
grade, retraction flags…) without a running Qdrant server. On the **server
profile** these translate to a ``qdrant-client`` ``Filter``; on the **embedded
profile** we cannot depend on the client, so this module re-implements the same
semantics locally and offers :func:`to_qdrant` as the one-way bridge to the
server JSON shape.

A :class:`Filter` is a frozen dataclass grouping :class:`FieldCondition` clauses
into three lists that mirror Qdrant exactly:

* ``must``     — every clause must match (logical **AND**, конъюнкция);
* ``should``   — at least one clause must match when the list is non-empty
  (logical **OR**, дизъюнкция); an empty ``should`` imposes nothing;
* ``must_not`` — no clause may match (negation, отрицание).

Each :class:`FieldCondition` carries one operator over one payload field:

* ``eq``     — field equals a scalar (Qdrant ``match.value``);
* ``in``     — field intersects a value set (Qdrant ``match.any``);
* ``range``  — numeric ``gte``/``lte`` bounds, inclusive (Qdrant ``range``);
* ``exists`` — field is present / absent (Qdrant ``values_count`` / ``is_empty``).

Payload values may be scalars or arrays; an array field matches a clause when
**any** of its elements does, matching Qdrant's multi-value semantics. Missing,
``None`` and empty-list fields all read as *absent* (пусто). Everything is
deterministic and dependency-free.

:func:`build_filter` is the ergonomic constructor. Bare keyword arguments (plus
an optional ``must=`` dict) form the ``must`` group; ``should=`` and
``must_not=`` dicts form the other two. Field/operator pairs use a ``__`` suffix
lookup (``field__in``, ``field__gte``, ``field__lte``, ``field__exists``); a bare
``field=value`` means ``eq``. Two range bounds on one field
(``year__gte=…, year__lte=…``) merge into a single :class:`FieldCondition`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Lookup suffixes recognised after a trailing ``__`` in :func:`build_filter`
# keys; anything else (or no suffix) is an equality (``eq``) lookup.
_LOOKUP_OPS: frozenset[str] = frozenset({"in", "gte", "lte", "exists"})

# Reserved top-level keyword names that select a boolean group rather than a
# payload field (a field literally so named must be passed inside a group dict).
_GROUPS: tuple[str, ...] = ("must", "should", "must_not")


def _is_number(value: Any) -> bool:
    """True for a real numeric value; ``bool`` is excluded (§4.5).

    Range bounds only order genuine numbers — treating ``True`` as ``1`` would
    silently pull booleans into numeric comparisons.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _payload_values(payload: dict, field: str) -> list[Any]:
    """Normalise ``payload[field]`` to a list of present values (§4.5).

    Missing keys, ``None`` and empty lists all yield ``[]`` (the field reads as
    absent, пусто). A scalar becomes a one-element list; a list/tuple is returned
    element-wise so multi-value fields match a clause when any element does.
    """
    if field not in payload:
        return []
    raw = payload[field]
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [v for v in raw if v is not None]
    return [raw]


@dataclass(frozen=True)
class FieldCondition:
    """One operator over one payload field (§4.5).

    ``op`` is one of ``"eq"``, ``"in"``, ``"range"``, ``"exists"``. Only the
    fields relevant to ``op`` are populated: ``value`` (eq scalar / exists flag),
    ``values`` (in set), ``gte``/``lte`` (range bounds). Frozen and hashable.
    """

    field: str
    op: str
    value: Any = None
    values: tuple[Any, ...] = ()
    gte: float | None = None
    lte: float | None = None

    def matches(self, payload: dict) -> bool:
        """Evaluate this single condition against ``payload`` (§4.5)."""
        present = _payload_values(payload, self.field)
        if self.op == "eq":
            return self.value in present
        if self.op == "in":
            allowed = self.values
            return any(v in allowed for v in present)
        if self.op == "range":
            return self._range_match(present)
        if self.op == "exists":
            return bool(present) == bool(self.value)
        raise ValueError(f"unknown op: {self.op!r}")

    def _range_match(self, present: list[Any]) -> bool:
        """Inclusive numeric ``gte``/``lte`` test over any present value (§4.5)."""
        for v in present:
            if not _is_number(v):
                continue
            if self.gte is not None and v < self.gte:
                continue
            if self.lte is not None and v > self.lte:
                continue
            return True
        return False

    def to_qdrant(self) -> dict:
        """Emit this clause in the ``qdrant-client`` condition JSON shape (§4.5).

        ``eq`` → ``match.value``; ``in`` → ``match.any``; ``range`` →
        ``range.{gte,lte}``; ``exists`` present → ``values_count.gte == 1``, absent
        → an ``is_empty`` condition.
        """
        if self.op == "eq":
            return {"key": self.field, "match": {"value": self.value}}
        if self.op == "in":
            return {"key": self.field, "match": {"any": list(self.values)}}
        if self.op == "range":
            bounds: dict[str, Any] = {}
            if self.gte is not None:
                bounds["gte"] = self.gte
            if self.lte is not None:
                bounds["lte"] = self.lte
            return {"key": self.field, "range": bounds}
        if self.op == "exists":
            if self.value:
                return {"key": self.field, "values_count": {"gte": 1}}
            return {"is_empty": {"key": self.field}}
        raise ValueError(f"unknown op: {self.op!r}")

    def as_dict(self) -> dict:
        """Plain-dict view carrying only the operator's relevant fields (§4.5)."""
        out: dict[str, Any] = {"field": self.field, "op": self.op}
        if self.op == "eq":
            out["value"] = self.value
        elif self.op == "in":
            out["values"] = list(self.values)
        elif self.op == "range":
            out["gte"] = self.gte
            out["lte"] = self.lte
        elif self.op == "exists":
            out["present"] = bool(self.value)
        return out


@dataclass(frozen=True)
class Filter:
    """Boolean grouping of :class:`FieldCondition` clauses (§4.5).

    ``must`` is an AND, ``must_not`` a negated AND, ``should`` an OR that only
    constrains when non-empty. An all-empty filter matches every payload. Frozen
    and hashable (each group is a tuple).
    """

    must: tuple[FieldCondition, ...] = ()
    should: tuple[FieldCondition, ...] = ()
    must_not: tuple[FieldCondition, ...] = ()

    def matches(self, payload: dict) -> bool:
        """True iff ``payload`` satisfies must ∧ ¬must_not ∧ (should? ∨) (§4.5)."""
        if not all(c.matches(payload) for c in self.must):
            return False
        if any(c.matches(payload) for c in self.must_not):
            return False
        # An empty ``should`` imposes nothing; otherwise at least one must match.
        return not self.should or any(c.matches(payload) for c in self.should)

    def to_qdrant(self) -> dict:
        """Emit the ``qdrant-client`` ``Filter`` JSON shape (§4.5).

        Only non-empty groups appear, so an empty filter renders as ``{}`` — the
        Qdrant match-everything filter.
        """
        out: dict[str, list[dict]] = {}
        for name in _GROUPS:
            group: tuple[FieldCondition, ...] = getattr(self, name)
            if group:
                out[name] = [c.to_qdrant() for c in group]
        return out

    def as_dict(self) -> dict:
        """Plain-dict view of all three groups (§4.5)."""
        return {name: [c.as_dict() for c in getattr(self, name)] for name in _GROUPS}


def _split_lookup(key: str) -> tuple[str, str]:
    """Split ``field__op`` into ``(field, op)``; bare keys are ``eq`` (§4.5)."""
    if "__" in key:
        base, _, suffix = key.rpartition("__")
        if suffix in _LOOKUP_OPS and base:
            return base, suffix
    return key, "eq"


def _coerce_values(value: Any) -> tuple[Any, ...]:
    """Coerce an ``in`` right-hand side to a value tuple (§4.5).

    A list/tuple/set is taken element-wise; a bare scalar (incl. a ``str``, which
    must *not* be split into characters) becomes a one-element tuple.
    """
    if isinstance(value, (list, tuple, set)):
        return tuple(value)
    return (value,)


def _build_conditions(spec: dict[str, Any]) -> tuple[FieldCondition, ...]:
    """Parse one group's lookup dict into ordered :class:`FieldCondition` s (§4.5).

    ``eq``/``in``/``exists`` clauses keep first-seen order; ``gte``/``lte`` on the
    same field merge into a single ``range`` clause appended after them.
    """
    conditions: list[FieldCondition] = []
    ranges: dict[str, dict[str, Any]] = {}
    for key, value in spec.items():
        field, op = _split_lookup(key)
        if op == "eq":
            conditions.append(FieldCondition(field=field, op="eq", value=value))
        elif op == "in":
            conditions.append(FieldCondition(field=field, op="in", values=_coerce_values(value)))
        elif op == "exists":
            conditions.append(FieldCondition(field=field, op="exists", value=bool(value)))
        else:  # "gte" / "lte"
            ranges.setdefault(field, {})[op] = value
    for field, bounds in ranges.items():
        conditions.append(
            FieldCondition(field=field, op="range", gte=bounds.get("gte"), lte=bounds.get("lte"))
        )
    return tuple(conditions)


def build_filter(**conds: Any) -> Filter:
    """Build a :class:`Filter` from keyword lookups (§4.5).

    Bare keywords and an optional ``must=`` dict populate the ``must`` group;
    ``should=`` and ``must_not=`` dicts populate their groups. Each group value is
    a ``{lookup: value}`` dict using ``__``-suffixed operators
    (``field__in``/``__gte``/``__lte``/``__exists``); a bare ``field=value`` is an
    equality. Example::

        build_filter(
            material="steel",
            year__gte=2000,
            year__lte=2020,
            should={"grade__in": ["A", "B"]},
            must_not={"deleted": True},
        )
    """
    must_spec: dict[str, Any] = dict(conds.pop("must", None) or {})
    should_spec: dict[str, Any] = dict(conds.pop("should", None) or {})
    must_not_spec: dict[str, Any] = dict(conds.pop("must_not", None) or {})
    must_spec.update(conds)  # remaining bare kwargs fold into the must group
    return Filter(
        must=_build_conditions(must_spec),
        should=_build_conditions(should_spec),
        must_not=_build_conditions(must_not_spec),
    )


def matches(filter: Filter, payload: dict) -> bool:
    """Evaluate ``filter`` against ``payload`` (§4.5). See :meth:`Filter.matches`."""
    return filter.matches(payload)


def to_qdrant(filter: Filter) -> dict:
    """Render ``filter`` as ``qdrant-client`` JSON (§4.5). See :meth:`Filter.to_qdrant`."""
    return filter.to_qdrant()
