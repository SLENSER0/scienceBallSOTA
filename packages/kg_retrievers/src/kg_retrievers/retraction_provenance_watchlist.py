"""Retraction co-provenance watchlist — риск по общему провенансу (§25.12).

``retraction_impact.py`` only follows *same-cell* evidence collapse: it flags a
``(material, property)`` cell when its own observations are retracted. It says
nothing about an *active* observation that merely **shares provenance** with a
retracted one — same source document, same extraction run, or same author. That
is guilt-by-shared-provenance (риск по общему провенансу): the active fact is not
retracted, but it leans on the same suspect pipeline, so it deserves a second
look.

This module scores that co-provenance risk. For every active observation it finds
retracted observations that share at least one *non-empty* provenance-key value
and reports:

* **shared_keys** — which provenance keys matched (e.g. ``('doc_id',)``);
* **retracted_neighbors** — the retracted observation ids that share a key;
* **risk** — ``len(shared_keys) / len(keys)`` in ``[0, 1]``.

Only active observations with at least one shared key are listed. Pure Python and
read-only: it reads no store and writes nothing. Per §25.12 provenance keys such
as ``extraction_run_id`` live in the JSON ``props`` catch-all rather than a
queryable Kuzu column, so callers pass them flattened onto each dict's top level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_KEYS: tuple[str, ...] = ("doc_id", "extraction_run_id", "author")


@dataclass(frozen=True)
class WatchlistEntry:
    """One active observation at co-provenance risk (§25.12).

    ``shared_keys`` are the provenance keys whose non-empty value matches at least
    one retracted observation; ``retracted_neighbors`` are those retracted
    observation ids. ``risk`` is ``len(shared_keys) / len(keys)`` — the share of
    provenance dimensions that overlap a retraction (доля общего провенанса).
    """

    observation_id: str
    shared_keys: tuple[str, ...]
    retracted_neighbors: tuple[str, ...]
    risk: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "shared_keys": list(self.shared_keys),
            "retracted_neighbors": list(self.retracted_neighbors),
            "risk": self.risk,
        }


@dataclass(frozen=True)
class Watchlist:
    """Co-provenance watchlist over active observations (§25.12).

    ``entries`` is one :class:`WatchlistEntry` per flagged active observation,
    sorted by ``risk`` descending then ``observation_id`` ascending. ``n_flagged``
    is ``len(entries)`` — active observations that share provenance with at least
    one retraction (помечённые наблюдения).
    """

    entries: tuple[WatchlistEntry, ...]
    n_flagged: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.as_dict() for e in self.entries],
            "n_flagged": self.n_flagged,
        }


def build_watchlist(
    active: list[dict],
    retracted: list[dict],
    *,
    keys: tuple[str, ...] = DEFAULT_KEYS,
) -> Watchlist:
    """Flag active observations sharing provenance with retractions (§25.12).

    Each dict carries ``observation_id`` plus any provenance keys in ``keys``
    (e.g. ``doc_id``, ``extraction_run_id``, ``author``). For every active
    observation we scan ``retracted`` and, for each key, treat it as *shared* when
    both sides hold the **same non-empty** value. ``shared_keys`` collects the
    matched keys (in ``keys`` order); ``retracted_neighbors`` collects the
    retracted ids that share at least one key (sorted). ``risk`` is
    ``len(shared_keys) / len(keys)``.

    Only active observations with ``>= 1`` shared key are included; the rest are
    dropped and excluded from ``n_flagged``. Entries are sorted by ``risk``
    descending then ``observation_id`` ascending. An empty ``retracted`` list (or
    no overlap anywhere) yields ``entries == ()`` and ``n_flagged == 0``.
    """
    entries: list[WatchlistEntry] = []
    for obs in active:
        obs_id = str(obs["observation_id"])
        shared: list[str] = []
        neighbors: set[str] = set()
        for key in keys:
            value = obs.get(key)
            if value in (None, ""):
                continue
            key_hit = False
            for other in retracted:
                if other.get(key) == value:
                    key_hit = True
                    neighbors.add(str(other["observation_id"]))
            if key_hit:
                shared.append(key)
        if not shared:
            continue
        entries.append(
            WatchlistEntry(
                observation_id=obs_id,
                shared_keys=tuple(shared),
                retracted_neighbors=tuple(sorted(neighbors)),
                risk=len(shared) / len(keys),
            )
        )

    entries.sort(key=lambda e: (-e.risk, e.observation_id))
    return Watchlist(entries=tuple(entries), n_flagged=len(entries))
