"""Krippendorff's alpha (nominal metric) для золотого набора (§18.6).

Fleiss' kappa (see :mod:`kg_eval.fleiss_kappa`) needs a *fixed* panel size per item
and cannot tolerate missing labels. Krippendorff's alpha — согласие разметчиков при
неполной разметке (§18.6) — handles a variable number of coders per unit and freely
missing values, which is the realistic shape of a golden-set annotation table.

Input is one ``coder_id -> per-unit values`` mapping; ``None`` marks a value the coder
did not assign. All coders must supply the same number of units. A unit is *pairable*
only when at least two of its values are present; units with fewer are dropped.

Definitions (nominal difference ``δ²_{ck} = 0`` if ``c == k`` else ``1``):

* coincidence matrix ``o_{ck} = Σ_u (pairs of (c, k) within unit u) / (m_u − 1)`` where
  ``m_u`` is the count of present values in unit ``u`` (ordered pairs, ``i ≠ j``);
* value marginal ``n_c = Σ_k o_{ck}`` and total ``n = Σ_c n_c = Σ_u m_u`` (n_pairable);
* observed disagreement ``D_o = (1/n) Σ_{c≠k} o_{ck}``;
* expected disagreement ``D_e = (1/(n(n−1))) Σ_{c≠k} n_c n_k``;
* ``alpha = 1 − D_o / D_e``.

Empty input or no pairable values raises ``ValueError``. If every pairable value is
identical (``D_e == 0``) agreement is perfect and alpha collapses to ``1.0`` rather
than a ``0/0`` division.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class AlphaReport:
    """Krippendorff's alpha summary over a golden annotation table (§18.6).

    ``n_units`` is the total number of units supplied; ``n_pairable`` is the count of
    present values living in pairable units (``Σ_u m_u``). ``d_observed`` and
    ``d_expected`` are ``D_o`` / ``D_e`` and ``alpha`` the chance-corrected agreement.
    """

    n_units: int
    n_pairable: int
    d_observed: float
    d_expected: float
    alpha: float

    def as_dict(self) -> dict[str, object]:
        return {
            "n_units": self.n_units,
            "n_pairable": self.n_pairable,
            "d_observed": round(self.d_observed, 4),
            "d_expected": round(self.d_expected, 4),
            "alpha": round(self.alpha, 4),
        }


def krippendorff_alpha_nominal(data: Mapping[str, Sequence[object | None]]) -> AlphaReport:
    """Compute :class:`AlphaReport` from a ``coder_id -> per-unit values`` mapping.

    ``None`` marks a missing value. All coders must have the same unit count; units with
    fewer than two present values are dropped. Empty input or no pairable values raises
    ``ValueError``.
    """
    coders = list(data.keys())
    if not coders:
        raise ValueError("no coders supplied")

    lengths = {len(values) for values in data.values()}
    if len(lengths) > 1:
        raise ValueError(f"ragged coder value sequences: lengths {sorted(lengths)}")
    n_units = lengths.pop()

    # Coincidence matrix over ordered pairs of present values, weighted by 1/(m_u - 1).
    coincidence: dict[tuple[object, object], float] = {}
    n_pairable = 0
    for unit_idx in range(n_units):
        present = [data[c][unit_idx] for c in coders if data[c][unit_idx] is not None]
        m = len(present)
        if m < 2:
            continue
        n_pairable += m
        weight = 1.0 / (m - 1)
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                key = (present[i], present[j])
                coincidence[key] = coincidence.get(key, 0.0) + weight

    if n_pairable == 0 or not coincidence:
        raise ValueError("no pairable values: need >=1 unit with >=2 present values")

    # Value marginals n_c as coincidence row sums; total n == n_pairable.
    marginals: dict[object, float] = {}
    for (c, _k), o in coincidence.items():
        marginals[c] = marginals.get(c, 0.0) + o
    n = float(n_pairable)

    d_observed = sum(o for (c, k), o in coincidence.items() if c != k) / n

    off_diag = sum(marginals[c] * marginals[k] for c in marginals for k in marginals if c != k)
    d_expected = off_diag / (n * (n - 1.0))

    # All pairable values identical → perfect agreement, avoid 0/0.
    alpha = 1.0 if d_expected == 0.0 else 1.0 - d_observed / d_expected

    return AlphaReport(
        n_units=n_units,
        n_pairable=n_pairable,
        d_observed=d_observed,
        d_expected=d_expected,
        alpha=alpha,
    )
