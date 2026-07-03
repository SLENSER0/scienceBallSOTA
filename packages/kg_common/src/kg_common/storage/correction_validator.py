"""Action ``correct`` — валидация единиц и пересчёт ``value_normalized`` (§16.6).

When a curator *corrects* a measured property they supply a new ``(value, unit)``
pair. Before the correction is accepted the new unit must be **dimensionally
compatible** with the property's target unit (you may not «correct» a length into
a mass), and the value must be **re-expressed** in that target unit so the stored
``value_normalized`` stays comparable across records.

This module leans on :mod:`kg_common.units.conversions`
(:func:`~kg_common.units.conversions.are_compatible`,
:func:`~kg_common.units.conversions.dimension_of`,
:func:`~kg_common.units.conversions.convert`) for the dimension arithmetic, and
adds a small **SI-prefix expander** so prefixed spellings the conversion registry
does not carry verbatim (``km``, ``cm``, …) still resolve to a known base unit
plus a scaling factor.

Public API:

* :class:`CorrectionResult` — frozen outcome with :meth:`~CorrectionResult.as_dict`.
* :func:`validate_correction` — validate a new ``(value, unit)`` against a target.
* :func:`raise_status`        — map an outcome to an HTTP status (200 / 422).

Pure Python, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.units.conversions import (
    are_compatible,
    convert,
    dimension_of,
    is_known_unit,
)

# HTTP статусы результата коррекции (§16.6).
STATUS_OK = 200
STATUS_DIMENSION_MISMATCH = 422

# ---------------------------------------------------------------------------
# §16.6 — SI-приставки. Единицы вроде ``km``/``cm`` отсутствуют в реестре
# конвертаций дословно, поэтому раскладываем «приставка + базовая единица».
# Longer prefixes first so ``da`` is tried before ``d``.
# ---------------------------------------------------------------------------
_SI_PREFIXES: tuple[tuple[str, float], ...] = (
    ("da", 1e1),
    ("Y", 1e24),
    ("Z", 1e21),
    ("E", 1e18),
    ("P", 1e15),
    ("T", 1e12),
    ("G", 1e9),
    ("M", 1e6),
    ("k", 1e3),
    ("h", 1e2),
    ("d", 1e-1),
    ("c", 1e-2),
    ("m", 1e-3),
    ("µ", 1e-6),
    ("μ", 1e-6),
    ("u", 1e-6),
    ("n", 1e-9),
    ("p", 1e-12),
    ("f", 1e-15),
)


@dataclass(frozen=True)
class CorrectionResult:
    """Итог валидации коррекции единиц — результат действия ``correct`` (§16.6).

    ``ok``               — прошла ли проверка размерности.
    ``value``            — исходное скорректированное значение (echo of the input).
    ``unit``             — исходная единица коррекции (echo of ``new_unit``).
    ``value_normalized`` — значение, пересчитанное в ``base_unit``; ``None`` on failure.
    ``base_unit``        — целевая единица нормализации; ``None`` on failure.
    ``error``            — человекочитаемая причина отказа; ``None`` on success.
    """

    ok: bool
    value: float | None
    unit: str | None
    value_normalized: float | None
    base_unit: str | None
    error: str | None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — строка результата коррекции (§16.6)."""
        return {
            "ok": self.ok,
            "value": self.value,
            "unit": self.unit,
            "value_normalized": self.value_normalized,
            "base_unit": self.base_unit,
            "error": self.error,
        }


def _expand(unit: str) -> tuple[str | None, float]:
    """Resolve *unit* to ``(base_symbol, factor)`` known to conversions (§16.6).

    Returns the unit itself with ``factor == 1.0`` when the conversion registry
    already knows it; otherwise strips a leading SI prefix and returns the base
    symbol plus the prefix's multiplier (``km`` → ``("m", 1000.0)``). Yields
    ``(None, 1.0)`` when nothing resolves — неизвестная единица.
    """
    if is_known_unit(unit):
        return unit, 1.0
    for prefix, factor in _SI_PREFIXES:
        if len(unit) > len(prefix) and unit.startswith(prefix):
            rest = unit[len(prefix) :]
            if is_known_unit(rest):
                return rest, factor
    return None, 1.0


def _describe(unit: str, base: str | None) -> str:
    """Best-effort ``"unit (dimension)"`` label for an error message (§16.6)."""
    if base is None:
        return f"{unit!r} (unknown)"
    try:
        return f"{unit!r} ({dimension_of(base)})"
    except ValueError:
        return f"{unit!r} (unknown)"


def validate_correction(
    new_value: float,
    new_unit: str,
    target_dimension_unit: str,
) -> CorrectionResult:
    """Validate a corrected ``(value, unit)`` and recompute normalized value (§16.6).

    If *new_unit* is dimensionally **incompatible** with *target_dimension_unit*
    (or either unit is unknown) returns ``ok=False`` with an ``error`` and
    ``value_normalized=None``. Otherwise converts *new_value* into
    *target_dimension_unit* — «базовую единицу цели» — and returns ``ok=True``
    with the normalized value and ``base_unit == target_dimension_unit``.
    """
    value = float(new_value)
    base_new, factor_new = _expand(new_unit)
    base_tgt, factor_tgt = _expand(target_dimension_unit)

    if base_new is None or base_tgt is None or not are_compatible(base_new, base_tgt):
        error = (
            f"unit {_describe(new_unit, base_new)} is not dimensionally compatible "
            f"with target {_describe(target_dimension_unit, base_tgt)}"
        )
        return CorrectionResult(
            ok=False,
            value=value,
            unit=new_unit,
            value_normalized=None,
            base_unit=None,
            error=error,
        )

    # Value on *new_unit* → value on *base_new* → convert to *base_tgt* → *target*.
    base_value = convert(value * factor_new, base_new, base_tgt)
    normalized = base_value / factor_tgt
    return CorrectionResult(
        ok=True,
        value=value,
        unit=new_unit,
        value_normalized=normalized,
        base_unit=target_dimension_unit,
        error=None,
    )


def raise_status(result: CorrectionResult) -> int:
    """Map a :class:`CorrectionResult` to an HTTP status code (§16.6).

    ``200`` when the correction validated; ``422`` on a dimension mismatch (or an
    otherwise-rejected unit).
    """
    return STATUS_OK if result.ok else STATUS_DIMENSION_MISMATCH


__all__ = [
    "STATUS_DIMENSION_MISMATCH",
    "STATUS_OK",
    "CorrectionResult",
    "raise_status",
    "validate_correction",
]
