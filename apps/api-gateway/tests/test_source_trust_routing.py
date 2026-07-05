"""Domain-reputation routing for source-trust: boundary matching + unknown→review.

Guards the 10-agent-verify fixes: substring domain matching let spoofed subdomains
('foo.edu.evil.com', 'springer-fake.ru') classify as scholarly and auto-ingest, and let
'x.com' match 'netflix.com'. Unknown hosts must route to review, not auto-ingest on year.
"""

from __future__ import annotations

import pytest
from api_gateway.routers.research import _assess_source_trust, _domain_reputation


@pytest.mark.parametrize(
    ("url", "dclass"),
    [
        # spoofs / substrings must NOT classify as scholarly/gov/junk (boundary match)
        ("https://foo.edu.evil.com/x", "unknown"),
        ("https://springer-fake.ru/x", "unknown"),
        ("https://pubmed.evil.com/x", "unknown"),
        ("https://www.education.com/x", "unknown"),  # '.edu' sits inside 'education'
        ("https://netflix.com/x", "unknown"),  # 'x.com' is a substring of 'netflix.com'
        ("https://mypubmed.ru/x", "unknown"),
        # legitimate sources classify correctly
        ("https://www.sciencedirect.com/x", "scholarly"),
        ("https://link.springer.com/x", "scholarly"),
        ("https://pubmed.ncbi.nlm.nih.gov/1", "scholarly"),
        ("https://x.foo.edu/p", "scholarly"),
        ("https://epa.gov/x", "gov"),
        ("https://x.com/p", "junk"),
        ("https://studocu.com/x", "junk"),
    ],
)
def test_domain_reputation_matches_on_boundaries(url: str, dclass: str) -> None:
    assert _domain_reputation(url)[0] == dclass


def test_unknown_host_routes_to_review() -> None:
    # an unknown host must not auto-ingest on year alone → capped to low (→ review queue)
    t = _assess_source_trust({"title": "T", "url": "https://some-random-blog.xyz/p", "year": 2025})
    assert t["domain"] == "unknown"
    assert t["trust_tier"] in ("low", "untrusted")


def test_scholarly_host_auto_ingests() -> None:
    t = _assess_source_trust({"title": "T", "url": "https://www.sciencedirect.com/p", "year": 2025})
    assert t["domain"] == "scholarly"
    assert t["trust_tier"] in ("medium", "high")
