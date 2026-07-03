"""Детерминированная разметка подтверждённости claims (§18.8/§18.10).

No-LLM детектор: разбивает ответ на claims и помечает каждый как
``supported`` только если он несёт разрешимый ``evidence_id`` И все упомянутые
им числа встречаются в тексте процитированного evidence. Итог питает
:func:`kg_eval.graphrag_mode_c_eval.evaluate_mode_c` (поля ``supported`` /
``cited_doc_ids``) и напрямую даёт ``unsupported_claim_rate``.

A no-LLM detector that splits an answer into claims and labels each
``supported`` only when it carries a resolvable ``evidence_id`` *and* every
number it mentions appears in the cited evidence text. The output feeds
:func:`evaluate_mode_c` and yields ``unsupported_claim_rate`` directly.

Pure-python: только stdlib + :func:`kg_eval.replay_divergence.extract_numbers`.
Детерминированно — одинаковый вход даёт одинаковый выход.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from kg_eval.replay_divergence import extract_numbers

# Инлайновый маркер цитаты вида ``[e1]`` / inline citation marker like ``[e1]``.
_CITE_RE = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")

# Границы предложений: точка, точка с запятой или перевод строки (§18.8).
_SENT_RE = re.compile(r"[.;\n]")


@dataclass(frozen=True)
class Claim:
    """Один claim с его цитатами, числами и вердиктом (§18.8) — RU/EN."""

    text: str
    cited_ids: tuple[str, ...]
    numbers: tuple[float, ...]
    supported: bool

    def as_dict(self) -> dict[str, object]:
        """Return the claim as a plain dict (RU: как словарь)."""
        return {
            "text": self.text,
            "cited_ids": list(self.cited_ids),
            "numbers": [float(n) for n in self.numbers],
            "supported": bool(self.supported),
        }


@dataclass(frozen=True)
class ClaimSupportResult:
    """Замороженный итог разметки claims (§18.10) — RU/EN."""

    claims: tuple[Claim, ...]
    unsupported_claim_rate: float
    citation_precision: float

    def as_dict(self) -> dict[str, object]:
        """Return the result as plain floats + claim dicts (RU: как словарь)."""
        return {
            "claims": [c.as_dict() for c in self.claims],
            "unsupported_claim_rate": round(float(self.unsupported_claim_rate), 6),
            "citation_precision": round(float(self.citation_precision), 6),
        }


def split_claims(answer: str) -> list[str]:
    """Разбить ответ на claims по ``.``/``;``/newline → непустые фрагменты.

    Splits ``answer`` on sentence boundaries (period, semicolon, newline) and
    returns the trimmed, non-empty fragments in order.
    """
    return [part.strip() for part in _SENT_RE.split(answer) if part.strip()]


def _strip_citations(text: str) -> str:
    """Убрать инлайновые маркеры цитат, чтобы их цифры не попали в числа."""
    return _CITE_RE.sub(" ", text)


def label_claims(answer: str, evidence: Mapping[str, str]) -> ClaimSupportResult:
    """Разметить claims против ``evidence`` и посчитать итоговые метрики (§18.10).

    Для каждого claim ``cited_ids`` парсятся из маркеров вида ``[e1]``. Claim
    ``supported`` только если хотя бы один cited id присутствует в ``evidence``
    И каждое извлечённое число (маркеры цитат при этом вырезаются) встречается в
    объединённом тексте существующих процитированных evidence.

    * ``unsupported_claim_rate`` = unsupported / total (``0.0`` без claims).
    * ``citation_precision`` = cited-existing / cited-total (``0.0`` без цитат).
    """
    claims: list[Claim] = []
    cited_total = 0
    cited_existing = 0

    for sentence in split_claims(answer):
        cited_ids = tuple(_CITE_RE.findall(sentence))
        numbers = extract_numbers(_strip_citations(sentence))

        existing = [cid for cid in cited_ids if cid in evidence]
        cited_total += len(cited_ids)
        cited_existing += len(existing)

        evidence_numbers = extract_numbers(" ".join(evidence[cid] for cid in existing))
        supported = bool(existing) and all(n in evidence_numbers for n in numbers)

        claims.append(
            Claim(text=sentence, cited_ids=cited_ids, numbers=numbers, supported=supported)
        )

    total = len(claims)
    unsupported = sum(1 for c in claims if not c.supported)
    unsupported_claim_rate = unsupported / total if total else 0.0
    citation_precision = cited_existing / cited_total if cited_total else 0.0

    return ClaimSupportResult(
        claims=tuple(claims),
        unsupported_claim_rate=unsupported_claim_rate,
        citation_precision=citation_precision,
    )
