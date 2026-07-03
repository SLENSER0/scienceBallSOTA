"""[DE] Measurable-value-in-mention detector (spec §33 / port of science_ball A7).

Offline, LLM-optional heuristic answering the question the absence layer never asks: when
a document MENTIONS a property, does the text actually **state a measurable value** for it,
or merely **name** it ("параметр X не измеряли; запланировано в будущей работе")? A bare
mention is otherwise treated as evidence of a *missed observation*, so a genuine gap
(property named, no value) is indistinguishable from a real extractor miss (value stated in
prose) — the mention-vs-value confusion that drives ``false_possible_miss_rate`` up and
``possible_miss`` precision down.

This module ONLY detects the signal. It is wired into the production verdict behind an
**opt-in** gate (``Settings.absence_value_gate``, default off): at ingest the MENTIONS
linker runs it to stamp ``value_present`` on the ``Document→(MENTIONS)→Property`` prose edge
(:mod:`kg_retrievers.value_in_mention` → ingestion), and :mod:`kg_retrievers.absence_signals`
consults that flag to downgrade a would-be ``possible_miss`` to ``genuine_gap`` only on
positive evidence of no value. The Track-C benchmark (:mod:`kg_eval.absence_eval`) also uses
it to *measure* the achievable fix (the regex detector) against the ground-truth oracle.

Heuristic, by design and by admission:

* a value counts as present when a sentence that names the property also contains a numeric
  token and no explicit non-measurement / deferral cue;
* negation cues are word-boundary-anchored (so ``was not`` does not fire on ``notably``) but
  are scoped to the *sentence*, not the clause — a value stated in one clause of a sentence
  whose other clause defers ("Модуль 110 ГПа, старение не проводили") is a known false
  negative;
* **any digit** counts (temperatures, method codes) — masked on the synthetic corpus because
  the "not measured" sentences carry no digit, but a stricter detector should require the
  number to co-occur with a unit near the property mention.
"""

from __future__ import annotations

import re

# Non-measurement / deferral cues. Russian stems are prefix-matched (to catch inflections
# like «не измеряли/измерялся»); English cues are whole phrases. All are anchored with a
# leading word boundary so a cue never fires inside a longer word (e.g. "was not" ⊄ "notably").
_CUE_PATTERNS: tuple[str, ...] = (
    r"не измер",
    r"не определ",
    r"не оцен",
    r"не провод",
    r"не удалось",
    r"не приводит",
    r"не сообщ",
    r"не указ",
    r"нет данных",
    r"отсутств",
    r"недоступ",
    r"запланир",
    r"в будущей работе",
    r"будущих работ",
    r"предстоит",
    r"not measured",
    r"not determined",
    r"not reported",
    r"not available",
    r"n/a",
    r"future work",
    r"planned",
)
_NEGATION_RE = re.compile(r"\b(?:" + "|".join(_CUE_PATTERNS) + r")", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def value_present_in_text(text: str, aliases: list[str] | None = None) -> bool:
    """True if some sentence that names the property states a measurable value (a numeric
    token, no non-measurement cue).

    ``aliases``: property surface forms used to locate the relevant sentence(s).

    * ``None`` → no property filter (every sentence is eligible).
    * a list  → require a sentence to contain one of them; if the list is empty after
      dropping falsy entries the property is un-locatable and the function returns ``False``
      (it must NOT fall through to "match any numbered sentence").
    """
    if not text:
        return False
    als: list[str] | None = None
    if aliases is not None:
        als = [a.lower() for a in aliases if a]
        if not als:
            return False  # property requested but not locatable → cannot confirm a value
    for sent in _sentences(text):
        low = sent.lower()
        if als is not None and not any(a in low for a in als):
            continue  # sentence does not mention THIS property
        if _NEGATION_RE.search(low):
            continue  # explicitly not measured / deferred → not a stated value
        if _NUMBER_RE.search(sent):
            return True
    return False
