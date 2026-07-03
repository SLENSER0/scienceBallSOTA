"""Robustness scoring under input perturbation (§23.17).

Оценивает устойчивость метрики к «грязному» входу: OCR-шум, проблемы кодировки,
смена языка. Для каждой пертурбации известны два счёта — ``clean`` (чистый вход)
и ``perturbed`` (искажённый вход) той же метрики (больше — лучше, диапазон
[0, 1]). Просадка компонента считается как ``abs_drop = clean - perturbed`` и
относительная ``rel_drop = abs_drop / clean`` (0.0 когда ``clean == 0``). Итоговая
устойчивость ``robustness = mean_perturbed / mean_clean`` (1.0 когда среднее
чистое равно 0), худшая пертурбация — с максимальной ``rel_drop`` (ничьи — по
имени), тест пройден, если каждая ``rel_drop`` не превышает порога.

Ни один существующий модуль не измеряет просадку «чистый против искажённого»
входа — здесь именно это изолируется и агрегируется в один отчёт.

Robustness of a higher-better metric in [0, 1] under input perturbation (OCR
noise, encoding, language). Per perturbation the clean and perturbed scores are
compared: ``abs_drop = clean - perturbed`` and ``rel_drop = abs_drop / clean``
(0.0 when ``clean == 0``). Overall ``robustness = mean_perturbed / mean_clean``
(1.0 when ``mean_clean == 0``); the worst perturbation has the largest
``rel_drop`` (ties by name); passed iff every ``rel_drop <= max_rel_drop``.

Pure-python: только stdlib. Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PerturbationDrop:
    """Просадка метрики на одной пертурбации (§23.17).

    ``abs_drop = clean - perturbed`` — абсолютная просадка (отрицательна при
    улучшении). ``rel_drop = abs_drop / clean`` — относительная просадка, равна
    0.0 при ``clean == 0`` (деление на ноль не выполняется).

    ``abs_drop = clean - perturbed`` (negative when perturbed improves).
    ``rel_drop = abs_drop / clean``, forced to 0.0 when ``clean == 0``.
    """

    name: str
    clean: float
    perturbed: float
    abs_drop: float
    rel_drop: float

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "name": self.name,
            "clean": self.clean,
            "perturbed": self.perturbed,
            "abs_drop": self.abs_drop,
            "rel_drop": self.rel_drop,
        }


@dataclass(frozen=True)
class RobustnessReport:
    """Сводный отчёт по устойчивости метрики к пертурбациям (§23.17).

    ``robustness = mean_perturbed / mean_clean`` (1.0 когда ``mean_clean == 0``);
    больше — лучше, значение > 1.0 означает улучшение под искажением. ``worst`` —
    имя пертурбации с максимальной ``rel_drop`` (ничьи по алфавиту). ``passed``
    истинно, если каждая ``rel_drop`` не превышает ``max_rel_drop``.

    ``robustness = mean_perturbed / mean_clean`` (1.0 when ``mean_clean == 0``);
    higher is better and > 1.0 means the metric improved. ``worst`` is the name
    with the largest ``rel_drop`` (alphabetical ties); ``passed`` iff every
    ``rel_drop <= max_rel_drop``.
    """

    n: int
    mean_clean: float
    mean_perturbed: float
    robustness: float
    worst: str
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        """Plain-``dict`` view (JSON-ready)."""
        return {
            "n": self.n,
            "mean_clean": self.mean_clean,
            "mean_perturbed": self.mean_perturbed,
            "robustness": self.robustness,
            "worst": self.worst,
            "passed": self.passed,
        }


def score_robustness(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_rel_drop: float = 0.2,
) -> RobustnessReport:
    """Построить :class:`RobustnessReport` из просадок по пертурбациям (§23.17).

    Каждая строка — ``Mapping`` с ключами ``name`` (str), ``clean`` (float),
    ``perturbed`` (float). Для строки ``abs_drop = clean - perturbed``,
    ``rel_drop = abs_drop / clean`` (0.0 при ``clean == 0``). Затем
    ``robustness = mean_perturbed / mean_clean`` (1.0 при ``mean_clean == 0``),
    ``worst`` — имя с максимальной ``rel_drop`` (ничьи по алфавиту), ``passed``
    истинно, если каждая ``rel_drop <= max_rel_drop``. Пустой вход — ``ValueError``.

    Each row maps ``name``/``clean``/``perturbed``. Per row ``abs_drop`` and
    ``rel_drop`` (0.0 when ``clean == 0``) are computed; the aggregate
    ``robustness`` is ``mean_perturbed / mean_clean`` (1.0 when ``mean_clean``
    is 0). ``worst`` is the largest-``rel_drop`` name (alphabetical ties) and
    ``passed`` iff all ``rel_drop <= max_rel_drop``. Empty input raises.
    """
    if not rows:
        raise ValueError("rows must be non-empty / вход не должен быть пустым")

    drops: list[PerturbationDrop] = []
    sum_clean = 0.0
    sum_perturbed = 0.0
    for row in rows:
        name = str(row["name"])
        clean = float(row["clean"])
        perturbed = float(row["perturbed"])
        abs_drop = clean - perturbed
        rel_drop = abs_drop / clean if clean != 0 else 0.0
        drops.append(
            PerturbationDrop(
                name=name,
                clean=clean,
                perturbed=perturbed,
                abs_drop=abs_drop,
                rel_drop=rel_drop,
            )
        )
        sum_clean += clean
        sum_perturbed += perturbed

    n = len(drops)
    mean_clean = sum_clean / n
    mean_perturbed = sum_perturbed / n
    robustness = mean_perturbed / mean_clean if mean_clean != 0 else 1.0
    # Худшая пертурбация — максимальная rel_drop; ничьи разрешаются по имени.
    # Worst perturbation is the largest rel_drop; ties broken alphabetically.
    worst = min(drops, key=lambda d: (-d.rel_drop, d.name)).name
    passed = all(d.rel_drop <= max_rel_drop for d in drops)

    return RobustnessReport(
        n=n,
        mean_clean=mean_clean,
        mean_perturbed=mean_perturbed,
        robustness=robustness,
        worst=worst,
        passed=passed,
    )
