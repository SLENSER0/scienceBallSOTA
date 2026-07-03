"""Citation existence / phantom-citation check (§18.10).

Детерминированная проверка / deterministic guard that every cited
``evidence_id`` in an answer resolves to a *known* evidence set.  A cited id
that is not part of the known set is a **phantom citation** and constitutes a
hard fail — RU: фантомная ссылка = жёсткий провал.

This complements :mod:`kg_eval.graphrag_mode_c_eval`, which assumes labeled
claims: here we only need the flat set of cited ids and the universe of ids
that actually exist.

Definitions — RU/EN:

* ``phantom`` — cited ids not present in ``known_ids`` (sorted, deduped) /
  ссылки, отсутствующие в известном множестве.
* ``precision`` — ``|cited ∩ known| / |cited|`` (``1.0`` when nothing cited) /
  точность цитирования.
* ``missing_required`` — required ids that were never cited /
  обязательные ссылки, которые не были процитированы.
* ``ok`` — no phantom **and** no missing required / нет фантомов и пропусков.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CitationCheckResult:
    """Frozen result of a citation-existence check (§18.10)."""

    cited: tuple[str, ...]
    phantom: tuple[str, ...]
    missing_required: tuple[str, ...]
    ok: bool
    precision: float

    def as_dict(self) -> dict[str, object]:
        """Return a plain-dict view (RU: как словарь) with rounded precision."""
        return {
            "cited": list(self.cited),
            "phantom": list(self.phantom),
            "missing_required": list(self.missing_required),
            "ok": bool(self.ok),
            "precision": round(float(self.precision), 6),
        }


def check_citations(
    cited_ids: Iterable[str],
    known_ids: Iterable[str],
    required_ids: Iterable[str] = (),
) -> CitationCheckResult:
    """Check that every cited evidence id resolves to a known evidence set.

    ``cited`` возвращается / is returned sorted and deduped.  ``phantom`` holds
    the cited ids absent from ``known_ids``; ``missing_required`` holds required
    ids that were never cited.  ``precision`` is ``|cited ∩ known| / |cited|``
    and defaults to ``1.0`` when nothing was cited.  ``ok`` is ``True`` only when
    there is no phantom citation and no missing required id.
    """
    cited_set = {str(c) for c in cited_ids}
    known_set = {str(k) for k in known_ids}
    required_set = {str(r) for r in required_ids}

    cited = tuple(sorted(cited_set))
    phantom = tuple(sorted(cited_set - known_set))
    missing_required = tuple(sorted(required_set - cited_set))

    precision = len(cited_set & known_set) / len(cited_set) if cited_set else 1.0

    ok = not phantom and not missing_required

    return CitationCheckResult(
        cited=cited,
        phantom=phantom,
        missing_required=missing_required,
        ok=ok,
        precision=precision,
    )
