"""Deterministic numeric accuracy check (§18.10).

Детерминированная (без LLM) проверка числовой точности ответа. / Deterministic
(no-LLM) numeric extraction + tolerance comparison of answer text against a golden
``expected_numeric`` value.

Извлекаем числа регулярным выражением (десятичные, разделители тысяч, научная
запись), затем сравниваем с ожидаемым значением по абсолютному или относительному
допуску. / We pull numbers out with a regex (decimals, thousands separators,
scientific notation) and compare to the expected value by absolute or relative
tolerance. No model, fully reproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Число: знак? (группы тысяч через запятую | цифры) дробь? научная-экспонента?
# Number: sign? (comma-grouped thousands | plain digits) fraction? sci-exponent?
_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?"
# Единица — необязательный токен из букв/символов сразу за числом (с пробелом или без).
# Unit — optional letter/symbol token right after the number (space optional).
_UNIT = r"(?:\s*([A-Za-z°µΩμ%]+))?"
_PATTERN = re.compile(rf"({_NUMBER}){_UNIT}")


@dataclass(frozen=True)
class NumericExpectation:
    """Ожидаемое число из золотого набора. / Golden expected number.

    ``rel=True`` переключает допуск ``tol`` в относительный режим (доля от |value|).
    ``rel=True`` switches ``tol`` into relative mode (fraction of |value|).
    """

    value: float
    unit: str | None = None
    tol: float = 0.0
    rel: bool = False


@dataclass(frozen=True)
class NumericCheckResult:
    """Результат сравнения. / Comparison result.

    ``best_value`` — ближайшее извлечённое значение; ``delta`` — |best_value - value|.
    ``best_value`` is the closest extracted value; ``delta`` is |best_value - value|.
    """

    matched: bool
    extracted: list[tuple[float, str | None]]
    best_value: float | None
    delta: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "matched": bool(self.matched),
            "extracted": [[v, u] for (v, u) in self.extracted],
            "best_value": self.best_value,
            "delta": self.delta,
        }


def extract_numbers(text: str) -> list[tuple[float, str | None]]:
    """Извлечь (значение, единица) из текста. / Extract (value, unit) pairs from text.

    Разбирает '180 C', '2.5h', '1,200 MPa' -> (1200.0, 'MPa'), научную запись '1e3'.
    Parses '180 C', '2.5h', '1,200 MPa' -> (1200.0, 'MPa'), scientific '1e3'.
    """
    out: list[tuple[float, str | None]] = []
    for match in _PATTERN.finditer(text):
        raw = match.group(1).replace(",", "")
        unit = match.group(2)
        out.append((float(raw), unit))
    return out


def check_numeric(text: str, exp: NumericExpectation) -> NumericCheckResult:
    """Сопоставить числа из текста с ожиданием по допуску. / Match text numbers vs exp.

    Совпадение — если какое-либо извлечённое значение попадает в абсолютный (или
    относительный при ``rel=True``) допуск. / Matched iff some extracted value falls
    within the absolute (or relative when ``rel=True``) tolerance.
    """
    extracted = extract_numbers(text)
    if not extracted:
        return NumericCheckResult(False, [], None, None)
    best_value = extracted[0][0]
    best_delta = abs(best_value - exp.value)
    for value, _unit in extracted[1:]:
        delta = abs(value - exp.value)
        if delta < best_delta:
            best_delta, best_value = delta, value
    threshold = exp.tol * abs(exp.value) if exp.rel else exp.tol
    matched = best_delta <= threshold
    return NumericCheckResult(matched, extracted, best_value, best_delta)
