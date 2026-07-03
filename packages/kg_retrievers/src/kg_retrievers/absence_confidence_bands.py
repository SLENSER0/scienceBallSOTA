"""Absence-confidence bands / abstain zone for reported knowledge gaps (§25.11).

Каждая пустая ячейка покрытия несёт ``confidence_of_absence`` — либо число в
``[0, 1]`` («насколько реально отсутствие данных»), либо строку ``"unknown"``,
когда recall извлекателя слишком мал, чтобы делать вывод (см. §25.3–25.5).

Для UI и триажа непрерывную шкалу удобно свернуть в три полосы уверенности плюс
служебную полосу ``UNKNOWN``:

- ``HIGH`` — ``conf >= high_at``: мы уверены, что пробел реален;
- ``MID``  — ``low_at <= conf < high_at``: зона воздержания (abstain zone), где
  ни подтвердить, ни отвергнуть отсутствие нельзя — сюда стоит направить ревью;
- ``LOW``  — ``conf < low_at``: отсутствие, скорее всего, артефакт извлечения;
- ``UNKNOWN`` — нечисловая уверенность (например, строка ``"unknown"``).

``bucket_bands`` раскладывает ячейки по полосам, считает долю (share) каждой
полосы и выставляет ``n_abstain_zone`` равным размеру полосы ``MID``.

Each empty coverage cell carries ``confidence_of_absence`` — a float in ``[0, 1]``
or the string ``"unknown"``. This module folds that scale into three confidence
bands plus an ``UNKNOWN`` band, exposes the ``MID`` band as the *abstain zone*,
and reports per-band shares that sum to 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = "0.1.0"

# Band labels ---------------------------------------------------------------
HIGH = "HIGH"
MID = "MID"
LOW = "LOW"
UNKNOWN = "UNKNOWN"

# Order in which bands are materialised / rendered.
BAND_ORDER: tuple[str, ...] = (HIGH, MID, LOW, UNKNOWN)

# Default thresholds (mirror confidence_of_absence gating; MID is the abstain zone).
DEFAULT_HIGH_AT = 0.6
DEFAULT_LOW_AT = 0.25
DEFAULT_MAX_EXAMPLES = 5


@dataclass(frozen=True)
class Band:
    """One confidence band with its members' share and a few examples.

    ``examples`` are ``(subject, detail)`` pairs, truncated to ``max_examples``.
    """

    name: str
    count: int
    share: float
    examples: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "count": self.count,
            "share": self.share,
            "examples": [list(pair) for pair in self.examples],
        }


@dataclass(frozen=True)
class ConfidenceBands:
    """All bands for a set of cells, with totals and the abstain-zone size."""

    bands: list[Band]
    n_total: int
    n_abstain_zone: int

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "bands": [b.as_dict() for b in self.bands],
            "n_total": self.n_total,
            "n_abstain_zone": self.n_abstain_zone,
        }


def band_for(conf: object, *, high_at: float, low_at: float) -> str:
    """Classify a single ``confidence_of_absence`` value into a band label.

    Возвращает ``'HIGH'`` при числовом ``conf >= high_at``, ``'LOW'`` при
    ``conf < low_at``, ``'MID'`` иначе, и ``'UNKNOWN'`` для нечисловой уверенности
    (строки вроде ``"unknown"`` или ``None``). Булевы значения нечисловые тут.
    """
    # bool is a subclass of int/float — treat it as non-numeric (UNKNOWN).
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return UNKNOWN
    value = float(conf)
    if value >= high_at:
        return HIGH
    if value < low_at:
        return LOW
    return MID


def bucket_bands(
    cells: list[dict],
    *,
    high_at: float = DEFAULT_HIGH_AT,
    low_at: float = DEFAULT_LOW_AT,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> ConfidenceBands:
    """Bucket coverage ``cells`` by ``confidence_of_absence`` into confidence bands.

    Каждая ячейка — ``dict`` с ключом ``confidence_of_absence``; для примеров
    используются ``material_name``/``material_id`` и ``property_name``. Доли (share)
    считаются от ``n_total`` и в сумме дают 1.0 при ``n_total > 0``; ``n_abstain_zone``
    равен размеру полосы ``MID``. Пустой вход → ``n_total == 0`` без деления на ноль.
    """
    counts: dict[str, int] = dict.fromkeys(BAND_ORDER, 0)
    examples: dict[str, list[tuple[str, str]]] = {name: [] for name in BAND_ORDER}

    for cell in cells:
        conf = cell.get("confidence_of_absence")
        label = band_for(conf, high_at=high_at, low_at=low_at)
        counts[label] += 1
        if len(examples[label]) < max_examples:
            examples[label].append(_example_of(cell))

    n_total = len(cells)
    bands = [
        Band(
            name=name,
            count=counts[name],
            share=(counts[name] / n_total) if n_total else 0.0,
            examples=examples[name],
        )
        for name in BAND_ORDER
    ]
    return ConfidenceBands(bands=bands, n_total=n_total, n_abstain_zone=counts[MID])


def _example_of(cell: dict) -> tuple[str, str]:
    """Build a ``(subject, detail)`` example pair from a coverage cell."""
    subject = cell.get("material_name") or cell.get("material_id") or ""
    detail = cell.get("property_name") or ""
    return (str(subject), str(detail))
