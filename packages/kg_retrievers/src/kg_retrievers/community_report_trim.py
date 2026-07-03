"""§11.2/§11.4 — community-report token-budget trimming (``max_input_length``).

Отчёт сообщества (community report) состоит из заголовка, резюме и списка находок
(findings). Перед подачей в LLM-контекст его нужно урезать под бюджет токенов, чтобы
не превысить ``max_input_length``. This module builds the report text incrementally:
``title`` + ``summary`` are *always* kept, then each finding-summary line is appended
only while the running token estimate stays within ``max_tokens``. As soon as a finding
would push the estimate over budget, it and all trailing findings are dropped and the
result is flagged ``truncated``.

Token estimation is deliberately cheap and deterministic — ``len(text) // chars_per_token``
(≈4 chars/token by default) — so trimming has no model dependency and is hand-checkable.
Результат — frozen :class:`TrimmedReport` с ``as_dict()`` для JSON-транспорта.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def estimate_tokens(text: str, chars_per_token: int = 4) -> int:
    """Cheap deterministic token estimate: ``len(text) // chars_per_token``.

    Грубая, но воспроизводимая оценка числа токенов без обращения к модели.
    ``chars_per_token`` — сколько символов приходится на один токен (по умолчанию 4).
    """
    return len(text) // chars_per_token


def _finding_line(finding: Any) -> str:
    """Extract the summary line of a single finding (строка-находка).

    A finding is normally a ``dict`` with a ``"summary"`` key; a bare string is
    accepted as-is. Missing summaries yield an empty line.
    """
    if isinstance(finding, dict):
        return str(finding.get("summary", ""))
    return str(finding)


@dataclass(frozen=True)
class TrimmedReport:
    """A community report trimmed to a token budget (§11.2/§11.4).

    ``text`` всегда содержит ``title`` + ``summary`` и столько находок, сколько
    поместилось в бюджет. ``est_tokens`` — оценка токенов итогового текста;
    ``truncated`` истинно, если хотя бы одна находка была отброшена; ``kept_findings``
    — число реально добавленных находок.
    """

    community_id: int
    text: str
    est_tokens: int
    truncated: bool
    kept_findings: int

    def as_dict(self) -> dict:
        """Return a plain ``dict`` for JSON transport (сериализация)."""
        return {
            "community_id": self.community_id,
            "text": self.text,
            "est_tokens": self.est_tokens,
            "truncated": self.truncated,
            "kept_findings": self.kept_findings,
        }


def trim_report(
    report: dict,
    *,
    max_tokens: int,
    chars_per_token: int = 4,
) -> TrimmedReport:
    """Trim a community ``report`` to fit within ``max_tokens`` (§11.2/§11.4).

    Текст строится из ``title`` + '\\n' + ``summary``; затем построчно добавляются
    находки (``report["findings"]``), пока оценка токенов не превышает ``max_tokens``.
    Первая же находка, выходящая за бюджет, вместе со всеми последующими отбрасывается,
    и ``truncated`` выставляется в ``True``.
    """
    community_id = int(report.get("community_id", 0))
    title = str(report.get("title", ""))
    summary = str(report.get("summary", ""))
    findings = list(report.get("findings", []))

    text = f"{title}\n{summary}"
    kept_findings = 0
    for finding in findings:
        candidate = f"{text}\n{_finding_line(finding)}"
        if estimate_tokens(candidate, chars_per_token) <= max_tokens:
            text = candidate
            kept_findings += 1
        else:
            break

    truncated = kept_findings < len(findings)
    return TrimmedReport(
        community_id=community_id,
        text=text,
        est_tokens=estimate_tokens(text, chars_per_token),
        truncated=truncated,
        kept_findings=kept_findings,
    )
