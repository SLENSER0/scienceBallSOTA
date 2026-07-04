"""§13.12 валидация ответа / answer validation (pure python).

A post-synthesis sanity check that never touches the graph store: given the
rendered ``answer`` text and the list of citations attached to it, flag numeric
claims (числовые утверждения) that carry no inline citation marker ``[n]`` in
their sentence. A number backed by a nearby marker is treated as grounded; the
rest surface in :attr:`AnswerValidation.numeric_claims_without_evidence`, so an
unsupported «твёрдость 9» or «45%» cannot slip through uncited.

Deterministic and dependency-free — see :mod:`agent_service.citation_formatter`
for the ``[n]`` marker convention and :mod:`agent_service.verifier` for the
graph-backed grounding check this complements. The check is sentence-scoped: a
citation marker anywhere in a number's sentence grounds every number in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Inline citation marker, e.g. ``[1]`` / ``[12]`` — one or more digits in brackets.
_MARKER_RE = re.compile(r"\[\d+\]")

# A numeric-claim token: integer/decimal (``.`` or ``,`` grouped) with an optional
# trailing ``%``. The leading guard keeps the "2" in "H2O" or a year suffix from
# matching mid-word — a claim must start at a non-word, non-dot boundary.
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*%?")

# Sentence boundary: whitespace after a terminator, or a run of newlines. The
# lookbehind never fires inside a decimal ("1.2" — the dot precedes a digit, not
# whitespace), so numbers stay intact.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# --- H-5: only *measurable* numbers require a citation ---------------------
# A bare integer is a year, an ordinal count («5 стадий»), an identifier
# («таблица 2») or a dimensionless index far more often than a measured value.
# So a number counts as a "claim needing evidence" only when it carries a unit
# (число+единица) or sits in a sentence that is *about* a measurable property —
# never for the incidental cases enumerated below.

# Measurement units that can trail a number (optionally after one space), incl.
# composite units like «см/с» or «мг/л». Sorted longest-first so the alternation
# prefers «см» over «с»; a trailing letter-boundary keeps «с» from matching the
# «с» in «стадий». Kept curated (not a generic \w+) so prepositions like «по» or
# nouns like «стадий» are never mistaken for units.
_UNIT_TOKENS = [
    "‰", "°C", "°С", "°F", "°", "ppm", "ppb", "HV", "HB", "HRC",
    "мкг", "мг", "кг", "нг", "мкм", "нм", "мм", "см", "дм", "км",
    "мл", "сек", "мин", "сут", "час", "кПа", "МПа", "ГПа", "Па", "бар",
    "атм", "кВт", "МВт", "мВт", "Вт", "кВ", "мВ", "мА", "Ом", "кДж",
    "МДж", "Дж", "ккал", "кал", "эВ", "моль", "об",
    "г", "т", "м", "л", "ч", "с", "В", "А", "%",
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(_UNIT_TOKENS, key=len, reverse=True))
_UNIT_BASE = "(?:" + _UNIT_ALT + ")"
# unit right after the number: optional space, a base unit, an optional /·-joined
# second base unit, then a non-letter boundary so «5 метров» is not «5 м».
_UNIT_AFTER_RE = re.compile(r"\s?" + _UNIT_BASE + r"(?:[·/]" + _UNIT_BASE + r")?(?![А-Яа-яA-Za-z])")

# A counting noun right after the number → an ordinal count, not a measurement.
_COUNTER_AFTER_RE = re.compile(
    r"\s?(?:стади|этап|шаг|ступен|фаз|цикл|сло[йя]|класс|вариант|способ|метод|"
    r"образц|проб|элемент|компонент|номер|позиц|пункт|раза?\b|разновидн)",
    re.IGNORECASE,
)

# An identifier prefix right before the number → a label («таблица 2», «№5»).
_ID_PREFIX_RE = re.compile(
    r"(?:^|[\s(])(?:№|#|табл\.?|таблиц\w*|рис\.?|рисун\w*|пункт|гост|iso)\s*$",
    re.IGNORECASE,
)

# Sentence is *about* a measured property when it mentions one of these stems.
_PROPERTY_STEMS: frozenset[str] = frozenset({
    "твёрд", "тверд", "температур", "скорост", "давлен", "концентрац", "плотност",
    "эффективн", "кпд", "коэффициент", "выход", "извлечен", "содержан", "напряжен",
    "вязкост", "растворим", "расход", "мощност", "энерг", "глубин", "площад", "масс",
    "объём", "объем", "удельн", "селективн", "кислотн", "щёлочн", "щелочн", "влажн",
    "зольн", "крупност", "диаметр", "длин", "ширин", "толщин", "высот", "частот",
    "сопротивлен", "теплопровод", "себестоим", "стоимост", "затрат", "продолжит",
    "пропускн", "потер", "дозиров",
})


@dataclass(frozen=True)
class AnswerValidation:
    """Result of §13.12 numeric-claim validation over a rendered answer.

    ``ok`` is ``True`` when no numeric claim is left without evidence.
    ``numeric_claims_without_evidence`` lists the offending number tokens in order
    of appearance (в порядке появления), ``has_citations`` mirrors whether any
    citation is attached, and ``issues`` holds RU/EN human-readable notes.
    """

    ok: bool
    numeric_claims_without_evidence: list[str]
    has_citations: bool
    issues: list[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to ``{ok, numeric_claims_without_evidence, has_citations, issues}``."""
        return {
            "ok": self.ok,
            "numeric_claims_without_evidence": list(self.numeric_claims_without_evidence),
            "has_citations": self.has_citations,
            "issues": list(self.issues),
        }


