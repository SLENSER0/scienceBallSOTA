"""Text2Cypher schema grounding — LLM prompt context + label/rel allowlist (§12.10).

§12.10 requires that generated Cypher be *grounded* in the canonical graph schema:
the LLM is shown exactly which node labels and relationship types (and, optionally,
which properties per label) it may use, and any Cypher it produces is validated so
labels/relationships outside that allowlist are rejected.

Заземление схемы. This module is deliberately distinct from the graph-service
``cypher_guard._check_allowlist`` (a regex-based hard reject at query time): it
serves the *generation* side by producing

* a deterministic, human-readable :class:`SchemaContext.prompt` string that lists the
  allowed labels, allowed relationships and (when supplied) per-label properties, for
  splicing into the Text2Cypher system prompt; and
* a structured :func:`validate_against_schema` that returns a **sorted list of
  violation messages** (not a bool) so callers can surface every out-of-schema label
  or relationship at once.

Everything here is pure stdlib and deterministic — labels/relationships are stored
sorted and deduplicated, so building the same context twice yields identical prompts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaContext:
    """Canonical schema allowlist + its rendered grounding prompt (§12.10).

    - ``labels`` — allowed node labels, stored sorted and deduplicated;
    - ``relationships`` — allowed relationship types, stored sorted and deduplicated;
    - ``prompt`` — deterministic multi-line grounding string listing the allowed
      labels, relationships and (when provided) per-label properties.
    """

    labels: tuple[str, ...]
    relationships: tuple[str, ...]
    prompt: str

    def as_dict(self) -> dict:
        return {
            "labels": list(self.labels),
            "relationships": list(self.relationships),
            "prompt": self.prompt,
        }


def _sorted_unique(names: list[str]) -> tuple[str, ...]:
    """Deduplicate and sort ``names`` for a stable, canonical allowlist (§12.10)."""
    return tuple(sorted(set(names)))


def _render_prompt(
    labels: tuple[str, ...],
    relationships: tuple[str, ...],
    properties: dict[str, list[str]] | None,
) -> str:
    """Render the deterministic grounding prompt for the Text2Cypher LLM (§12.10).

    Lists ``Allowed labels:`` then ``Allowed relationships:`` (comma-joined, in the
    already-sorted order), and — when ``properties`` is given — one ``Properties of
    <label>:`` line per label that carries properties, so the model sees exactly which
    property names are queryable.
    """
    lines: list[str] = [
        "Allowed labels: " + ", ".join(labels),
        "Allowed relationships: " + ", ".join(relationships),
    ]
    if properties:
        for label in sorted(properties):
            props = sorted(set(properties[label]))
            if props:
                lines.append(f"Properties of {label}: " + ", ".join(props))
    return "\n".join(lines)


def build_context(
    labels: list[str],
    relationships: list[str],
    properties: dict[str, list[str]] | None = None,
) -> SchemaContext:
    """Build a :class:`SchemaContext` from an allowlist of labels/relationships (§12.10).

    Labels and relationships are stored **sorted and deduplicated**, and ``prompt`` is a
    deterministic multi-line string naming every allowed label and relationship (plus
    per-label properties when ``properties`` is supplied). Building the same context
    twice yields an identical prompt.
    """
    label_tuple = _sorted_unique(labels)
    rel_tuple = _sorted_unique(relationships)
    prompt = _render_prompt(label_tuple, rel_tuple, properties)
    return SchemaContext(labels=label_tuple, relationships=rel_tuple, prompt=prompt)


def validate_against_schema(
    labels_used: set[str],
    rels_used: set[str],
    ctx: SchemaContext,
) -> list[str]:
    """Flag used labels/relationships absent from ``ctx``'s allowlist (§12.10).

    Returns a **sorted** list of human-readable violation messages — one per used label
    not in ``ctx.labels`` and one per used relationship not in ``ctx.relationships``.
    An empty list means the used labels/relationships are fully grounded in the schema.
    """
    allowed_labels = set(ctx.labels)
    allowed_rels = set(ctx.relationships)
    violations: list[str] = []
    for label in labels_used:
        if label not in allowed_labels:
            violations.append(f"Label '{label}' is not in the allowed schema")
    for rel in rels_used:
        if rel not in allowed_rels:
            violations.append(f"Relationship '{rel}' is not in the allowed schema")
    return sorted(violations)
