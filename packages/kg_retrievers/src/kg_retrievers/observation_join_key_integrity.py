"""§25.3 — provenance-lineage integrity over Observation join keys.

The §25.3 acceptance criterion is blunt: every ``Observation`` must carry the
join keys that tie it back to *how* it came to exist — the ``extraction_run_id``
that produced it, the ``extractor`` that read it, and the ``extractor_version``
that pins the reader's behaviour. Without all three, an observation is an orphan
измерение (measurement) with no lineage: you cannot re-run the extractor that
made it, cannot diff two runs, and cannot retract a whole run's output.

This module is a read-only linter over already-materialised observation dicts.
It is deliberately **distinct** from :mod:`kg_common.provenance_completeness`,
which scores evidence-pack manifest slots (the retrieval-time bundle handed to
the LLM); here we audit the *storage-time* lineage keys on each Observation
node. The Kuzu note holds: those keys are custom node props, not RETURN columns,
so upstream read them via ``get_node`` and folded them into the plain dict this
audit consumes — never a projected column.

:func:`check_join_keys` walks the batch and emits a frozen
:class:`IntegrityReport`: how many observations were seen, how many carried
every required key (non-empty), the ``completeness`` ratio, a per-key tally of
what was missing, and the sorted ids of the offending (incomplete) observations.

Экземпляр Observation считается полным тогда и только тогда, когда каждый
обязательный ключ присутствует и непуст.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_common import get_logger

_log = get_logger("observation_join_key_integrity")

# The §25.3 lineage keys every Observation must carry to be re-runnable.
REQUIRED_JOIN_KEYS: tuple[str, ...] = (
    "extraction_run_id",
    "extractor",
    "extractor_version",
)


@dataclass(frozen=True)
class IntegrityReport:
    """Result of a §25.3 join-key integrity audit over a batch of Observations.

    ``n`` — сколько наблюдений проверено (observations seen); ``n_complete`` —
    how many carried every required key non-empty; ``completeness`` —
    ``n_complete / n`` (vacuously ``1.0`` when ``n == 0``); ``missing_by_key`` —
    per-key count of observations missing/empty that key; ``offenders`` — the
    sorted ids of incomplete observations.
    """

    n: int
    n_complete: int
    completeness: float
    missing_by_key: dict[str, int]
    offenders: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "n_complete": self.n_complete,
            "completeness": self.completeness,
            "missing_by_key": dict(self.missing_by_key),
            "offenders": list(self.offenders),
        }


def _is_present(value: Any) -> bool:
    """True iff ``value`` is a non-empty join-key value.

    ``None`` and the empty string (after stripping) count as missing — a blank
    ``extractor`` is no lineage at all. Non-string values are accepted as-is.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def check_join_keys(
    observations: list[dict],
    *,
    required: tuple[str, ...] = REQUIRED_JOIN_KEYS,
    id_key: str = "id",
) -> IntegrityReport:
    """Audit §25.3 lineage keys over ``observations``.

    An observation is *complete* iff every key in ``required`` is present and
    non-empty (see :func:`_is_present`). ``missing_by_key`` tallies, per required
    key, how many observations lack it; ``offenders`` is the sorted list of the
    ids (read from ``id_key``) of incomplete observations. ``completeness`` is
    ``n_complete / n``, or ``1.0`` vacuously when the batch is empty.
    """
    n = len(observations)
    missing_by_key: dict[str, int] = dict.fromkeys(required, 0)
    offenders: list[str] = []
    n_complete = 0

    for obs in observations:
        obs_complete = True
        for key in required:
            if not _is_present(obs.get(key)):
                missing_by_key[key] += 1
                obs_complete = False
        if obs_complete:
            n_complete += 1
        else:
            offenders.append(str(obs.get(id_key)))

    completeness = 1.0 if n == 0 else n_complete / n
    offenders_sorted = tuple(sorted(offenders))

    _log.debug(
        "join-key integrity: n=%d complete=%d completeness=%.3f offenders=%d",
        n,
        n_complete,
        completeness,
        len(offenders_sorted),
    )
    return IntegrityReport(
        n=n,
        n_complete=n_complete,
        completeness=completeness,
        missing_by_key=missing_by_key,
        offenders=offenders_sorted,
    )
