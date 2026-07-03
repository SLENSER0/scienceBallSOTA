"""§25.11 — multi-document absence posterior (много-документный пробел).

Distinct from the single-recall :func:`kg_retrievers.absence_bayes.posterior_absence`:
here ``K`` documents each **mention** a ``(material, property)`` cell, each with its
own extractor recall ``r_i``, and **nothing** was extracted from any of them. A miss
now requires *every* extractor to have missed independently, so the combined miss
probability is the product of the per-document miss chances::

    combined_miss = Π_i (1 - r_i)

With prior ``e = P(exists)`` the "no evidence across K docs" posterior is::

    P(missed | no evidence) = e · combined_miss / (e · combined_miss + (1 - e))
    P(absent | no evidence) = 1 - P(missed | no evidence)

More corroborating documents (each with recall > 0) drive ``combined_miss`` down,
so an empty cell reads *less* like a miss and *more* like a настоящий пробел —
the posterior is monotone in the number of docs. Один документ с recall = 1.0
делает ``combined_miss = 0``: extraction never misses, so absence is certain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp01(x: float) -> float:
    """Clamp ``x`` into the closed interval ``[0, 1]`` (§25.11 input hygiene)."""
    return max(0.0, min(float(x), 1.0))


@dataclass(frozen=True)
class MultiDocAbsence:
    """Multi-document absence posteriors for a cell mentioned by ``n_docs`` docs.

    ``combined_miss`` is Π (1 - r_i) over the per-document recalls. ``p_extractor_missed``
    and ``p_truly_absent`` are the "no evidence across all docs" posteriors (each in
    ``[0, 1]``; they sum to 1). ``n_docs`` is the number of recalls combined.
    """

    p_extractor_missed: float
    p_truly_absent: float
    combined_miss: float
    n_docs: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "p_extractor_missed": self.p_extractor_missed,
            "p_truly_absent": self.p_truly_absent,
            "combined_miss": self.combined_miss,
            "n_docs": self.n_docs,
        }


def combined_miss_probability(recalls: list[float]) -> float:
    """Probability *every* extractor missed -> Π (1 - r_i), recalls clamped to ``[0, 1]``.

    An empty list is the empty product ``1.0`` (no extractor ran, so a miss is
    vacuously certain). Any recall of ``1.0`` collapses the product to ``0.0``.
    """
    product = 1.0
    for r in recalls:
        product *= 1.0 - _clamp01(r)
    return product


def posterior_multidoc(exists_prior: float, recalls: list[float]) -> MultiDocAbsence:
    """Combine ``K`` per-document misses on *no evidence* -> :class:`MultiDocAbsence`.

    ``exists_prior`` is ``e = P(the datum exists)``; ``recalls`` are the per-document
    extractor recalls. All are clamped to ``[0, 1]``. When the denominator collapses to
    ``0`` (``e = 1`` and ``combined_miss = 0``: the datum certainly exists yet no extractor
    can miss), a no-evidence cell cannot be a miss, so ``p_extractor_missed = 0``.
    """
    e = _clamp01(exists_prior)
    combined_miss = combined_miss_probability(recalls)
    num_missed = e * combined_miss  # exists yet every extractor missed
    num_absent = 1.0 - e  # truly absent -> no evidence with certainty
    denom = num_missed + num_absent
    p_extractor_missed = 0.0 if denom <= 0.0 else num_missed / denom
    p_truly_absent = 1.0 - p_extractor_missed
    return MultiDocAbsence(
        p_extractor_missed=p_extractor_missed,
        p_truly_absent=p_truly_absent,
        combined_miss=combined_miss,
        n_docs=len(recalls),
    )
