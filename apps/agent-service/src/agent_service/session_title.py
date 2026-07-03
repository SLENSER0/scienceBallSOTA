"""§13.24 деривация заголовка чат-сессии / chat-session title derivation.

§13.24 персистит ``chat_sessions``/``chat_messages``, но ничто не выводит
человекочитаемый заголовок (preview) сессии из первого вопроса пользователя для
списка сессий в UI. Этот модуль закрывает пробел: он сворачивает внутренние
пробелы, срезает завершающую пунктуацию (например ``?``), обрезает строку по
границе слова до ``max_len`` (добавляя ``…`` когда пришлось резать) и падает на
``'New chat'`` для пустого/пробельного вопроса.

Логика чистая и детерминированная (нет графа, нет LLM), поэтому тривиально
юнит-тестируется. §13.24 chat_sessions/chat_messages are persisted, but nothing
derives a human-readable session title/preview from the first user question — this
fills that gap with a pure, deterministic helper.

:class:`SessionTitle` хранит сам заголовок, флаг обрезки и число ходов;
:meth:`SessionTitle.as_dict` рендерит orjson-совместимый plain dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Строка-заглушка для пустого вопроса / fallback for an empty question.
_FALLBACK_TITLE = "New chat"

#: Символ-многоточие, добавляемый при обрезке / ellipsis appended when truncated.
_ELLIPSIS = "…"

#: Завершающая пунктуация для срезания / trailing punctuation to strip.
_TRAILING_PUNCT = "?!.,;:…"


@dataclass(frozen=True)
class SessionTitle:
    """Производный заголовок чат-сессии / a derived chat-session title.

    ``title`` — уже свёрнутый и обрезанный заголовок; ``truncated`` — истина, если
    исходный вопрос пришлось резать по границе слова; ``turn_count`` — число ходов
    в сессии (эхо-параметр для UI). Датакласс неизменяем и JSON-готов.
    """

    title: str
    truncated: bool
    turn_count: int

    def as_dict(self) -> dict[str, Any]:
        """orjson-безопасный dict / an orjson-serialisable plain dict."""
        return {
            "title": self.title,
            "truncated": self.truncated,
            "turn_count": self.turn_count,
        }


def _collapse_whitespace(text: str) -> str:
    """Свернуть любые пробельные последовательности в один пробел / collapse runs."""
    return " ".join(text.split())


def _truncate_on_word_boundary(text: str, max_len: int) -> tuple[str, bool]:
    """Обрезать по границе слова до ``max_len`` / truncate on a word boundary.

    Возвращает ``(title, truncated)``. Когда строка укладывается в ``max_len`` —
    отдаём её как есть с ``truncated=False``. Иначе режем по последнему пробелу до
    предела и добавляем ``…`` (гарантируя ``len(title) <= max_len + 1``).
    """
    if len(text) <= max_len:
        return text, False
    head = text[:max_len]
    cut = head.rfind(" ")
    # cut > 0 — режем по последнему пробелу; иначе одно длинное слово / word or long token.
    head = head[:cut] if cut > 0 else head.rstrip()
    return head.rstrip(_TRAILING_PUNCT + " ") + _ELLIPSIS, True


def derive_title(
    first_question: str,
    turn_count: int = 1,
    *,
    max_len: int = 60,
) -> SessionTitle:
    """Вывести заголовок сессии из первого вопроса / derive a session title.

    Сворачивает внутренние пробелы, срезает завершающую пунктуацию, обрезает по
    границе слова до ``max_len`` (добавляя ``…`` при срезе) и падает на
    ``'New chat'`` для пустого/пробельного ввода. ``turn_count`` эхо-переносится
    в :class:`SessionTitle` без изменений.
    """
    collapsed = _collapse_whitespace(first_question)
    if not collapsed:
        return SessionTitle(title=_FALLBACK_TITLE, truncated=False, turn_count=turn_count)

    stripped = collapsed.rstrip(_TRAILING_PUNCT + " ")
    if not stripped:
        # Вопрос состоял только из пунктуации / question was punctuation-only.
        return SessionTitle(title=_FALLBACK_TITLE, truncated=False, turn_count=turn_count)

    title, truncated = _truncate_on_word_boundary(stripped, max_len)
    return SessionTitle(title=title, truncated=truncated, turn_count=turn_count)
