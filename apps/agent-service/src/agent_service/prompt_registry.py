"""Versioned prompt registry — repeatable execution (§13.1 / §13.23).

§13.1 / §13.23 mandate that every LLM node prompt (intent few-shot, query
planner, verifier/critic, answer synthesis) be **versioned and pinned** so a
given agent run is reproducible («повторяемое исполнение»): the same registry
fingerprint ⇒ the same prompt bodies ⇒ the same deterministic behaviour up to
model sampling. Until now there was no prompts registry (no ``prompts/`` dir).

This module is that registry. A :class:`PromptTemplate` is a frozen
``(name, version, template)`` triple whose :meth:`~PromptTemplate.render` does
plain ``str.format`` substitution over ``{placeholder}`` slots. :data:`REGISTRY`
seeds the four spec-named node prompts (``intent_classifier`` / ``query_planner``
/ ``verifier`` / ``answer_synthesizer``), each pinned to a version (``v1``).

* :func:`get_prompt` — fetch a template by name (raises ``KeyError`` if unknown).
* :func:`active_versions` — ``name → version`` map for the whole registry.
* :func:`versions_fingerprint` — sha256 over the sorted ``name:version`` lines,
  a stable 64-hex digest identifying *which* prompt set is pinned. Two registries
  with the same name/version pairs share a fingerprint regardless of insertion
  order (детерминированный отпечаток набора промптов).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    """A pinned, versioned node prompt (§13.23 «версионированный промпт»).

    Fields
    ------
    name
        Registry key / node name (e.g. ``"verifier"``).
    version
        Pinned version tag (e.g. ``"v1"``) — bump on any body change.
    template
        The prompt body with ``{placeholder}`` slots for :meth:`render`.
    """

    name: str
    version: str
    template: str

    def render(self, **kwargs: object) -> str:
        """Substitute ``{placeholder}`` slots via ``str.format`` (подстановка)."""
        return self.template.format(**kwargs)

    def as_dict(self) -> dict[str, str]:
        """Full structured view for logging / provenance (§7.3)."""
        return {"name": self.name, "version": self.version, "template": self.template}


# --- builtin registry: the four §13.1 node prompts, pinned to v1 -------------
# Each body is a ``{...}``-placeholder template; bump ``version`` on any edit.
_BUILTINS: tuple[PromptTemplate, ...] = (
    PromptTemplate(
        name="intent_classifier",
        version="v1",
        template=(
            "Classify the user question into one of the nine §7.5 intents.\n"
            "Few-shot examples:\n{examples}\n\n"
            "Question: {question}\n"
            "Intent:"
        ),
    ),
    PromptTemplate(
        name="query_planner",
        version="v1",
        template=(
            "Plan retrieval for intent '{intent}'.\n"
            "Question: {question}\n"
            "Available tools: {tools}\n"
            "Emit an ordered tool plan as JSON."
        ),
    ),
    PromptTemplate(
        name="verifier",
        version="v1",
        template=(
            "You are a verifier/critic. Check the draft answer against the "
            "evidence.\n"
            "Evidence:\n{evidence}\n\n"
            "Draft answer:\n{answer}\n\n"
            "List unsupported claims or reply OK."
        ),
    ),
    PromptTemplate(
        name="answer_synthesizer",
        version="v1",
        template=(
            "Synthesize a grounded answer for the question using only the "
            "evidence.\n"
            "Question: {question}\n"
            "Evidence:\n{evidence}\n\n"
            "Answer with inline citations:"
        ),
    ),
)

# Insertion-ordered registry keyed by prompt name (§13.23 active prompt set).
REGISTRY: dict[str, PromptTemplate] = {tpl.name: tpl for tpl in _BUILTINS}


def get_prompt(name: str) -> PromptTemplate:
    """Return the pinned :class:`PromptTemplate` for ``name`` (§13.23).

    Raises
    ------
    KeyError
        If ``name`` is not a registered prompt (неизвестный промпт).
    """
    return REGISTRY[name]


def active_versions(registry: Mapping[str, PromptTemplate] | None = None) -> dict[str, str]:
    """Return the ``name → version`` map for every registered prompt (§13.23)."""
    reg = REGISTRY if registry is None else registry
    return {name: tpl.version for name, tpl in reg.items()}


def versions_fingerprint(registry: Mapping[str, PromptTemplate] | None = None) -> str:
    """Return a stable 64-hex sha256 over sorted ``name:version`` lines (§13.23).

    The digest identifies *which* prompt set is pinned. It is order-independent
    (lines are sorted before hashing), so two registries with identical
    name/version pairs share a fingerprint (детерминированный отпечаток набора).
    """
    reg = REGISTRY if registry is None else registry
    lines = sorted(f"{name}:{tpl.version}" for name, tpl in reg.items())
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
