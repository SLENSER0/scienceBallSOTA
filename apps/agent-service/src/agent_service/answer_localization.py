"""§13.17 bilingual section-label localization for the six answer tabs.

§13.17 requires answers in the user's language (``state['language']`` ∈
{``'ru'``, ``'en'``}). :mod:`agent_service.answer_tabs` emits six fixed section
keys — ``summary``, ``experiments``, ``evidence``, ``graph``, ``gaps``,
``contradictions`` — but the tab *labels* shown to the reader must be localized.

Этот модуль хранит единственную ru/en таблицу подписей (:data:`LABELS`) и
раскладывает её по языку через :func:`localize_sections`. Чистый python, без
графа и LLM: подписи детерминированы и порядок ключей совпадает с
:data:`SECTION_KEYS` (порядком вкладок §5.2.2).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "LABELS",
    "SECTION_KEYS",
    "LocalizedLabels",
    "label_for",
    "localize_sections",
]

# The six §5.2.2 / §13.17 section keys, in display order.
SECTION_KEYS: tuple[str, ...] = (
    "summary",
    "experiments",
    "evidence",
    "graph",
    "gaps",
    "contradictions",
)

# Default language used when a requested language is unknown (§13.17).
_FALLBACK_LANGUAGE = "en"

# ru/en подписи для каждой из шести вкладок ответа (§13.17).
LABELS: dict[str, dict[str, str]] = {
    "summary": {"en": "Summary", "ru": "Сводка"},
    "experiments": {"en": "Experiments", "ru": "Эксперименты"},
    "evidence": {"en": "Evidence", "ru": "Доказательства"},
    "graph": {"en": "Graph", "ru": "Граф"},
    "gaps": {"en": "Gaps", "ru": "Пробелы"},
    "contradictions": {"en": "Contradictions", "ru": "Противоречия"},
}


def label_for(key: str, language: str) -> str:
    """Return the localized label for ``key`` in ``language`` (§13.17).

    Falls back to the English label for an unknown ``language``; returns ``key``
    itself unchanged for an unknown ``key``.
    """
    translations = LABELS.get(key)
    if translations is None:
        return key
    return translations.get(language, translations[_FALLBACK_LANGUAGE])


@dataclass(frozen=True)
class LocalizedLabels:
    """Frozen ordered (key, label) mapping for one language (§13.17)."""

    language: str
    labels: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, str]:
        """Render an ordered ``{key: label}`` dict preserving key order."""
        return dict(self.labels)


def localize_sections(language: str) -> LocalizedLabels:
    """Localize all six §13.17 section labels into ``language``.

    Keys are emitted in :data:`SECTION_KEYS` order; unknown languages fall back
    to English per :func:`label_for`.
    """
    labels = tuple((key, label_for(key, language)) for key in SECTION_KEYS)
    return LocalizedLabels(language=language, labels=labels)
