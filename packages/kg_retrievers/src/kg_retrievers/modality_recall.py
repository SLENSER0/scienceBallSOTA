"""Context-keyed extractor-recall lookup (§25.10).

Resolves an expected extraction recall (полнота извлечения) for the *context* in
which a fact was surfaced — the ``(source_type, kind, parser_version,
extractor_version)`` tuple — via a three-step fallback chain (§25.10):

1. **exact** — a calibrated per-context prior for the full composite key wins;
2. **modality** — else the static per-modality (по модальности) heuristic keyed on
   ``context['kind']``: a structured ``catalog_row`` is near-certain to be extracted
   (0.98), a ``table_row`` slightly less (0.90), while free-text ``prose`` depends on
   whether an LLM extractor ran (0.55 online) or only an offline pass did (0.15);
3. **default** — else a neutral fallback (0.5).

Only step 1 yields ``calibrated=True`` (it comes from a supplied telemetry table);
the heuristic modality/default steps are always ``calibrated=False`` so the absence
layer (§25.11) never mistakes a guess for measured coverage.
"""

from __future__ import annotations

from dataclasses import dataclass

# Static per-modality heuristic recall priors (online extractor available), §25.10.
MODALITY_PRIORS: dict[str, float] = {
    "catalog_row": 0.98,
    "table_row": 0.90,
    "prose": 0.55,
}

# Offline overrides: without an LLM extractor, prose recall collapses sharply.
_OFFLINE_PRIORS: dict[str, float] = {
    "prose": 0.15,
}

# Composite-key fields, in order, forming the exact-lookup key (§25.10).
_KEY_FIELDS: tuple[str, ...] = (
    "source_type",
    "kind",
    "parser_version",
    "extractor_version",
)


def _context_key(context: dict) -> str:
    """Build the composite exact-lookup key from a context dict (§25.10).

    Joins the ``(source_type, kind, parser_version, extractor_version)`` fields with
    ``|``; missing fields contribute an empty segment so keys stay positional.
    """
    return "|".join(str(context.get(field, "")) for field in _KEY_FIELDS)


@dataclass(frozen=True)
class ContextRecall:
    """One resolved context recall (§25.10).

    ``context_key`` — the key that matched (composite key for exact/default, the
    modality for a modality hit); ``recall`` — expected recall in ``[0, 1]``;
    ``source`` — how it resolved (``'exact'`` / ``'modality'`` / ``'default'``);
    ``calibrated`` — ``True`` only for an exact telemetry-backed prior.
    """

    context_key: str
    recall: float
    source: str
    calibrated: bool = False

    def as_dict(self) -> dict:
        return {
            "context_key": self.context_key,
            "recall": self.recall,
            "source": self.source,
            "calibrated": self.calibrated,
        }


def recall_for_context(
    context: dict,
    priors: dict[str, float] | None = None,
    *,
    offline: bool = False,
    default: float = 0.5,
) -> ContextRecall:
    """Resolve an extractor recall for ``context`` via the §25.10 fallback chain.

    Exact composite-key hit in ``priors`` → ``source='exact'`` (``calibrated=True``);
    else the per-modality heuristic for ``context['kind']`` (offline-aware for prose) →
    ``source='modality'``; else ``default`` → ``source='default'``. The heuristic and
    default branches are always ``calibrated=False``.
    """
    key = _context_key(context)
    if priors and key in priors:
        return ContextRecall(context_key=key, recall=priors[key], source="exact", calibrated=True)

    kind = context.get("kind")
    if offline and kind in _OFFLINE_PRIORS:
        return ContextRecall(context_key=kind, recall=_OFFLINE_PRIORS[kind], source="modality")
    if kind in MODALITY_PRIORS:
        return ContextRecall(context_key=kind, recall=MODALITY_PRIORS[kind], source="modality")

    return ContextRecall(context_key=key, recall=default, source="default")
