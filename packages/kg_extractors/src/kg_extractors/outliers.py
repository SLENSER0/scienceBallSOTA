"""Statistical outlier detection over a measurement population (§7.7).

The named *детект выбросов* deliverable: given a flat population of extracted
measurements, flag values that are statistically anomalous **within their own
peer group** — the ``(material_class, property)`` cohort — so a curator never
compares the hardness of a steel against the hardness of a ceramic.

Two complementary, robust (outlier-resistant) tests are applied per group and
combined with **OR** (a value flagged by either test is an outlier):

* **IQR fence** (межквартильный размах, Tukey) — a value below
  ``Q1 - 1.5·IQR`` or above ``Q3 + 1.5·IQR`` (:func:`iqr_bounds`). Distribution
  free; the classic box-plot whisker rule.
* **Robust z-score** (модифицированный z-счёт, Iglewicz–Hoaglin) — the
  median/MAD score ``(x - median) / (1.4826·MAD)`` (:func:`robust_zscore`);
  a magnitude above ``z_thresh`` (default ``3.5``) is anomalous. The ``1.4826``
  factor rescales the MAD to be a consistent estimator of the standard
  deviation for normal data, so the ``3.5`` cutoff mirrors a ~3.5σ rule.

A separate cheap heuristic, :func:`unit_scale_suspect`, catches the common
data-entry blunder of an order-of-magnitude unit slip (×10 / ×100 / ×1000,
e.g. ``1480`` recorded where the cohort typically sits near ``148``).

Groups smaller than :data:`MIN_GROUP_SIZE` are statistically meaningless, so
they are returned untouched (never flagged) rather than raising — the pipeline
must survive a lone measurement gracefully. Pure Python, stdlib
:mod:`statistics` only — no numpy, no LLM, no I/O.
"""

from __future__ import annotations

import math
import statistics as st
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

#: MAD → σ consistency factor (нормирующий множитель) for normal data.
MAD_SCALE = 1.4826

#: Minimum group size for which outlier tests are trusted (меньше ⇒ пропуск).
MIN_GROUP_SIZE = 4

#: Default robust z-score cutoff (порог), Iglewicz–Hoaglin recommend 3.5.
DEFAULT_Z_THRESH = 3.5

#: Default grouping key — the peer cohort a value is judged against (§7.7).
DEFAULT_GROUP_KEY: tuple[str, str] = ("material_class", "property")

# --- method tokens (метод, сработавший на значении) --------------------------
METHOD_NONE = "none"  # не выброс
METHOD_IQR = "iqr"  # межквартильная граница
METHOD_ROBUST_Z = "robust_z"  # модифицированный z-счёт
METHOD_BOTH = "iqr+robust_z"  # обе проверки

#: Log10 tolerance for :func:`unit_scale_suspect` — how close the ratio must
#: sit to a clean power of ten (допуск близости к порядку величины).
_SCALE_LOG_TOL = 0.2


