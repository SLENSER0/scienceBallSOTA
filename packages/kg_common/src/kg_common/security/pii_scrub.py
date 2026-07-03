"""PII scrubbing for LLM context (§19.5 privacy).

Персональные данные не должны попадать в контекст LLM — before any free text is
handed to a model we mask personally-identifying tokens. This module detects and
masks ORCID iDs (checksum-shaped ``NNNN-NNNN-NNNN-NNNX``), email addresses and
phone numbers according to a :class:`PiiPolicy` («политика маскирования»).

:func:`detect_orcid` validates the ISO 7064 MOD 11-2 checksum, so only
well-formed ORCID iDs are reported. :func:`scrub_pii` returns a :class:`ScrubResult`
carrying the masked text and the tuple of kinds that were found. Pure-python,
regex only — no third-party dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ORCID candidate: four groups ``NNNN-NNNN-NNNN-NNNC`` where C is a digit or 'X'.
_ORCID_RE = re.compile(r"(?<![\d-])(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])(?![\d-])")

# Email — local part @ domain with a TLD of at least two letters.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Phone — optional country code, area code, prefix and line («телефонный номер»).
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"\+?\d{1,3}[\s.\-]?"  # optional country code / leading group
    r"\(?\d{3}\)?[\s.\-]?"  # area code
    r"\d{3}[\s.\-]?"  # prefix
    r"\d{4}"  # line number
    r"(?!\d)"
)


@dataclass(frozen=True)
class PiiPolicy:
    """Which PII kinds to mask and the marker to use («политика маскирования»)."""

    mask_email: bool
    mask_orcid: bool
    mask_phone: bool
    mask_marker: str = "[REDACTED]"

    def as_dict(self) -> dict[str, Any]:
        """Serialise the policy to a plain dict."""
        return {
            "mask_email": self.mask_email,
            "mask_orcid": self.mask_orcid,
            "mask_phone": self.mask_phone,
            "mask_marker": self.mask_marker,
        }


@dataclass(frozen=True)
class ScrubResult:
    """Masked text plus the kinds of PII detected («результат маскирования»)."""

    text: str
    found: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Serialise the result to a plain dict (roundtrips via ``ScrubResult(**d)``)."""
        return {"text": self.text, "found": self.found}


def _orcid_checksum_ok(orcid: str) -> bool:
    """True if *orcid* passes the ISO 7064 MOD 11-2 checksum («контрольная сумма»)."""
    digits = orcid.replace("-", "")
    if len(digits) != 16:
        return False
    total = 0
    for ch in digits[:15]:
        if not ch.isdigit():
            return False
        total = (total + int(ch)) * 2
    expected = (12 - (total % 11)) % 11
    check = "X" if expected == 10 else str(expected)
    return digits[15].upper() == check


def detect_orcid(text: str) -> list[str]:
    """Return the raw ORCID iD strings in *text* whose checksum is valid (§19.5)."""
    return [m.group(1) for m in _ORCID_RE.finditer(text) if _orcid_checksum_ok(m.group(1))]


def scrub_pii(text: str, policy: PiiPolicy) -> ScrubResult:
    """Return *text* with policy-enabled PII masked, plus the kinds found (§19.5).

    Kinds are scrubbed most-specific first (ORCID → email → phone) so that ORCID
    digit groups are never mis-read as a phone number.
    """
    out = text
    found: list[str] = []

    if policy.mask_orcid and detect_orcid(out):
        out = _ORCID_RE.sub(
            lambda m: policy.mask_marker if _orcid_checksum_ok(m.group(1)) else m.group(0),
            out,
        )
        found.append("orcid")

    if policy.mask_email and _EMAIL_RE.search(out):
        out = _EMAIL_RE.sub(policy.mask_marker, out)
        found.append("email")

    if policy.mask_phone and _PHONE_RE.search(out):
        out = _PHONE_RE.sub(policy.mask_marker, out)
        found.append("phone")

    return ScrubResult(text=out, found=tuple(found))
