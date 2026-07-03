"""§13.23 воспроизводимый прогон / repeatable execution (§7.1) — run fingerprint.

§7.1 acceptance requires that two runs of the *same* question with the *same* seed
produce identical ``intent`` / ``query_plan`` / ``cypher_queries``. This module turns
that requirement into a machine-checkable artefact: a stable content hash (отпечаток
прогона / run fingerprint) computed over *exactly* those decision fields, so
reproducibility can be asserted by comparing two digests instead of eyeballing state.

Determinism rules:

* Canonical JSON is produced by :mod:`orjson` with sorted keys, so dict ordering never
  perturbs a hash (порядок ключей не влияет / key order is irrelevant).
* ``cypher_hash`` is taken over the **sorted** query list, so re-emitting the same
  Cypher in a different order yields the same hash (перестановка запросов не меняет hash).
* ``digest`` folds the canonical question/intent/plan parts together with the sorted
  cypher hash, the prompt version and the seed — the full identity of a run.

Nothing here touches a graph store or an LLM, so the whole module is unit-testable in
isolation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import orjson

# Ключи состояния, задающие идентичность прогона / state keys defining run identity.
_QUESTION_KEY = "normalized_question"
_INTENT_KEY = "intent"
_PLAN_KEY = "query_plan"
_CYPHER_KEY = "cypher_queries"


def _canonical(value: Any) -> bytes:
    """Канонический JSON (sorted keys) / canonical JSON bytes with sorted keys."""
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def _sha256_hex(payload: bytes) -> str:
    """sha256 → 64 строчных hex-символов / 64 lowercase hex chars."""
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RunFingerprint:
    """Отпечаток одного прогона / fingerprint of a single agent run (§13.23)."""

    intent: str
    prompt_version: str
    seed: int
    plan_hash: str
    cypher_hash: str
    digest: str

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict со всеми шестью полями / flat dict of all six fields."""
        return {
            "intent": self.intent,
            "prompt_version": self.prompt_version,
            "seed": self.seed,
            "plan_hash": self.plan_hash,
            "cypher_hash": self.cypher_hash,
            "digest": self.digest,
        }


def compute_fingerprint(state: dict, prompt_version: str, seed: int) -> RunFingerprint:
    """Построить отпечаток по состоянию агента / build a fingerprint from agent state.

    ``state`` is read for ``normalized_question``, ``intent``, ``query_plan`` and
    ``cypher_queries`` (missing keys default to empty). ``plan_hash`` hashes the
    canonical plan; ``cypher_hash`` hashes the *sorted* Cypher list; ``digest`` binds
    the canonical question/intent/plan parts to the cypher hash, ``prompt_version``
    and ``seed``.
    """
    question = state.get(_QUESTION_KEY, "")
    intent = str(state.get(_INTENT_KEY, ""))
    query_plan = state.get(_PLAN_KEY, {})
    cypher_queries = list(state.get(_CYPHER_KEY, []))

    question_part = _canonical(question)
    intent_part = _canonical(intent)
    plan_part = _canonical(query_plan)
    cypher_part = _canonical(sorted(cypher_queries))

    plan_hash = _sha256_hex(plan_part)
    cypher_hash = _sha256_hex(cypher_part)

    digest = _sha256_hex(
        b"\x00".join(
            [
                question_part,
                intent_part,
                plan_part,
                cypher_hash.encode("ascii"),
                prompt_version.encode("utf-8"),
                str(int(seed)).encode("ascii"),
            ]
        )
    )
    return RunFingerprint(
        intent=intent,
        prompt_version=prompt_version,
        seed=int(seed),
        plan_hash=plan_hash,
        cypher_hash=cypher_hash,
        digest=digest,
    )


def same_run(a: RunFingerprint, b: RunFingerprint) -> bool:
    """Равны ли прогоны по digest / do two fingerprints identify the same run."""
    return a.digest == b.digest
