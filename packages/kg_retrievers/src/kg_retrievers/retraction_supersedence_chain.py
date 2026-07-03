"""Retraction supersedence chains — retracted-and-replaced lineage (§25.12).

Pure-python reconstruction of *supersedence chains* over a list of observation dicts.
Each observation carries an ``id`` and, when it has been retracted-and-replaced, a
``superseded_by`` pointer to the *newer* observation that took its place. Following those
pointers oldest→newest yields a chain whose terminal node — the one nobody supersedes —
is the current *head*. The head is the chain's :dfn:`active head` unless the head itself
carries a truthy ``retracted`` flag, in which case the chain has no live representative
and ``active_head`` is ``None``.

Цепочки замещения ретракций: прослеживаем указатели ``superseded_by`` от старого к
новому, чтобы найти текущую «голову» каждой линии; голова активна, если сама не
ретрагирована. Циклы обрываются без зацикливания.

No existing retriever walks ``superseded_by`` links, so this module owns that traversal.
The functional graph (each node has at most one successor) is grouped by terminal head:
``n_chains`` is the number of distinct heads and ``n_orphans`` the number of singleton
chains. Cycle detection guarantees termination on malformed ``A→B→A`` loops. Results are
frozen dataclasses exposing ``as_dict()`` for JSON transport.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SupersedenceChain:
    """One retracted-and-replaced lineage (§25.12).

    - ``head`` — terminal id nobody supersedes (the current representative);
    - ``members`` — chain ids ordered oldest→newest, ending at ``head``;
    - ``length`` — number of members (``1`` ⇒ orphan/standalone);
    - ``active_head`` — ``head`` unless ``head`` is itself retracted, then ``None``.
    """

    head: str
    members: tuple[str, ...]
    length: int
    active_head: str | None

    def as_dict(self) -> dict:
        return {
            "head": self.head,
            "members": list(self.members),
            "length": self.length,
            "active_head": self.active_head,
        }


@dataclass(frozen=True)
class SupersedenceReport:
    """All supersedence chains over an observation set (§25.12).

    - ``chains`` — one :class:`SupersedenceChain` per distinct head;
    - ``n_chains`` — number of distinct heads (``== len(chains)``);
    - ``n_orphans`` — number of chains of length 1.
    """

    chains: tuple[SupersedenceChain, ...]
    n_chains: int
    n_orphans: int

    def as_dict(self) -> dict:
        return {
            "chains": [c.as_dict() for c in self.chains],
            "n_chains": self.n_chains,
            "n_orphans": self.n_orphans,
        }


def build_chains(
    observations: list[dict],
    *,
    id_key: str = "id",
    supersede_key: str = "superseded_by",
) -> SupersedenceReport:
    """Build supersedence chains from ``superseded_by`` pointers (§25.12).

    Each observation's ``supersede_key`` points at the *newer* observation that
    superseded it; following those pointers oldest→newest reaches a terminal *head* that
    nobody supersedes. Observations are grouped by their head — one chain per distinct
    head — with ``members`` ordered oldest-first. ``active_head`` is the head unless the
    head carries a truthy ``retracted`` property, in which case it is ``None``. Pointers
    to unknown ids and self/loop cycles are handled without infinite traversal.
    """
    by_id: dict[str, dict] = {}
    for obs in observations:
        oid = obs.get(id_key)
        if oid is None:
            continue
        by_id[str(oid)] = obs

    # Forward edge: node → the newer node that supersedes it (only valid, known ids).
    succ: dict[str, str] = {}
    for oid, obs in by_id.items():
        tgt = obs.get(supersede_key)
        if tgt and str(tgt) in by_id and str(tgt) != oid:
            succ[oid] = str(tgt)

    def head_of(start: str) -> str:
        """Terminal node reached from ``start``; stop on a cycle (§25.12)."""
        seen = {start}
        cur = start
        while True:
            nxt = succ.get(cur)
            if nxt is None or nxt in seen:
                return cur
            seen.add(nxt)
            cur = nxt

    def depth_to_head(start: str, head: str) -> int:
        """Number of forward steps from ``start`` to its ``head`` (cycle-safe)."""
        seen: set[str] = set()
        cur = start
        steps = 0
        while cur != head and cur not in seen:
            seen.add(cur)
            nxt = succ.get(cur)
            if nxt is None:
                break
            cur = nxt
            steps += 1
        return steps

    # Group every observation under its terminal head → one chain per distinct head.
    groups: dict[str, list[str]] = {}
    for oid in by_id:
        groups.setdefault(head_of(oid), []).append(oid)

    chains: list[SupersedenceChain] = []
    for head in sorted(groups):
        members = groups[head]
        # Oldest-first: deepest (farthest from head) first, id-tiebreak for determinism.
        ordered = tuple(sorted(members, key=lambda m: (-depth_to_head(m, head), m)))
        retracted = bool(by_id[head].get("retracted"))
        chains.append(
            SupersedenceChain(
                head=head,
                members=ordered,
                length=len(ordered),
                active_head=None if retracted else head,
            )
        )

    n_orphans = sum(1 for c in chains if c.length == 1)
    return SupersedenceReport(
        chains=tuple(chains),
        n_chains=len(chains),
        n_orphans=n_orphans,
    )
