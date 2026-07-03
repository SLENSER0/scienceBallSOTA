"""Population summary statistics for typical-band derivation (§7.7).

Where :mod:`kg_extractors.outliers` judges *individual* points against their
peer group and returns per-value verdicts, this module summarises the **whole**
``(material_class × property_class)`` population of normalized values into one
compact distribution — count, central tendency, spread and percentile tails.
That summary is the raw material from which the §7.7 *типичные диапазоны*
(typical bands) feeding :mod:`kg_extractors.property_ranges` are derived.

Pure Python, stdlib :mod:`statistics` only — no numpy, no LLM, no I/O.

RU/EN: сводная статистика популяции измерений для вывода типичных диапазонов.
"""

from __future__ import annotations

import statistics as st
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PopulationSummary:
    """Compact distribution of a measurement population (§7.7).

    Fields
    ------
    n
        Number of usable (numeric) values summarised (объём выборки).
    mean
        Arithmetic mean (среднее).
    median
        Median, the 50th percentile (медиана).
    stdev
        Sample standard deviation; ``0.0`` for a single value (стандартное
        отклонение).
    p05, p95
        5th / 95th percentiles — the robust distribution tails used to seed a
        typical band (перцентильные хвосты).
    minimum, maximum
        Smallest / largest values (минимум / максимум).
    unit
        Canonical unit the values are expressed in, or ``None`` (единица).
    """

    n: int
    mean: float
    median: float
    stdev: float
    p05: float
    p95: float
    minimum: float
    maximum: float
    unit: str | None

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "n": self.n,
            "mean": self.mean,
            "median": self.median,
            "stdev": self.stdev,
            "p05": self.p05,
            "p95": self.p95,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "unit": self.unit,
        }


def _to_float(value: object) -> float | None:
    """Coerce *value* to ``float`` (comma decimals allowed); ``None`` on failure."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _coerce_all(values: Iterable[object]) -> list[float]:
    """Coerce an iterable to floats, silently skipping non-numeric entries."""
    out: list[float] = []
    for v in values:
        f = _to_float(v)
        if f is not None:
            out.append(f)
    return out


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile ``q`` (0..100) of *values* (§7.7).

    Uses the ``(n - 1) · q/100`` rank convention: the fractional rank is split
    into a lower index and a fraction, then linearly interpolated between the
    two straddling sorted values. ``q == 0`` returns the minimum, ``q == 100``
    the maximum. Raises :class:`ValueError` on an empty sequence or a ``q``
    outside ``[0, 100]`` (линейная интерполяция перцентиля).
    """
    xs = sorted(_coerce_all(values))
    if not xs:
        raise ValueError("percentile of empty sequence")
    if not 0.0 <= q <= 100.0:
        raise ValueError(f"q must be in [0, 100], got {q!r}")
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * (q / 100.0)
    lo = int(rank)  # floor
    frac = rank - lo
    if lo + 1 >= len(xs):
        return xs[lo]
    return xs[lo] + frac * (xs[lo + 1] - xs[lo])


def summarize_population(values: Iterable[float], unit: str | None = None) -> PopulationSummary:
    """Summarise a measurement population into a :class:`PopulationSummary` (§7.7).

    Non-numeric entries are coerced where possible (comma decimals) and skipped
    otherwise. An empty population (after coercion) raises :class:`ValueError`;
    a single value yields ``stdev == 0.0`` and identical percentiles/extrema.

    RU/EN: свернуть популяцию значений в компактное распределение.
    """
    xs = _coerce_all(values)
    if not xs:
        raise ValueError("cannot summarize an empty population")
    stdev = st.stdev(xs) if len(xs) > 1 else 0.0
    return PopulationSummary(
        n=len(xs),
        mean=st.fmean(xs),
        median=st.median(xs),
        stdev=stdev,
        p05=percentile(xs, 5.0),
        p95=percentile(xs, 95.0),
        minimum=min(xs),
        maximum=max(xs),
        unit=unit,
    )


def suggest_typical_band(values: Iterable[float], k: float = 1.5) -> tuple[float, float]:
    """Suggest a typical band ``(lo, hi)`` via a Tukey IQR fence (§7.7).

    Returns ``(Q1 - k·IQR, Q3 + k·IQR)`` with quartiles from :func:`percentile`
    (25th / 75th). The fence trims statistical outliers from the band, so an
    extreme value sits *outside* the returned range. Fewer than two usable
    values collapse the band to ``(x, x)`` (or raise on empty). ``k`` widens or
    tightens the fence (граница типичного диапазона по межквартильному размаху).
    """
    xs = _coerce_all(values)
    if not xs:
        raise ValueError("cannot suggest a band for an empty population")
    if len(xs) == 1:
        return (xs[0], xs[0])
    q1 = percentile(xs, 25.0)
    q3 = percentile(xs, 75.0)
    iqr = q3 - q1
    return (q1 - k * iqr, q3 + k * iqr)
