"""Per-cell absence-verdict rationale for the §25.14 UI. / Обоснование отсутствия.

Section 25.14 renders, for each classified coverage cell, a short human-facing
explanation of *why* a fact is absent: a stable **headline** naming the verdict
plus a list of structured **factor** strings (mentions, recall context,
retraction state, extractor-miss threshold). This is deliberately narrow and
deterministic — distinct from:

* :mod:`absence_self_check` — batch, cross-cell warning collector;
* :mod:`gap_narrative` (§24.11) — the two-block "что неизвестно / что проверить
  пилотно" answer partition.

Here every cell folds independently into one :class:`AbsenceRationale`. No store,
no I/O — a pure function over a plain dict, safe to call repeatedly with an
identical result (determinism is a documented guarantee, exercised in tests).

Input cell dict / входная ячейка::

    {
        "verdict":            str,    # classification, e.g. "possible_miss"
        "p_extractor_missed": float,  # P(extractor missed the fact) in [0, 1]
        "has_mentions":       bool,   # any MENTIONS edges seen for the entity?
        "recall":             float,  # modality recall prior in [0, 1]
        "retracted_count":    int,    # supporting docs that were retracted
        "calibrated":         bool,   # is p_extractor_missed calibrated?
    }
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger

_log = get_logger("absence_rationale")

# Verdict -> stable headline (§25.14). Unknown verdicts fall back to _DEFAULT.
_HEADLINES: dict[str, str] = {
    "possible_miss": "Вероятен пропуск извлечения (possible extraction miss)",
    "genuine_gap": "Скорее всего реальный пробел (genuine gap)",
    "retracted": "Опора на отозванные источники (retracted evidence)",
    "covered": "Факт покрыт (covered)",
}
_DEFAULT_HEADLINE = "Статус отсутствия не классифицирован (unknown verdict)"


@dataclass(frozen=True)
class AbsenceRationale:
    """Rationale for one absence cell (§25.14). / Обоснование одной ячейки.

    ``headline`` is the stable, verdict-keyed one-liner; ``factors`` is the
    ordered list of supporting factor strings (MENTIONS presence, recall prior,
    retraction state, extractor-miss threshold). ``calibrated`` is copied through
    from the input so the UI can badge whether ``p_extractor_missed`` is trusted.
    """

    verdict: str
    headline: str
    factors: list[str]
    calibrated: bool

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "headline": self.headline,
            "factors": list(self.factors),
            "calibrated": self.calibrated,
        }


def build_rationale(cell: dict) -> AbsenceRationale:
    """Build a deterministic §25.14 rationale from a classified ``cell``. / Собрать.

    Аргументы / Arguments:
        cell: classified absence cell (see module docstring). Missing keys take
            neutral defaults: ``verdict`` -> ``""``, ``p_extractor_missed`` /
            ``recall`` -> ``0.0``, ``has_mentions`` -> ``False``,
            ``retracted_count`` -> ``0``, ``calibrated`` -> ``False``.

    Правила / Rules (factors are appended in this fixed order):
        1. ``has_mentions`` True adds a ``MENTIONS`` factor; False omits it.
        2. always: a recall-context factor carrying the recall value;
        3. always: an extractor-miss factor carrying ``p_extractor_missed``;
        4. ``retracted_count > 0`` adds a retraction factor naming the count.

    The headline is looked up by verdict; an unknown verdict yields a non-empty
    fallback headline and never raises. Calling twice on the same cell returns
    equal ``factors`` (deterministic — no sets, no dict ordering).
    """
    verdict = cell.get("verdict", "")
    p_missed = float(cell.get("p_extractor_missed", 0.0))
    has_mentions = bool(cell.get("has_mentions", False))
    recall = float(cell.get("recall", 0.0))
    retracted_count = int(cell.get("retracted_count", 0))
    calibrated = bool(cell.get("calibrated", False))

    headline = _HEADLINES.get(verdict, _DEFAULT_HEADLINE)

    factors: list[str] = []

    if has_mentions:
        factors.append("MENTIONS: сущность упоминается в тексте (mentions present)")

    factors.append(f"Полнота модальности (recall) = {recall:.2f}")

    calib = "калибр." if calibrated else "не калибр."
    factors.append(f"P(пропуск извлечения) = {p_missed:.2f} [{calib}]")

    if retracted_count > 0:
        factors.append(f"Отзыв (retraction): {retracted_count} отозванных источник(ов)")

    _log.debug("rationale verdict=%s factors=%d", verdict, len(factors))
    return AbsenceRationale(
        verdict=verdict,
        headline=headline,
        factors=factors,
        calibrated=calibrated,
    )
