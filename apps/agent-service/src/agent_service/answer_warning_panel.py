"""§5.2.2 / §13.17 warning-panel aggregate builder for ``answer_synthesizer``.

Pure-python, deterministic projection over the already-prepared agent state
(§13.11). Считает три числа для UI-панели предупреждений: сколько противоречий
(``contradictions``), сколько цитат с низкой уверенностью (``citations`` с
``confidence`` строго меньше порога) и сколько «пробелов» типа ``missing_*``
(``gaps``). Это ИМЕННО счётчики для warning-панели — в отличие от
``answer_tabs``, который раскладывает полные секции-пейлоады по вкладкам.

Ничего здесь не трогает граф-стор и не зовёт LLM — модуль unit-testable без
засеянной Kuzu-базы. Kuzu note: custom node props are NOT queryable columns —
a retriever must RETURN base columns and read the rest via ``get_node``; к
моменту, когда состояние доходит сюда, строки уже несут склеенные props как
обычные dict, так что ничего тут стор не дёргает.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["WarningPanel", "build_warning_panel"]


@dataclass(frozen=True)
class WarningPanel:
    """Числовой агрегат для UI-панели предупреждений (§5.2.2 / §13.17).

    Хранит только счётчики (contradictions / low-confidence / missing-data) и
    производный флаг ``has_warnings``. :meth:`as_dict` отдаёт ровно эти четыре
    ключа — payload'ы секций живут в ``answer_tabs``, не здесь.
    """

    contradictions_count: int
    low_confidence_count: int
    missing_data_count: int
    has_warnings: bool

    def as_dict(self) -> dict[str, Any]:
        """Return exactly the four warning-panel keys as a plain dict."""
        return asdict(self)


def build_warning_panel(state: dict, low_conf_threshold: float = 0.5) -> WarningPanel:
    """Build the §13.17 warning-panel aggregate from agent ``state`` (§13.11).

    :param state: mapping с полями ``contradictions`` / ``citations`` / ``gaps``.
    :param low_conf_threshold: порог; цитата считается low-confidence при
        ``confidence`` СТРОГО меньше порога (равенство порогу не считается).
    :returns: :class:`WarningPanel` со счётчиками и производным ``has_warnings``.
    """
    contradictions = _as_seq(state.get("contradictions"))
    citations = _as_seq(state.get("citations"))
    gaps = _as_seq(state.get("gaps"))

    contradictions_count = len(contradictions)

    low_confidence_count = sum(
        1
        for item in citations
        if isinstance(item, Mapping)
        and isinstance(item.get("confidence"), (int, float))
        and not isinstance(item.get("confidence"), bool)
        and float(item["confidence"]) < low_conf_threshold
    )

    missing_data_count = sum(
        1
        for gap in gaps
        if isinstance(gap, Mapping)
        and isinstance(gap.get("type"), str)
        and gap["type"].startswith("missing_")
    )

    has_warnings = contradictions_count > 0 or low_confidence_count > 0 or missing_data_count > 0

    return WarningPanel(
        contradictions_count=contradictions_count,
        low_confidence_count=low_confidence_count,
        missing_data_count=missing_data_count,
        has_warnings=has_warnings,
    )


def _as_seq(value: Any) -> Sequence[Any]:
    """Coerce a possibly-missing state field to a safe, non-str sequence."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()
