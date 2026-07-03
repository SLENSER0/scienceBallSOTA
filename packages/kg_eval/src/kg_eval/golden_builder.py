"""Golden-dataset builder + IO (§18.3 / §18.6).

Строит небольшой детерминированный «золотой» набор вопросов-ответов для
демо-домена (обогатительная фабрика: обессоливание воды методом обратного
осмоса и смежные потоки). Каждый :class:`GoldenQA` ссылается на канонические
seed-идентификаторы (строки), поэтому граф/хранилище здесь не нужны — только
``json`` для сериализации.

Builds a small deterministic golden question/answer set for the demo domain
(concentrator plant: reverse-osmosis water desalination and related flows).
Each :class:`GoldenQA` references canonical seed ids as plain strings, so no
store is required — only ``json`` for round-tripping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GoldenQA:
    """Один золотой вопрос-ответ / one golden QA row.

    ``id``                      — уникальный идентификатор кейса.
    ``question``                — вопрос на русском языке (RU).
    ``expected_entities``       — канонические seed-id ожидаемых сущностей.
    ``expected_answer_contains``— подстроки, которые должен содержать ответ.
    ``expected_gap``            — ожидается ли пробел в знаниях (True/False).
    """

    id: str
    question: str
    expected_entities: tuple[str, ...] = ()
    expected_answer_contains: tuple[str, ...] = ()
    expected_gap: bool = False

    def as_dict(self) -> dict[str, object]:
        """Serialise to a plain JSON-friendly dict (lists, not tuples)."""
        return {
            "id": self.id,
            "question": self.question,
            "expected_entities": list(self.expected_entities),
            "expected_answer_contains": list(self.expected_answer_contains),
            "expected_gap": self.expected_gap,
        }

    @classmethod
    def from_dict(cls, row: dict[str, object]) -> GoldenQA:
        """Rebuild a :class:`GoldenQA` from :meth:`as_dict` output."""
        return cls(
            id=str(row["id"]),
            question=str(row["question"]),
            expected_entities=tuple(row.get("expected_entities") or ()),  # type: ignore[arg-type]
            expected_answer_contains=tuple(row.get("expected_answer_contains") or ()),  # type: ignore[arg-type]
            expected_gap=bool(row.get("expected_gap", False)),
        )


# --- Deterministic seed golden set ------------------------------------------
# Канонические seed-id совпадают со строковыми ключами демо-домена; ответы
# держим короткими и проверяемыми вручную. Порядок фиксирован → детерминизм.
_SEED: tuple[GoldenQA, ...] = (
    GoldenQA(
        id="q_ro_desalination",
        question=(
            "Какие методы обессоливания воды подходят для обогатительной фабрики, "
            "если исходная вода содержит сульфаты и хлориды, а требуемый сухой "
            "остаток — ≤1000 мг/дм³?"
        ),
        expected_entities=(
            "water_desalination",
            "reverse_osmosis",
            "sulfates",
            "chlorides",
        ),
        expected_answer_contains=("осмос", "мембран"),
        expected_gap=False,
    ),
    GoldenQA(
        id="q_ro_tds_target",
        question=(
            "Какой сухой остаток (TDS) достижим обратным осмосом при исходной "
            "минерализации 200–300 мг/л по каждому иону?"
        ),
        expected_entities=("reverse_osmosis", "tds", "water_desalination"),
        expected_answer_contains=("1000", "мг"),
        expected_gap=False,
    ),
    GoldenQA(
        id="q_so2_removal",
        question=(
            "Какие методы удаления SO2 из отходящих газов применяются и какова их эффективность?"
        ),
        expected_entities=("so2_removal", "so2"),
        expected_answer_contains=("SO2",),
        expected_gap=False,
    ),
    GoldenQA(
        id="q_cold_heap_leaching_gap",
        question=(
            "Есть ли эксперименты для комбинации холодный климат + кучное "
            "выщелачивание + никелевая руда?"
        ),
        expected_entities=("heap_leaching", "nickel"),
        expected_answer_contains=("нет данных",),
        expected_gap=True,
    ),
)


def build_golden_from_seed() -> list[GoldenQA]:
    """Return the deterministic demo golden set (same call → same set)."""
    return list(_SEED)


def save_golden(items: list[GoldenQA], path: str | Path) -> Path:
    """Write ``items`` as a JSON array to ``path``; return the written path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [qa.as_dict() for qa in items]
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_golden(path: str | Path) -> list[GoldenQA]:
    """Read a golden JSON array written by :func:`save_golden`."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GoldenQA.from_dict(row) for row in raw]


__all__ = [
    "GoldenQA",
    "build_golden_from_seed",
    "save_golden",
    "load_golden",
]
