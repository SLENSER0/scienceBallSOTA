"""Answer blocks 'что неизвестно' and 'что проверить пилотно' (§24.11).

Section 24.11 requires that an answer partition its coverage cells into two
narrative blocks presented to the reader:

* **Что неизвестно / не найдено** ("what is unknown / not found") — cells with
  no supporting experiments (``evidence_count == 0``);
* **Что проверить пилотно** ("what to pilot-check") — cells that *are* covered
  but only weakly: low confidence (``confidence < pilot_conf``) or a strong
  local dependence (``local_dependence is True``) that must be validated on the
  reader's own conditions before trusting the result.

A cell that is well covered *and* high-confidence *and* not locally dependent
belongs to neither block — nothing needs flagging. This module provides the
frozen :class:`GapBlocks` container and the pure function
:func:`build_gap_blocks`. No store, no I/O — it folds plain dicts.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger

_log = get_logger("gap_narrative")


@dataclass(frozen=True)
class GapBlocks:
    """The two answer blocks required by §24.11. / Два блока ответа.

    ``unknown`` holds labels with no experiments (что неизвестно/не найдено);
    ``pilot_check`` holds labels that are covered but weak — low confidence or
    strongly locally dependent (что проверить пилотно). Labels within each block
    are deduplicated and sorted. The two blocks are disjoint: a cell with
    ``evidence_count == 0`` is *only* unknown, never pilot-check.
    """

    unknown: tuple[str, ...]
    pilot_check: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "unknown": list(self.unknown),
            "pilot_check": list(self.pilot_check),
        }


def build_gap_blocks(cells: list[dict], *, pilot_conf: float = 0.5) -> GapBlocks:
    """Partition coverage ``cells`` into the two §24.11 answer blocks. / Разбить ячейки.

    Аргументы / Arguments:
        cells: coverage cells, each ``{label, evidence_count, confidence,
            local_dependence}``. ``local_dependence`` defaults to ``False``.
        pilot_conf: confidence threshold; a covered cell is pilot-check iff its
            confidence is strictly below this bound (or it is locally dependent).

    Правила / Rules (per cell):
        * ``evidence_count == 0`` → **unknown** (and never pilot-check);
        * else ``confidence < pilot_conf`` or ``local_dependence`` → **pilot_check**;
        * otherwise → neither block.

    Labels are deduplicated and sorted within each block.
    """
    unknown: set[str] = set()
    pilot_check: set[str] = set()

    for cell in cells:
        label = cell["label"]
        evidence_count = cell.get("evidence_count", 0)

        if evidence_count == 0:
            unknown.add(label)
            continue

        confidence = cell.get("confidence", 0.0)
        local_dependence = cell.get("local_dependence", False)

        if confidence < pilot_conf or local_dependence:
            pilot_check.add(label)

    return GapBlocks(
        unknown=tuple(sorted(unknown)),
        pilot_check=tuple(sorted(pilot_check)),
    )
