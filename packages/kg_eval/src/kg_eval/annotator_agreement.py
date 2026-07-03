"""Inter-annotator agreement / quality control разметки (§23.26).

Pure-stdlib scoring of two annotators' categorical labels keyed by item id — the
quality-control half of the annotation protocol (§23.26: разметка золотых данных
двумя разметчиками, контроль согласованности). Only *shared* item ids (present in
both annotators' maps) are scored; items seen by a single annotator are ignored so
partial coverage never inflates or deflates agreement.

Metrics:

* ``percent_agreement`` — observed agreement ``po`` = fraction of shared items where
  both annotators assigned the same label.
* ``cohen_kappa`` — chance-corrected agreement ``(po - pe) / (1 - pe)`` where ``pe``
  is the expected agreement from each annotator's marginal label distribution.
  When ``po == 1.0`` (perfect agreement) kappa collapses to ``1.0`` even if the
  degenerate ``pe == 1.0`` would otherwise make the ratio ``0/0``.

Empty overlap (no shared ids) is a caller bug and raises ``ValueError`` rather than
returning a meaningless ``0/0``. Kappa is always in ``[-1.0, 1.0]``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelAgreement:
    """Per-label counts across the shared item ids (§23.26).

    ``a_count``/``b_count`` — how often each annotator used ``label``; ``agreed`` —
    how many shared items where *both* assigned ``label``.
    """

    label: str
    a_count: int
    b_count: int
    agreed: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "label": self.label,
            "a_count": self.a_count,
            "b_count": self.b_count,
            "agreed": self.agreed,
        }


@dataclass(frozen=True)
class AgreementReport:
    """Inter-annotator agreement summary over shared item ids (§23.26).

    ``n_items`` counts only ids present in *both* annotators' maps. ``per_label`` is
    ordered by label; ``disagreements`` is the sorted tuple of mismatched shared ids.
    """

    n_items: int
    observed_agreement: float
    expected_agreement: float
    cohen_kappa: float
    per_label: tuple[LabelAgreement, ...]
    disagreements: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "n_items": self.n_items,
            "observed_agreement": round(self.observed_agreement, 4),
            "expected_agreement": round(self.expected_agreement, 4),
            "cohen_kappa": round(self.cohen_kappa, 4),
            "per_label": [la.as_dict() for la in self.per_label],
            "disagreements": list(self.disagreements),
        }


def _shared_ids(a: Mapping[str, str], b: Mapping[str, str]) -> list[str]:
    """Sorted item ids present in *both* annotator maps; empty → ``ValueError``."""
    shared = sorted(set(a) & set(b))
    if not shared:
        raise ValueError("no shared item ids between annotators")
    return shared


def percent_agreement(a: Mapping[str, str], b: Mapping[str, str]) -> float:
    """Observed agreement ``po`` over shared ids — fraction with identical labels."""
    shared = _shared_ids(a, b)
    agreed = sum(1 for i in shared if a[i] == b[i])
    return agreed / len(shared)


def cohen_kappa(a: Mapping[str, str], b: Mapping[str, str]) -> float:
    """Cohen's kappa over shared ids: ``(po - pe) / (1 - pe)``.

    Returns ``1.0`` when ``po == 1.0`` even if ``pe == 1.0`` (degenerate single-label
    case). Otherwise a ``pe == 1.0`` with imperfect ``po`` cannot occur, so the
    denominator is well defined. Result is clamped to ``[-1.0, 1.0]``.
    """
    shared = _shared_ids(a, b)
    n = len(shared)
    po = sum(1 for i in shared if a[i] == b[i]) / n
    if po == 1.0:
        return 1.0

    labels = {a[i] for i in shared} | {b[i] for i in shared}
    pe = 0.0
    for label in labels:
        pa = sum(1 for i in shared if a[i] == label) / n
        pb = sum(1 for i in shared if b[i] == label) / n
        pe += pa * pb

    if pe == 1.0:
        return 1.0
    kappa = (po - pe) / (1.0 - pe)
    return max(-1.0, min(1.0, kappa))


def disagreement_ids(a: Mapping[str, str], b: Mapping[str, str]) -> tuple[str, ...]:
    """Sorted tuple of shared ids where the two annotators assigned different labels."""
    shared = _shared_ids(a, b)
    return tuple(i for i in shared if a[i] != b[i])


def agreement_report(a: Mapping[str, str], b: Mapping[str, str]) -> AgreementReport:
    """Full :class:`AgreementReport` over the shared ids of ``a`` and ``b``.

    Raises ``ValueError`` when the two maps share no item ids.
    """
    shared = _shared_ids(a, b)
    n = len(shared)
    po = percent_agreement(a, b)
    pe = 0.0
    labels = sorted({a[i] for i in shared} | {b[i] for i in shared})
    per_label: list[LabelAgreement] = []
    for label in labels:
        a_count = sum(1 for i in shared if a[i] == label)
        b_count = sum(1 for i in shared if b[i] == label)
        agreed = sum(1 for i in shared if a[i] == label and b[i] == label)
        per_label.append(LabelAgreement(label, a_count, b_count, agreed))
        pe += (a_count / n) * (b_count / n)

    kappa = cohen_kappa(a, b)
    return AgreementReport(
        n_items=n,
        observed_agreement=po,
        expected_agreement=pe,
        cohen_kappa=kappa,
        per_label=tuple(per_label),
        disagreements=disagreement_ids(a, b),
    )
