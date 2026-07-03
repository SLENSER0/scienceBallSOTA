"""Inter-configuration agreement for absence verdicts (Cohen's kappa) (§25.15).

В отличие от :mod:`kg_eval.absence_verdict_confusion` (который сверяет предсказанные
verdict'ы с золотыми метками), этот модуль измеряет *согласованность двух конфигураций*
между собой: две absence-карты, построенные под разными priors/backends, сравниваются
по общим ячейкам без обращения к gold-разметке.

Unlike the gold-scored confusion matrix, this is a *reliability* measure between two
runs: we join two absence maps on shared ``(material_id, property_name)`` keys, then
report raw agreement, Cohen's kappa (chance-corrected against marginal verdict
frequencies) and a flip matrix counting each ``a->b`` disagreement.

Соглашения о вырожденных случаях: пустое пересечение ключей даёт ``n == 0`` и
``cohen_kappa == 0.0``; когда ожидаемое случайное согласие ``pe == 1.0`` (обе стороны
всегда выдают один и тот же verdict), ``cohen_kappa`` считается равным ``1.0``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

KeySpec = tuple[str, ...]
"""Кортеж имён полей, образующих ключ соединения (join key)."""


@dataclass(frozen=True)
class VerdictAgreement:
    """Inter-configuration verdict agreement over shared cells (§25.15).

    ``n`` — число общих ячеек (shared keys); ``n_agree`` — сколько из них совпало по
    verdict'у. ``raw_agreement == n_agree / n`` (observed agreement ``po``).
    ``cohen_kappa`` — chance-corrected ``(po - pe) / (1 - pe)``, где ``pe`` оценивается по
    маргинальным частотам verdict'ов; равен ``1.0`` при ``1 - pe == 0`` и ``0.0`` при
    ``n == 0``. ``flip_matrix`` содержит счётчики расхождений с ключами вида ``'a->b'``.
    """

    n: int
    n_agree: int
    raw_agreement: float
    cohen_kappa: float
    flip_matrix: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        """Serialise to plain JSON-friendly dicts (сериализация в обычные dict)."""
        return {
            "n": self.n,
            "n_agree": self.n_agree,
            "raw_agreement": round(self.raw_agreement, 4),
            "cohen_kappa": round(self.cohen_kappa, 4),
            "flip_matrix": dict(self.flip_matrix),
        }


def _index(cells: list[dict], key: KeySpec, verdict_key: str) -> dict[tuple, str]:
    """Index ``cells`` by their join key, keeping the verdict value (последний выигрывает).

    Ячейки без полного ключа или без ``verdict_key`` пропускаются, чтобы соединение шло
    только по валидным записям.
    """
    indexed: dict[tuple, str] = {}
    for cell in cells:
        if verdict_key not in cell or any(part not in cell for part in key):
            continue
        indexed[tuple(cell[part] for part in key)] = cell[verdict_key]
    return indexed


def verdict_agreement(
    cells_a: list[dict],
    cells_b: list[dict],
    *,
    key: KeySpec = ("material_id", "property_name"),
    verdict_key: str = "absence_verdict",
) -> VerdictAgreement:
    """Compute inter-configuration verdict agreement between two absence maps (§25.15).

    Соединение выполняется только по общим ключам (inner join); ключи, присутствующие
    лишь в одной карте, игнорируются и не входят в ``n``. ``raw_agreement`` — доля
    совпавших verdict'ов; ``cohen_kappa`` корректирует её на случайное согласие ``pe``,
    вычисленное по маргинальным частотам verdict'ов каждой стороны. При ``1 - pe == 0``
    kappa считается ``1.0``; при пустом пересечении — ``0.0``.
    """
    index_a = _index(cells_a, key, verdict_key)
    index_b = _index(cells_b, key, verdict_key)
    shared = index_a.keys() & index_b.keys()

    n = len(shared)
    if n == 0:
        return VerdictAgreement(
            n=0,
            n_agree=0,
            raw_agreement=0.0,
            cohen_kappa=0.0,
            flip_matrix={},
        )

    n_agree = 0
    flip_matrix: dict[str, int] = {}
    marginal_a: Counter[str] = Counter()
    marginal_b: Counter[str] = Counter()
    for shared_key in shared:
        verdict_a = index_a[shared_key]
        verdict_b = index_b[shared_key]
        marginal_a[verdict_a] += 1
        marginal_b[verdict_b] += 1
        if verdict_a == verdict_b:
            n_agree += 1
        else:
            label = f"{verdict_a}->{verdict_b}"
            flip_matrix[label] = flip_matrix.get(label, 0) + 1

    po = n_agree / n
    verdicts = marginal_a.keys() | marginal_b.keys()
    pe = sum((marginal_a[v] / n) * (marginal_b[v] / n) for v in verdicts)
    cohen_kappa = 1.0 if (1.0 - pe) == 0 else (po - pe) / (1.0 - pe)

    return VerdictAgreement(
        n=n,
        n_agree=n_agree,
        raw_agreement=po,
        cohen_kappa=cohen_kappa,
        flip_matrix=flip_matrix,
    )
