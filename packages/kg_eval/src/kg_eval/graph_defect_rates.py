"""Raw graph-quality defect rates feeding kg_health_score (§23.24).

Pure-stdlib computation of a handful of *raw* KG defect rates — orphan nodes,
duplicate entities, missing measurement units, missing experiment baselines —
each in ``0..1``. Эти "сырые" метрики (ниже — лучше) затем скармливаются
:mod:`kg_eval.kg_health_score`, где инвертируются и взвешиваются в composite.

Здесь нет весов и порогов: только честный подсчёт долей дефектов над графом,
заданным списками узлов и рёбер (обычные ``Mapping``, не Kuzu-строки).

Определения (все доли делятся на ``n_nodes``, кроме unit/baseline — те делятся
на число узлов соответствующего label; при нулевом знаменателе доля ``0.0``):

* ``orphan_rate`` — доля узлов, чей ``id`` не встречается ни в ``src``, ни в
  ``dst`` ни одного ребра;
* ``duplicate_entity_rate`` — ``(n_nodes - число различных групп) / n_nodes``,
  где группа — нормализованная пара ``(label, name)`` (case/space-insensitive);
* ``missing_unit_rate`` — доля узлов ``label == 'Measurement'`` без непустого
  ``unit`` среди всех Measurement-узлов;
* ``missing_baseline_rate`` — доля узлов ``label == 'Experiment'`` без ключа
  ``baseline`` среди всех Experiment-узлов.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def _norm(value: object) -> str:
    """Normalize a token: lower-case + collapsed whitespace + strip (RU: нормализация).

    Делает сопоставление имён/лейблов нечувствительным к регистру и к числу
    пробелов, поэтому ``'Al Cu'`` и ``'al  cu'`` дают один и тот же ключ.
    """
    return " ".join(str(value).split()).lower()


@dataclass(frozen=True)
class DefectRates:
    """Raw KG defect rates in ``0..1`` (§23.24).

    ``n_nodes`` — число узлов графа; остальные поля — доли дефектов (ниже —
    лучше). При пустом графе ``n_nodes == 0`` и все доли ``0.0``.
    """

    n_nodes: int
    orphan_rate: float
    duplicate_entity_rate: float
    missing_unit_rate: float
    missing_baseline_rate: float

    def as_dict(self) -> dict[str, float | int]:
        """5 ключей: ``n_nodes`` (int) + четыре доли, округлённые до 4 знаков."""
        return {
            "n_nodes": self.n_nodes,
            "orphan_rate": round(self.orphan_rate, 4),
            "duplicate_entity_rate": round(self.duplicate_entity_rate, 4),
            "missing_unit_rate": round(self.missing_unit_rate, 4),
            "missing_baseline_rate": round(self.missing_baseline_rate, 4),
        }


def scan(
    nodes: Sequence[Mapping[str, object]],
    edges: Sequence[Mapping[str, object]],
) -> DefectRates:
    """Compute raw defect rates over ``nodes``/``edges`` (§23.24).

    ``nodes`` — последовательность отображений с ключом ``id`` (и опционально
    ``label``, ``name``, ``unit``, ``baseline``); ``edges`` — с ключами ``src``
    и ``dst``. Знаменатели, равные нулю, дают долю ``0.0`` (защита от деления).
    """
    n_nodes = len(nodes)
    if n_nodes == 0:
        return DefectRates(0, 0.0, 0.0, 0.0, 0.0)

    # --- orphan_rate: узлы, чей id не участвует ни в одном ребре -------------
    connected: set[object] = set()
    for edge in edges:
        if "src" in edge:
            connected.add(edge["src"])
        if "dst" in edge:
            connected.add(edge["dst"])
    orphans = sum(1 for node in nodes if node.get("id") not in connected)
    orphan_rate = orphans / n_nodes

    # --- duplicate_entity_rate: (n_nodes - distinct groups) / n_nodes -------
    groups: set[tuple[str, str]] = set()
    for node in nodes:
        groups.add((_norm(node.get("label", "")), _norm(node.get("name", ""))))
    duplicate_entity_rate = (n_nodes - len(groups)) / n_nodes

    # --- missing_unit_rate: только среди Measurement-узлов -------------------
    measurements = [n for n in nodes if _norm(n.get("label", "")) == "measurement"]
    missing_units = sum(1 for n in measurements if not str(n.get("unit", "")).strip())
    missing_unit_rate = missing_units / len(measurements) if measurements else 0.0

    # --- missing_baseline_rate: только среди Experiment-узлов ----------------
    experiments = [n for n in nodes if _norm(n.get("label", "")) == "experiment"]
    missing_baselines = sum(1 for n in experiments if not n.get("baseline"))
    missing_baseline_rate = missing_baselines / len(experiments) if experiments else 0.0

    return DefectRates(
        n_nodes=n_nodes,
        orphan_rate=orphan_rate,
        duplicate_entity_rate=duplicate_entity_rate,
        missing_unit_rate=missing_unit_rate,
        missing_baseline_rate=missing_baseline_rate,
    )
