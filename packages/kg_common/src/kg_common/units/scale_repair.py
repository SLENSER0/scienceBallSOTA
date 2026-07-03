"""Unit-scale error repair suggestions (§7.7) — factor 10/100/1000.

``outliers.unit_scale_suspect`` только сообщает *bool* «похоже на ошибку
масштаба» относительно заданного типичного значения. §7.7 просит, помимо
детекции, *предложить вероятное исправление*. Этот модуль — policy-band-driven
repair suggester: он читает типичную полосу (``typical_min``/``typical_max``,
с откатом к жёстким ``min``/``max``) из
:data:`kg_common.units.policy.PROPERTY_UNIT_POLICY` и, если значение выходит за
полосу, перебирает степени десяти ``(0.001, 0.01, 0.1, 1, 10, 100, 1000)``,
возвращая *первый* множитель, после умножения на который значение попадает
внутрь полосы.

If the value is already inside the band, the suggested factor is ``1.0`` and
``in_band`` is ``True`` — исправление не требуется.

Pure python — no external dependency beyond the policy table.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .policy import PROPERTY_UNIT_POLICY

# Candidate scale factors, tried in this order (§7.7). Первый множитель,
# после которого значение попадает в полосу, и есть предложение.
_SCALE_FACTORS: tuple[float, ...] = (0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)


@dataclass(frozen=True)
class ScaleRepair:
    """Suggested scale-error repair for one measurement (§7.7).

    Attributes / поля:

    * ``property_id``     — canonical ``prop:*`` id the value belongs to.
    * ``value``           — the original (suspect) value.
    * ``suggested_factor``— множитель-исправление (``1.0`` ⇒ ничего не менять).
    * ``corrected_value`` — ``value * suggested_factor``.
    * ``in_band``         — ``True`` iff the *original* value already sits inside
      the typical band (then ``suggested_factor == 1.0``).
    * ``reason``          — human-readable RU/EN explanation.
    """

    property_id: str
    value: float
    suggested_factor: float
    corrected_value: float
    in_band: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _band(spec: dict[str, object]) -> tuple[float | None, float | None]:
    """Return the (lo, hi) plausibility band for a policy *spec*.

    Prefer ``typical_min``/``typical_max``; fall back to the hard ``min``/``max``
    when a typical bound is absent (e.g. percentage properties).
    """
    lo = spec.get("typical_min", spec.get("min"))
    hi = spec.get("typical_max", spec.get("max"))
    lo_f = None if lo is None else float(lo)  # type: ignore[arg-type]
    hi_f = None if hi is None else float(hi)  # type: ignore[arg-type]
    return lo_f, hi_f


def _inside(value: float, lo: float | None, hi: float | None) -> bool:
    """True iff *value* lies within the (possibly half-open) band ``[lo, hi]``."""
    above_lo = lo is None or value >= lo
    below_hi = hi is None or value <= hi
    return above_lo and below_hi


def suggest_scale_repair(value: float, property_id: str) -> ScaleRepair:
    """Suggest a factor-of-ten scale repair for *value* under *property_id* (§7.7).

    Reads the typical band from :data:`PROPERTY_UNIT_POLICY`. If the value is
    already inside the band, returns ``suggested_factor == 1.0`` and
    ``in_band=True``. Otherwise tries the scale factors
    ``(0.001, 0.01, 0.1, 1, 10, 100, 1000)`` in order and returns the first that
    lands the value inside the band. If none fits (or the property is unknown /
    has no band), returns ``suggested_factor == 1.0`` with ``in_band=False``.
    """
    spec = PROPERTY_UNIT_POLICY.get(property_id)
    if spec is None:
        return ScaleRepair(
            property_id, value, 1.0, value, False, f"no unit policy for {property_id!r}"
        )

    lo, hi = _band(spec)
    if lo is None and hi is None:
        return ScaleRepair(property_id, value, 1.0, value, False, "no plausibility band")

    lo_s = "-inf" if lo is None else f"{lo:g}"
    hi_s = "+inf" if hi is None else f"{hi:g}"

    if _inside(value, lo, hi):
        return ScaleRepair(
            property_id, value, 1.0, value, True, f"{value:g} already in band [{lo_s}, {hi_s}]"
        )

    for factor in _SCALE_FACTORS:
        corrected = value * factor
        if _inside(corrected, lo, hi):
            return ScaleRepair(
                property_id,
                value,
                factor,
                corrected,
                False,
                f"{value:g} out of band [{lo_s}, {hi_s}]; ×{factor:g} → {corrected:g}",
            )

    return ScaleRepair(
        property_id,
        value,
        1.0,
        value,
        False,
        f"{value:g} out of band [{lo_s}, {hi_s}]; no scale factor lands inside",
    )
