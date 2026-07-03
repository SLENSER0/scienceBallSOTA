"""§12.11 — character-span snippet extraction for ``get_document_snippet``.

Извлечение сниппета (*snippet* — фрагмент документа) по символьному диапазону
(span) ``char_start``/``char_end`` (§8.3). Вокруг целевого диапазона берётся
контекстное окно радиусом ``radius`` символов, границы окна усечены (clamp) к
пределам документа ``[0, len(text)]``. Целевой span выделяется парой маркеров
(*marker pair*) для кликабельных доказательных участков (*clickable evidence
spans*, §12.11).

Deterministic and offline-safe (no LLM). Backs the ``get_document_snippet`` tool
and highlight rendering; complements :mod:`kg_retrievers.report_evidence` which
only reconstructs community :class:`EvidenceRef` locations without windowing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Snippet:
    """Фрагмент документа с выделенным целевым диапазоном (§12.11).

    Attributes:
        text: подстрока-окно вокруг целевого span (без маркеров).
        start: усечённая (clamped) левая граница окна в исходном тексте.
        end: усечённая правая граница окна в исходном тексте.
        highlighted: то же окно, но целевой span обёрнут парой маркеров.
    """

    text: str
    start: int
    end: int
    highlighted: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain JSON-ready dict."""
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "highlighted": self.highlighted,
        }


def extract_window(
    text: str,
    char_start: int,
    char_end: int,
    *,
    radius: int = 80,
    marker: tuple[str, str] = ("«", "»"),
) -> Snippet:
    """Extract a context window around ``[char_start, char_end)`` (§12.11).

    Границы окна: ``start = max(0, char_start - radius)`` и
    ``end = min(len(text), char_end + radius)``. Возвращается подстрока-окно и её
    копия ``highlighted`` с целевым span, обёрнутым парой ``marker``.

    Args:
        text: исходный текст документа.
        char_start: начало целевого span (включительно).
        char_end: конец целевого span (исключительно).
        radius: радиус контекста слева и справа в символах.
        marker: пара маркеров (открывающий, закрывающий) для выделения span.

    Returns:
        :class:`Snippet` с усечёнными границами и подсвеченным окном.
    """
    n = len(text)
    # Clamp the target span into the document, keeping start <= end (§8.3).
    span_start = max(0, min(char_start, n))
    span_end = max(span_start, min(char_end, n))

    start = max(0, span_start - radius)
    end = min(n, span_end + radius)

    window = text[start:end]

    # Offsets of the target span relative to the window start.
    rel_start = span_start - start
    rel_end = span_end - start
    open_m, close_m = marker
    highlighted = (
        window[:rel_start] + open_m + window[rel_start:rel_end] + close_m + window[rel_end:]
    )

    return Snippet(text=window, start=start, end=end, highlighted=highlighted)
