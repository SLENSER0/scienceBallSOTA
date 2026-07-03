"""FaithJudge/HHEM-style эвристический scorer верности (§18/§13.16).

Открытый заменитель для faithfulness-судьи из **FaithJudge** (Vectara,
EMNLP 2025 Industry, arXiv:2505.04847 — ``github.com/vectara/FaithJudge``).
Оригинальный FaithJudge использует **закрытый** судья o3-mini; здесь он
заменён детерминированной open-weight-free эвристикой (§23.33): claim
считается подтверждённым, если его значимые токены (числа + содержательные
слова) покрыты каким-либо evidence-текстом. Никаких весов и сети — чистый
python, одинаковый вход даёт одинаковый выход.

An open, weight-free substitute for the faithfulness judge in **FaithJudge**
(Vectara, EMNLP 2025 Industry, arXiv:2505.04847,
``github.com/vectara/FaithJudge``). The original FaithJudge relies on a
**closed** o3-mini judge; this module swaps it for a deterministic,
open-weight-free heuristic (§23.33): a claim counts as supported when its
salient tokens (numbers + content words) are covered by some evidence text.
No weights, no network — pure python, same input yields same output.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Границы предложений: ``;!?``/newline или точка вне десятичной дроби.
# Sentence boundary: ``;!?``/newline, or a ``.`` that is not a decimal point
# (i.e. not flanked by digits on both sides, so ``42.5`` stays intact).
_SENT_RE = re.compile(r"[;!?\n]|(?<!\d)\.|\.(?!\d)")

# Числовой токен (целые и десятичные, знак опционален) / numeric token.
_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")

# Словесный токен: буквы/цифры/подчёркивание / word token.
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Стоп-слова RU/EN — не считаются содержательными / stopwords excluded.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "of",
        "and",
        "or",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "as",
        "by",
        "has",
        "have",
        "had",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "from",
        "into",
        "than",
        "then",
        "there",
        "which",
        "but",
        "not",
        "no",
        "и",
        "в",
        "во",
        "на",
        "с",
        "со",
        "для",
        "по",
        "из",
        "это",
        "эта",
        "этот",
        "как",
        "что",
        "не",
        "а",
        "но",
        "к",
        "у",
        "о",
        "об",
        "же",
    }
)


@dataclass(frozen=True)
class FaithScore:
    """Замороженный итог оценки верности (§18) — RU/EN.

    * ``supported`` — число подтверждённых claims / supported claim count.
    * ``unsupported`` — число неподтверждённых claims / unsupported count.
    * ``score`` — ``supported / total`` (``1.0`` при отсутствии claims).
    * ``unsupported_claims`` — тексты неподтверждённых claims по порядку.
    """

    supported: int
    unsupported: int
    score: float
    unsupported_claims: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the score as plain ints/float + a claim list (RU: словарь)."""
        return {
            "supported": int(self.supported),
            "unsupported": int(self.unsupported),
            "score": round(float(self.score), 6),
            "unsupported_claims": list(self.unsupported_claims),
        }


def split_claims(answer: str) -> list[str]:
    """Разбить ответ на claim-предложения по ``.;!?``/newline → непустые.

    Splits ``answer`` on sentence boundaries and returns trimmed, non-empty
    fragments in order.
    """
    return [part.strip() for part in _SENT_RE.split(answer) if part.strip()]


def salient_tokens(text: str) -> tuple[frozenset[float], frozenset[str]]:
    """Извлечь значимые токены: числа и содержательные слова (§18).

    Returns ``(numbers, words)`` where ``numbers`` are parsed floats and
    ``words`` are lowercased content words with stopwords removed.
    """
    numbers = frozenset(float(m.group()) for m in _NUMBER_RE.finditer(text))
    words = frozenset(
        w for m in _WORD_RE.finditer(text.lower()) if (w := m.group()) not in _STOPWORDS
    )
    return numbers, words


def _claim_supported(
    claim: str, evidence: Sequence[tuple[frozenset[float], frozenset[str]]]
) -> bool:
    """Claim подтверждён, если какой-то evidence покрывает все его токены.

    A claim is supported when some single evidence text covers *all* of its
    salient numbers and content words. A claim with no salient tokens is
    vacuously supported (RU: пустой по смыслу claim подтверждён вакуумно).
    """
    numbers, words = salient_tokens(claim)
    if not numbers and not words:
        return True
    return any(numbers <= ev_nums and words <= ev_words for ev_nums, ev_words in evidence)


def faithfulness_score(answer: str, evidence_texts: Sequence[str]) -> FaithScore:
    """Оценить верность ответа относительно evidence-текстов (§18/§13.16).

    Ответ разбивается на claim-предложения; claim подтверждён, если его
    значимые токены (числа + содержательные слова) покрыты каким-либо
    evidence-текстом. ``score = supported / total``; пустой ответ (нет claims)
    даёт ``1.0`` (вакуумно верен). Open-weight-free замена судьи FaithJudge
    (arXiv:2505.04847, §23.33).

    Splits ``answer`` into claim sentences and marks each supported when its
    salient tokens are covered by some ``evidence_texts`` entry. ``score`` is
    ``supported / total``; an empty answer yields ``1.0`` (vacuously faithful).
    """
    evidence = [salient_tokens(text) for text in evidence_texts]
    claims = split_claims(answer)

    supported = 0
    unsupported_claims: list[str] = []
    for claim in claims:
        if _claim_supported(claim, evidence):
            supported += 1
        else:
            unsupported_claims.append(claim)

    total = len(claims)
    unsupported = len(unsupported_claims)
    score = 1.0 if total == 0 else supported / total

    return FaithScore(
        supported=supported,
        unsupported=unsupported,
        score=score,
        unsupported_claims=tuple(unsupported_claims),
    )
