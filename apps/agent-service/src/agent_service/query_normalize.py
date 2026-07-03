"""Query preprocessing: unit-normalization + numeric constraints (§13.7).

Второй, «тяжёлый» слой препроцессинга запроса (после дешёвого
:mod:`agent_service.preprocess`, который лишь чистит текст и ставит флаги).
Здесь из RU/EN вопроса вытаскиваются числовые условия эксперимента и сводятся
к каноническим единицам:

* **temperature** — ``°C`` напрямую, ``K`` → ``°C`` (вычитание 273.15);
* **time** — ``ч``/``h`` напрямую, ``мин``/``min`` → часы (``/60``),
  ``с``/``s`` → часы (``/3600``);
* **pressure** — ``МПа``/``bar``/``атм`` → значение в ``МПа``;
* **hardness** — ``HV`` / ``HRC`` / ``HB`` (шкалы несопоставимы, каждой свой ключ);
* **composition** — ``wt%`` (массовые) / ``at%`` (атомные) проценты.

Reuse (никаких копий парсеров единиц):

* :func:`kg_extractors.constraints.parse_constraints` — надёжно достаёт
  температуру в ``°C`` и давление (``МПа``/``бар``/``атм``) с операторами и
  диапазонами;
* :func:`kg_extractors.units.to_canonical` — конвертация ``K`` → ``°C``.

Единицы, которых не знает :mod:`kg_extractors` (Кельвины, время, твёрдость,
``wt%``/``at%``), добираются локальными регулярками. Результат совместим по духу
с :class:`agent_service.preprocess.PreprocessedQuery` — frozen dataclass с
``as_dict()`` (§7.3).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from kg_extractors.constraints import parse_constraints
from kg_extractors.units import to_canonical

# Число: знак + целая/дробная часть (десятичная запятая или точка) — как в units.py.
_NUM = r"[-+]?\d+(?:[.,]\d+)?"


def _f(raw: str) -> float:
    """Числовой токен с десятичной запятой/точкой и ведущим знаком → ``float``."""
    return float(raw.replace(",", ".").replace("+", ""))


# ---------------------------------------------------------------------------
# Регэкспы единиц, которых нет в kg_extractors (группы: num / sp / unit)
# ---------------------------------------------------------------------------
# Kelvin: одиночная K/К сразу после числа (не «кг», «км», не часть слова).
_RE_KELVIN = re.compile(
    rf"(?P<num>{_NUM})(?P<sp>\s*)(?P<unit>[KkКк])(?![A-Za-zА-Яа-яёЁ0-9])",
)
# Время: часы / минуты / секунды (RU + EN). «ч»/«h»/«с»/«s» защищены границей,
# длинные RU-слова стоят раньше кратких форм.
_RE_TIME = re.compile(
    rf"(?P<num>{_NUM})(?P<sp>\s*)(?P<unit>"
    r"час(?:ов|а)?|hours?|hrs?|ч(?![а-яё])|h(?![a-z])|"
    r"мин(?:ут[аоы]?)?|min(?:ute)?s?|"
    r"сек(?:унд[аоы]?)?|с(?![а-яё])|s(?![a-z])"
    r")",
    re.IGNORECASE,
)
# Твёрдость: шкалы Виккерса/Роквелла/Бринелля (HRC раньше HV/HB — длиннее).
_RE_HARDNESS = re.compile(
    rf"(?P<num>{_NUM})(?P<sp>\s*)(?P<unit>HRC|HV|HB)(?![A-Za-zА-Яа-яёЁ0-9])",
    re.IGNORECASE,
)
# Состав: массовые / атомные проценты (wt% | мас.% | масс.% | вес.% | at% | ат.%).
_RE_COMPOSITION = re.compile(
    rf"(?P<num>{_NUM})(?P<sp>\s*)(?P<unit>"
    r"wt\.?\s*%|мас{1,2}\.?\s*%|вес\.?\s*%|"
    r"at\.?\s*%|ат\.?\s*%"
    r")",
    re.IGNORECASE,
)
# ---------------------------------------------------------------------------
# Регэкспы только для переписывания написаний (rewrite) — °C и давление, чьи
# значения достаёт parse_constraints, но каноническое написание ставим здесь.
# ---------------------------------------------------------------------------
_RE_TEMP_C_RW = re.compile(
    rf"(?P<num>{_NUM})(?P<sp>\s*)(?P<unit>°\s*[CcСс]|degc)(?![A-Za-zА-Яа-яёЁ])",
    re.IGNORECASE,
)
_RE_PRESSURE_RW = re.compile(
    rf"(?P<num>{_NUM})(?P<sp>\s*)(?P<unit>мпа|mpa|бар|bar|атм|atm)"
    r"(?![A-Za-zА-Яа-яёЁ0-9])",
    re.IGNORECASE,
)


def _canon_time(unit: str) -> str:
    """Каноническое написание единицы времени: ``h`` | ``min`` | ``s``."""
    u = unit.lower()
    if u.startswith(("час", "ч", "h")):
        return "h"
    if u.startswith(("мин", "min")):
        return "min"
    return "s"


def _time_hours(value: float, unit: str) -> float:
    """Перевести значение времени в часы (мин→``/60``, с→``/3600``)."""
    canon = _canon_time(unit)
    if canon == "h":
        return value
    return value / 60.0 if canon == "min" else value / 3600.0


def _canon_pressure(unit: str) -> str:
    """Каноническое написание единицы давления: ``MPa`` | ``bar`` | ``atm``."""
    u = unit.lower()
    if u in ("мпа", "mpa"):
        return "MPa"
    return "bar" if u in ("бар", "bar") else "atm"


def _canon_comp(unit: str) -> str:
    """Каноническое написание доли состава: ``wt%`` (масс.) | ``at%`` (ат.)."""
    return "wt%" if unit.lower()[0] in ("w", "м", "в") else "at%"


# ---------------------------------------------------------------------------
# Результат
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NormalizedQuery:
    """Результат §13.7 unit-normalization запроса.

    Fields
    ------
    normalized_text
        Исходный текст с каноническими написаниями единиц (``°с`` → ``°C``,
        ``ч`` → ``h``, ``мпа`` → ``MPa`` …); числа сохранены (нормализованный текст).
    numeric_constraints
        Числовые условия по каноническим ключам: ``temperature_c``, ``time_h``,
        ``pressure_mpa``, ``hardness_hv``/``hardness_hrc``/``hardness_hb``,
        ``composition_wt_pct``/``composition_at_pct`` (числовые условия).
    units_found
        Канонические единицы в порядке появления, без повторов (найденные единицы).
    """

    normalized_text: str
    numeric_constraints: dict[str, float] = field(default_factory=dict)
    units_found: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Полное структурированное представление для state/логов (§7.3)."""
        return {
            "normalized_text": self.normalized_text,
            "numeric_constraints": dict(self.numeric_constraints),
            "units_found": list(self.units_found),
        }


