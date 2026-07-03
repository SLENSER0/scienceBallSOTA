"""OCR/parse edit-distance metrics — расстояние редактирования (§23.34/§23.31).

Pure-stdlib text-similarity scoring of a parser/OCR *prediction* string against a
gold *reference*, mirroring the edit-distance family used by OmniDocBench and
olmOCR-Bench to grade document-parsing quality:

* **CER** (character error rate) — Levenshtein edits between the two strings
  divided by the gold length (``0.0`` = perfect, larger = worse);
* **WER** (word error rate) — the same ratio computed over whitespace tokens
  rather than characters;
* **similarity** — a normalized closeness score ``1 - edits / max(len)`` that
  lands in ``[0, 1]`` (``1.0`` = identical, and ``1.0`` for two empty strings).

Everything is deterministic and I/O-free. :func:`levenshtein` is the classic
two-row dynamic-programming edit distance (insert/delete/substitute cost 1);
:func:`score` bundles the character-level facets into an
:class:`EditDistanceReport`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditDistanceReport:
    """Character-level edit-distance verdict — отчёт о расстоянии (§23.34).

    ``char_edits`` is the raw Levenshtein distance between gold and prediction;
    ``cer`` normalizes it by the gold length; ``similarity`` normalizes it by the
    longer of the two lengths (so it stays in ``[0, 1]`` and reads ``1.0`` for two
    empty strings).
    """

    gold_len: int
    pred_len: int
    char_edits: int
    cer: float
    wer: float
    similarity: float

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view with stable keys (§23.34)."""
        return {
            "gold_len": self.gold_len,
            "pred_len": self.pred_len,
            "char_edits": self.char_edits,
            "cer": self.cer,
            "wer": self.wer,
            "similarity": self.similarity,
        }


def levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance between *a* and *b* — число правок (§23.34).

    Minimum number of single-character insertions, deletions, or substitutions
    (each cost 1) to turn *a* into *b*. Computed with a rolling two-row DP in
    ``O(len(a) * len(b))`` time and ``O(min(len))`` space.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # Keep the shorter string on the inner axis to minimise the row width.
    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def char_error_rate(gold: str, pred: str) -> float:
    """Character error rate of *pred* against *gold* — CER (§23.34).

    ``levenshtein(gold, pred) / len(gold)``. An empty *gold* yields ``0.0`` when
    *pred* is also empty, else ``1.0`` (every predicted character is spurious).
    """
    if not gold:
        return 0.0 if not pred else 1.0
    return levenshtein(gold, pred) / len(gold)


def word_error_rate(gold: str, pred: str) -> float:
    """Word error rate of *pred* against *gold* — WER (§23.34).

    Levenshtein distance over whitespace-split *tokens* (not characters), divided
    by the gold token count. Empty *gold* yields ``0.0`` when *pred* has no tokens
    either, else ``1.0``.
    """
    gold_tokens = gold.split()
    pred_tokens = pred.split()
    if not gold_tokens:
        return 0.0 if not pred_tokens else 1.0
    return _levenshtein_tokens(gold_tokens, pred_tokens) / len(gold_tokens)


def _levenshtein_tokens(a: list[str], b: list[str]) -> int:
    """Levenshtein distance over two token sequences — правки по токенам (§23.34).

    Identical DP to :func:`levenshtein` but comparing list elements (whole words)
    rather than individual characters.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ta in enumerate(a, start=1):
        current = [i]
        for j, tb in enumerate(b, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (0 if ta == tb else 1)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def score(gold: str, pred: str) -> EditDistanceReport:
    """Score *pred* against *gold* into an :class:`EditDistanceReport` (§23.34).

    Bundles ``char_edits`` (Levenshtein distance), ``cer``, ``wer`` and
    ``similarity = 1 - char_edits / max(len(gold), len(pred))``. Two empty strings
    score ``similarity == 1.0`` and ``cer == wer == 0.0``.
    """
    edits = levenshtein(gold, pred)
    longest = max(len(gold), len(pred))
    similarity = 1.0 if longest == 0 else 1.0 - edits / longest
    return EditDistanceReport(
        gold_len=len(gold),
        pred_len=len(pred),
        char_edits=edits,
        cer=char_error_rate(gold, pred),
        wer=word_error_rate(gold, pred),
        similarity=similarity,
    )
