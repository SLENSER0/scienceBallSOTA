"""Tests for PII scrubbing before LLM context (§19.5 privacy)."""

from __future__ import annotations

from kg_common.security.pii_scrub import (
    PiiPolicy,
    ScrubResult,
    detect_orcid,
    scrub_pii,
)

# Two independently checksum-valid ORCID iDs (ISO 7064 MOD 11-2).
_ORCID_A = "0000-0002-1825-0097"
_ORCID_B = "0000-0001-5109-3700"

_ALL_ON = PiiPolicy(mask_email=True, mask_orcid=True, mask_phone=True)


def test_orcid_masked_and_flagged() -> None:
    res = scrub_pii(f"Author {_ORCID_A} contributed.", _ALL_ON)
    assert _ORCID_A not in res.text
    assert "[REDACTED]" in res.text
    assert "orcid" in res.found


def test_email_masked_when_enabled() -> None:
    res = scrub_pii("Contact jane.doe@example.org for data.", _ALL_ON)
    assert "jane.doe@example.org" not in res.text
    assert "email" in res.found


def test_phone_masked_when_enabled() -> None:
    res = scrub_pii("Call +1-202-555-0143 now.", _ALL_ON)
    assert "0143" not in res.text
    assert "phone" in res.found


def test_phone_survives_when_disabled() -> None:
    policy = PiiPolicy(mask_email=True, mask_orcid=True, mask_phone=False)
    res = scrub_pii("Call +1-202-555-0143 now.", policy)
    assert "+1-202-555-0143" in res.text
    assert "phone" not in res.found


def test_no_pii_is_identity() -> None:
    text = "The reaction rate increased by twelve percent under load."
    res = scrub_pii(text, _ALL_ON)
    assert res.text == text
    assert res.found == ()


def test_two_orcids_both_masked() -> None:
    res = scrub_pii(f"Authors {_ORCID_A} and {_ORCID_B}.", _ALL_ON)
    assert _ORCID_A not in res.text
    assert _ORCID_B not in res.text
    assert res.text.count("[REDACTED]") == 2
    assert res.found == ("orcid",)


def test_detect_orcid_returns_raw_strings() -> None:
    found = detect_orcid(f"see {_ORCID_A} and {_ORCID_B}")
    assert found == [_ORCID_A, _ORCID_B]


def test_detect_orcid_rejects_bad_checksum() -> None:
    # Same shape as _ORCID_A but wrong final check digit.
    assert detect_orcid("0000-0002-1825-0098") == []


def test_scrubresult_as_dict_roundtrips() -> None:
    res = ScrubResult(text="masked [REDACTED]", found=("orcid", "email"))
    data = res.as_dict()
    assert data == {"text": "masked [REDACTED]", "found": ("orcid", "email")}
    assert ScrubResult(**data) == res


def test_policy_as_dict() -> None:
    assert _ALL_ON.as_dict() == {
        "mask_email": True,
        "mask_orcid": True,
        "mask_phone": True,
        "mask_marker": "[REDACTED]",
    }