def _set(nc: dict[str, float], key: str, value: float) -> None:
    """Записать условие по ключу, если его ещё нет (побеждает первое вхождение)."""
    if key not in nc:
        nc[key] = round(float(value), 6)


def _rewrite(t: str) -> str:
    """Переписать написания единиц каноническими (число + пробел сохраняются)."""
    t = _RE_TEMP_C_RW.sub(lambda m: f"{m['num']}{m['sp']}°C", t)
    t = _RE_PRESSURE_RW.sub(lambda m: f"{m['num']}{m['sp']}{_canon_pressure(m['unit'])}", t)
    t = _RE_KELVIN.sub(lambda m: f"{m['num']}{m['sp']}K", t)
    t = _RE_TIME.sub(lambda m: f"{m['num']}{m['sp']}{_canon_time(m['unit'])}", t)
    t = _RE_HARDNESS.sub(lambda m: f"{m['num']}{m['sp']}{m['unit'].upper()}", t)
    return _RE_COMPOSITION.sub(lambda m: f"{m['num']}{m['sp']}{_canon_comp(m['unit'])}", t)


def _extract(t: str) -> tuple[dict[str, float], list[tuple[int, str]]]:
    """Достать числовые условия и (позиция, единица) для каждого найденного."""
    nc: dict[str, float] = {}
    units: list[tuple[int, str]] = []

    # Температура (°C) и давление (МПа/бар/атм) — переиспользуем parse_constraints.
    for c in parse_constraints(t):
        val = c.normalized_value if c.normalized_value is not None else c.normalized_min
        if val is None:
            continue
        if c.normalized_unit == "degC":
            _set(nc, "temperature_c", val)
            units.append((t.find(c.source_span), "°C"))
        elif c.normalized_unit == "bar":  # МПа/бар/атм канонизуются в бар
            _set(nc, "pressure_mpa", val / 10.0)
            units.append((t.find(c.source_span), _canon_pressure(c.unit or "bar")))

    # Температура (K) → °C через to_canonical (units.py знает kelvin).
    for m in _RE_KELVIN.finditer(t):
        norm = to_canonical(_f(m["num"]), "K")
        if norm is not None:
            _set(nc, "temperature_c", norm.value)
            units.append((m.start("unit"), "K"))

    # Время → часы.
    for m in _RE_TIME.finditer(t):
        _set(nc, "time_h", _time_hours(_f(m["num"]), m["unit"]))
        units.append((m.start("unit"), _canon_time(m["unit"])))

    # Твёрдость (HV/HRC/HB) — шкалы несопоставимы, каждой свой ключ.
    for m in _RE_HARDNESS.finditer(t):
        scale = m["unit"].upper()
        _set(nc, f"hardness_{scale.lower()}", _f(m["num"]))
        units.append((m.start("unit"), scale))

    # Состав (wt% / at%).
    for m in _RE_COMPOSITION.finditer(t):
        canon = _canon_comp(m["unit"])
        key = "composition_wt_pct" if canon == "wt%" else "composition_at_pct"
        _set(nc, key, _f(m["num"]))
        units.append((m.start("unit"), canon))

    return nc, units


def _units_found(units: list[tuple[int, str]]) -> list[str]:
    """Канонические единицы в порядке появления, без повторов."""
    seen: set[str] = set()
    out: list[str] = []
    for _, u in sorted(units, key=lambda x: x[0] if x[0] >= 0 else 10**9):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def normalize_query(text: str) -> NormalizedQuery:
    """Достать числовые условия и канонизировать единицы запроса (§13.7).

    Пример::

        >>> nq = normalize_query("закалка при 500 °C, 2 ч")
        >>> nq.numeric_constraints
        {'temperature_c': 500.0, 'time_h': 2.0}
        >>> nq.units_found
        ['°C', 'h']

    Пустой / без чисел ввод обрабатывается корректно: ``numeric_constraints`` и
    ``units_found`` пусты, ``normalized_text`` — исходный текст без изменений.
    """
    t = unicodedata.normalize("NFKC", text or "")
    nc, units = _extract(t)
    return NormalizedQuery(
        normalized_text=_rewrite(t),
        numeric_constraints=nc,
        units_found=_units_found(units),
    )