def _sentences(text: str) -> list[str]:
    """Split ``text`` into non-empty, stripped sentences (пустые строки отброшены)."""
    return [s for s in (part.strip() for part in _SENTENCE_SPLIT_RE.split(text)) if s]


def _requires_citation(token: str, cleaned: str, low: str, start: int, end: int) -> bool:
    """True iff ``token`` is a *measurable* claim that must carry evidence (H-5).

    Measurable = it trails a unit (``45%``, ``148 HV``, ``1.2 см/с``) or sits in a
    sentence about a measured property (``твёрдость … 9``). Incidental numbers are
    excluded: a year in 1900–2100, an ordinal count («5 стадий»), and label
    identifiers («таблица 2», «№5») — none of these need a citation.
    """
    after = cleaned[end:]
    before = cleaned[:start]
    has_unit = token[-1:] in ("%", "‰") or bool(_UNIT_AFTER_RE.match(after))

    # Incidental cases never need a citation (units, if any, keep them measurable).
    if _ID_PREFIX_RE.search(before):
        return False  # «таблица 2» / «№5» — a label, not a measurement
    if not has_unit and _COUNTER_AFTER_RE.match(after):
        return False  # «5 стадий» — an ordinal count
    if not has_unit and token.isdigit() and len(token) == 4 and 1900 <= int(token) <= 2100:
        return False  # a bare year

    if has_unit:
        return True
    return any(stem in low for stem in _PROPERTY_STEMS)


def validate_answer(answer: str, citations: list[Any]) -> AnswerValidation:
    """Flag numeric claims in ``answer`` that lack an inline ``[n]`` citation (§13.12).

    ``answer`` is split into sentences; a number token is grounded when its sentence
    carries at least one inline marker ``[n]`` **and** ``citations`` is non-empty
    (без цитат — заземлять нечем / with no citations there is nothing to ground on).
    Ungrounded numbers, in order of appearance, land in
    ``numeric_claims_without_evidence`` and ``ok`` is ``True`` iff that list is empty.
    Markers themselves are never counted as claims (``[1]`` — ссылка, а не число).
    """
    has_citations = len(citations) > 0
    without_evidence: list[str] = []
    for sentence in _sentences(answer):
        has_marker = bool(_MARKER_RE.search(sentence))
        cleaned = _MARKER_RE.sub(" ", sentence)  # drop markers so [1] isn't a claim
        grounded = has_citations and has_marker
        low = cleaned.lower()
        for m in _NUMBER_RE.finditer(cleaned):
            token = m.group()
            # H-5: only measurable claims need evidence; incidental numbers (years,
            # counts, labels) are skipped so they can't force «unverified» downstream.
            if not _requires_citation(token, cleaned, low, m.start(), m.end()):
                continue
            if not grounded:
                without_evidence.append(token)
    issues: list[str] = []
    if without_evidence and not has_citations:
        issues.append("ответ без цитат / answer has no citations")
    for num in without_evidence:
        ru = f"числовое утверждение «{num}» без ссылки"
        issues.append(f"{ru} / numeric claim «{num}» without citation")
    return AnswerValidation(
        ok=not without_evidence,
        numeric_claims_without_evidence=without_evidence,
        has_citations=has_citations,
        issues=issues,
    )
