"""Единая фабрика тестовых данных: детерминированный генератор большого графа (§23.3).

Deterministic, parametrized synthetic-graph generator for perf/load fixtures
(§23.9). Stdlib-only: no ``datetime.now`` and no unseeded ``random`` — every run
with the same ``seed`` produces byte-identical output.

Модель / Model
--------------
* ``Material`` --HAS_EXPERIMENT--> ``Experiment``
* ``Experiment`` --MEASURED--> ``Measurement``
* ``Measurement`` --SUPPORTED_BY--> ``Evidence``  (evidence-first invariant:
  каждое измерение имеет ровно один узел ``Evidence`` / every Measurement has
  exactly one Evidence node).

Node dicts follow the ``{"id", "label", **props}`` shape used elsewhere in
``kg_common.testing`` so they can feed ``KuzuGraphStore.upsert_node`` directly.
Помните / Note: в Kuzu пользовательские свойства не являются столбцами запроса —
их читают через ``get_node``; здесь мы возвращаем полные dict'ы для фикстур.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

__all__ = ["SyntheticGraph", "generate_graph", "node_counts"]

# Метки узлов в порядке генерации / node labels in generation order.
_NODE_LABELS: tuple[str, ...] = ("Material", "Experiment", "Measurement", "Evidence")


@dataclass(frozen=True)
class SyntheticGraph:
    """Неизменяемый результат генерации / immutable generated graph (§23.3).

    Attributes
    ----------
    nodes:
        Кортеж узлов ``{"id", "label", **props}`` / tuple of node dicts.
    edges:
        Кортеж рёбер ``{"id", "source", "target", "label"}`` / tuple of edges.
    counts:
        Число узлов по метке / node count per label; sums to ``len(nodes)``.
    """

    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        """Сериализуемое представление / plain-dict, stable for a given seed."""
        return {
            "nodes": [dict(n) for n in self.nodes],
            "edges": [dict(e) for e in self.edges],
            "counts": dict(self.counts),
        }


def _material_id(i: int) -> str:
    return f"mat:{i:06d}"


def _experiment_id(i: int, j: int) -> str:
    return f"exp:{i:06d}:{j:02d}"


def _measurement_id(i: int, j: int, k: int) -> str:
    return f"meas:{i:06d}:{j:02d}:{k:02d}"


def _evidence_id(i: int, j: int, k: int) -> str:
    return f"ev:{i:06d}:{j:02d}:{k:02d}"


def generate_graph(
    *,
    materials: int,
    experiments_per_material: int = 2,
    measurements_per_experiment: int = 1,
    seed: int = 0,
) -> SyntheticGraph:
    """Построить детерминированный граф / build a deterministic synthetic graph.

    Parameters
    ----------
    materials:
        Число материалов (>= 0) / number of ``Material`` nodes.
    experiments_per_material:
        Экспериментов на материал / experiments per material.
    measurements_per_experiment:
        Измерений на эксперимент / measurements per experiment.
    seed:
        Зерно ГПСЧ для значений атрибутов / RNG seed for attribute values; ids
        не зависят от seed / ids do not depend on seed.

    Returns
    -------
    SyntheticGraph
        Узлы/рёбра/счётчики; ``counts`` суммируется до ``len(nodes)`` and every
        Measurement has exactly one supporting Evidence node.
    """
    if materials < 0:
        raise ValueError("materials must be >= 0")
    if experiments_per_material < 0 or measurements_per_experiment < 0:
        raise ValueError("per-parent counts must be >= 0")

    # Детерминированный ГПСЧ для значений атрибутов / seeded RNG, not crypto.
    rng = random.Random(seed)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    counts: dict[str, int] = dict.fromkeys(_NODE_LABELS, 0)

    for i in range(materials):
        mat_id = _material_id(i)
        nodes.append(
            {
                "id": mat_id,
                "label": "Material",
                "name": f"Material {i:06d}",
                "material_class": rng.choice(("alloy", "ceramic", "polymer")),
                "review_status": "unreviewed",
            }
        )
        counts["Material"] += 1

        for j in range(experiments_per_material):
            exp_id = _experiment_id(i, j)
            nodes.append(
                {
                    "id": exp_id,
                    "label": "Experiment",
                    "name": f"experiment {i:06d}-{j:02d}",
                    "temperature_c": round(rng.uniform(20.0, 900.0), 3),
                    "review_status": "unreviewed",
                }
            )
            counts["Experiment"] += 1
            edges.append(
                {
                    "id": f"{mat_id}->{exp_id}:HAS_EXPERIMENT",
                    "source": mat_id,
                    "target": exp_id,
                    "label": "HAS_EXPERIMENT",
                }
            )

            for k in range(measurements_per_experiment):
                meas_id = _measurement_id(i, j, k)
                nodes.append(
                    {
                        "id": meas_id,
                        "label": "Measurement",
                        "name": f"measurement {i:06d}-{j:02d}-{k:02d}",
                        "property_name": "hardness",
                        "value_normalized": round(rng.uniform(50.0, 250.0), 3),
                        "normalized_unit": "HV",
                        "review_status": "unreviewed",
                    }
                )
                counts["Measurement"] += 1
                edges.append(
                    {
                        "id": f"{exp_id}->{meas_id}:MEASURED",
                        "source": exp_id,
                        "target": meas_id,
                        "label": "MEASURED",
                    }
                )

                # Evidence-first: ровно один узел Evidence на измерение.
                ev_id = _evidence_id(i, j, k)
                nodes.append(
                    {
                        "id": ev_id,
                        "label": "Evidence",
                        "doc_id": f"paper:{i:06d}",
                        "text": f"evidence for measurement {i:06d}-{j:02d}-{k:02d}",
                        "confidence": round(rng.uniform(0.5, 1.0), 3),
                        "evidence_strength": "peer_reviewed",
                        "review_status": "unreviewed",
                    }
                )
                counts["Evidence"] += 1
                edges.append(
                    {
                        "id": f"{meas_id}->{ev_id}:SUPPORTED_BY",
                        "source": meas_id,
                        "target": ev_id,
                        "label": "SUPPORTED_BY",
                    }
                )

    return SyntheticGraph(nodes=tuple(nodes), edges=tuple(edges), counts=counts)


def node_counts(g: SyntheticGraph) -> dict[str, int]:
    """Пересчитать узлы по метке из ``g.nodes`` / recount nodes per label.

    Всегда включает все известные метки (нули для отсутствующих) so the result
    is comparable with ``g.counts`` even for an empty graph.
    """
    result: dict[str, int] = dict.fromkeys(_NODE_LABELS, 0)
    for node in g.nodes:
        label = node["label"]
        result[label] = result.get(label, 0) + 1
    return result