@dataclass(frozen=True)
class OutlierFlag:
    """Per-value outlier verdict within its group (§7.7).

    Fields
    ------
    value
        The measurement value that was judged (проверяемое значение).
    group
        The peer-cohort key tuple the value was compared against — e.g.
        ``("steel", "hardness")`` (группа-когорта).
    method
        Which test(s) fired: ``"none"`` / ``"iqr"`` / ``"robust_z"`` /
        ``"iqr+robust_z"`` (сработавший метод).
    score
        The robust (median/MAD) z-score of the value, always reported for
        context even when the IQR fence is what flagged it (робастный z-счёт).
    is_outlier
        ``True`` iff either test flagged the value (признак выброса).
    """

    value: float
    group: tuple[object, ...]
    method: str
    score: float
    is_outlier: bool

    def as_dict(self) -> dict[str, object]:
        """Full structured view (все поля)."""
        return {
            "value": self.value,
            "group": self.group,
            "method": self.method,
            "score": self.score,
            "is_outlier": self.is_outlier,
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


def iqr_bounds(values: Iterable[float]) -> tuple[float, float]:
    """Tukey IQR outlier fence ``(lo, hi)`` for *values* (§7.7).

    Returns ``(Q1 - 1.5·IQR, Q3 + 1.5·IQR)`` using linear-interpolation
    (``"inclusive"``) quartiles. A value outside ``[lo, hi]`` is an outlier by
    the межквартильный размах rule. Fewer than two points yield an open fence
    ``(-inf, +inf)`` so nothing is flagged (graceful, никогда не падает).
    """
    xs = sorted(_coerce_all(values))
    if len(xs) < 2:
        return (float("-inf"), float("inf"))
    q1, _q2, q3 = st.quantiles(xs, n=4, method="inclusive")
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def robust_zscore(values: Iterable[float]) -> list[float]:
    """Modified (median/MAD) z-scores for *values* (§7.7).

    Each score is ``(x - median) / (1.4826·MAD)`` where ``MAD`` is the median
    absolute deviation from the median — the Iglewicz–Hoaglin robust z-счёт.
    When ``MAD == 0`` (a homogeneous group, no spread) the divisor would be
    zero, so all scores collapse to ``0.0`` (guard against ÷0). An empty input
    yields ``[]``.
    """
    xs = _coerce_all(values)
    if not xs:
        return []
    med = st.median(xs)
    mad = st.median([abs(x - med) for x in xs])
    scaled = MAD_SCALE * mad
    if scaled == 0:  # homogeneous group — no spread, nothing deviates
        return [0.0 for _ in xs]
    return [(x - med) / scaled for x in xs]


def unit_scale_suspect(value: float, typical: float) -> bool:
    """Heuristic: is *value* an order-of-magnitude unit slip vs *typical*? (§7.7).

    Flags the classic ×10 / ×100 / ×1000 data-entry error — e.g. ``1480``
    recorded where the cohort typically sits near ``148`` (ratio ≈ 10). Returns
    ``True`` iff ``|value|/|typical|`` lands close to a *non-unit* power of ten
    (its base-10 log rounds to a nonzero integer within a tight tolerance).
    Same-order-of-magnitude values (ratio near 1) and non-positive magnitudes
    return ``False`` (подозрение на ошибку масштаба).
    """
    v = _to_float(value)
    t = _to_float(typical)
    if v is None or t is None:
        return False
    v, t = abs(v), abs(t)
    if v == 0 or t == 0:
        return False
    exponent = math.log10(v / t)
    nearest = round(exponent)
    return nearest != 0 and abs(exponent - nearest) <= _SCALE_LOG_TOL


def detect_outliers(
    rows: Iterable[Mapping[str, object]],
    *,
    group_key: Sequence[str] = DEFAULT_GROUP_KEY,
    z_thresh: float = DEFAULT_Z_THRESH,
) -> list[OutlierFlag]:
    """Flag outliers per ``(material_class, property)`` group (§7.7).

    Each *row* is a mapping carrying a numeric ``"value"`` plus the *group_key*
    fields (default ``("material_class", "property")``). Rows are partitioned
    into peer cohorts and, within each cohort of at least :data:`MIN_GROUP_SIZE`
    values, flagged when they fall outside the :func:`iqr_bounds` fence **or**
    exceed *z_thresh* in :func:`robust_zscore` magnitude. Smaller cohorts are
    returned unflagged (graceful). Output preserves input row order; rows whose
    ``"value"`` is non-numeric are skipped. An empty input yields ``[]``.
    """
    records: list[tuple[tuple[object, ...], float]] = []
    group_vals: dict[tuple[object, ...], list[float]] = {}
    for row in rows:
        v = _to_float(row.get("value"))
        if v is None:  # skip rows with no usable numeric value
            continue
        group = tuple(row.get(k) for k in group_key)
        group_vals.setdefault(group, []).append(v)
        records.append((group, v))

    if not records:
        return []

    group_bounds: dict[tuple[object, ...], tuple[float, float] | None] = {}
    group_scores: dict[tuple[object, ...], list[float]] = {}
    for group, vals in group_vals.items():
        big_enough = len(vals) >= MIN_GROUP_SIZE
        group_bounds[group] = iqr_bounds(vals) if big_enough else None
        group_scores[group] = robust_zscore(vals)

    cursor: dict[tuple[object, ...], int] = dict.fromkeys(group_vals, 0)
    flags: list[OutlierFlag] = []
    for group, v in records:
        idx = cursor[group]
        cursor[group] = idx + 1
        score = group_scores[group][idx]
        bounds = group_bounds[group]

        by_iqr = bounds is not None and (v < bounds[0] or v > bounds[1])
        by_z = bounds is not None and abs(score) > z_thresh
        method = _method_token(by_iqr, by_z)
        flags.append(
            OutlierFlag(
                value=v,
                group=group,
                method=method,
                score=score,
                is_outlier=by_iqr or by_z,
            )
        )
    return flags


def _coerce_all(values: Iterable[float]) -> list[float]:
    """Coerce an iterable to a list of floats, dropping non-numeric entries."""
    out: list[float] = []
    for value in values:
        v = _to_float(value)
        if v is not None:
            out.append(v)
    return out


def _method_token(by_iqr: bool, by_z: bool) -> str:
    """Name the test(s) that fired (сработавший метод)."""
    if by_iqr and by_z:
        return METHOD_BOTH
    if by_iqr:
        return METHOD_IQR
    if by_z:
        return METHOD_ROBUST_Z
    return METHOD_NONE
