"""§7.6/§13.15 разрешение кореференции в follow-up / follow-up coreference resolver.

:mod:`conversation_memory` keeps a ring of dialogue turns but never *rewrites* a
follow-up question — so "How does it change?" arrives at the planner with a dangling
``it`` and no idea what entity the previous turn was about. §7.6 (multi-turn) needs
that anaphor bound back to the carried-over entity.

This module is pure python (no store / no LLM). :func:`resolve_followup` takes the raw
``question`` plus the ``prior_entities`` surfaced by the previous turn (most-recent
first) and, when the question is anaphoric *and* names no explicit entity of its own,
carries over ``prior_entities[0]`` — appending it as a parenthetical and recording each
``(pronoun, entity)`` substitution. A question that already names an entity is returned
verbatim. Bilingual (RU/EN): pronoun/anaphor tables per language, tokenisation is
Unicode-aware so Cyrillic forms match. Every rule is deterministic and hand-checkable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Anaphoric pronouns per language (местоимения / pronouns). Base forms — оblique/declined
#: Russian forms (``ним``/``ней`` …) are folded in via :data:`_ANAPHOR_FORMS` below.
PRONOUNS: dict[str, tuple[str, ...]] = {
    "ru": ("он", "она", "оно", "это", "этот", "этого", "там", "его"),
    "en": ("it", "its", "that", "this", "they", "there"),
}

#: Extra oblique/declined anaphors folded into detection but not part of :data:`PRONOUNS`.
_OBLIQUE: dict[str, tuple[str, ...]] = {
    "ru": ("ним", "нём", "нем", "ней", "ними", "им", "ему", "ей", "её", "ее", "неё", "нее"),
    "en": ("them", "their", "theirs"),
}

#: Full per-language anaphor lookup (pronouns ∪ oblique forms), lowercased for matching.
_ANAPHOR_FORMS: dict[str, frozenset[str]] = {
    lang: frozenset(w.lower() for w in (*forms, *_OBLIQUE.get(lang, ())))
    for lang, forms in PRONOUNS.items()
}

#: Unicode-aware word tokeniser (keeps Cyrillic; drops punctuation). ``\w`` incl. digits.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Resolution:
    """Result of a follow-up rewrite (§7.6): the resolved text + audit trail.

    Frozen and orjson-serialisable via :meth:`as_dict`.

    * ``resolved_question`` — the (possibly rewritten) question sent onward.
    * ``substitutions`` — the ``(pronoun, entity)`` bindings applied, in match order.
    * ``used_carryover`` — ``True`` iff an entity was carried over from a prior turn.
    """

    resolved_question: str
    substitutions: tuple[tuple[str, str], ...]
    used_carryover: bool

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a stable dict (substitutions as ``[pronoun, entity]`` lists)."""
        return {
            "resolved_question": self.resolved_question,
            "substitutions": [list(pair) for pair in self.substitutions],
            "used_carryover": self.used_carryover,
        }


def _tokens(text: str) -> list[str]:
    """Lowercased Unicode word tokens of ``text`` (детерминированно / deterministic)."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _names_explicit_entity(question: str, prior_entities: list[str]) -> bool:
    """True iff ``question`` already mentions any ``prior_entities`` (case-insensitive)."""
    haystack = question.lower()
    return any(entity and entity.lower() in haystack for entity in prior_entities)


def _matched_anaphors(question: str, language: str) -> tuple[str, ...]:
    """Anaphoric tokens in ``question`` for ``language``, deduped in first-seen order."""
    forms = _ANAPHOR_FORMS.get(language, _ANAPHOR_FORMS["en"])
    seen: list[str] = []
    for token in _tokens(question):
        if token in forms and token not in seen:
            seen.append(token)
    return tuple(seen)


def resolve_followup(question: str, prior_entities: list[str], language: str = "en") -> Resolution:
    """Rewrite an anaphoric follow-up by carrying over the most-recent prior entity.

    §7.6 multi-turn coreference. Carryover happens **iff** all hold:

    * ``prior_entities`` is non-empty (there is something to carry);
    * ``question`` names none of those entities explicitly (иначе — уже конкретно);
    * ``question`` contains at least one pronoun/anaphor for ``language``.

    On carryover the newest entity (``prior_entities[0]``) is appended as ``" (entity)"``
    and each matched pronoun is recorded as a ``(pronoun, entity)`` substitution. Otherwise
    the question is returned verbatim with ``used_carryover=False`` and no substitutions.
    """
    if not prior_entities or _names_explicit_entity(question, prior_entities):
        return Resolution(resolved_question=question, substitutions=(), used_carryover=False)

    matched = _matched_anaphors(question, language)
    if not matched:
        return Resolution(resolved_question=question, substitutions=(), used_carryover=False)

    entity = prior_entities[0]
    resolved = f"{question} ({entity})"
    substitutions = tuple((pronoun, entity) for pronoun in matched)
    return Resolution(resolved_question=resolved, substitutions=substitutions, used_carryover=True)
