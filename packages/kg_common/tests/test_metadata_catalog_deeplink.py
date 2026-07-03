"""§10.7 tests — native-catalog deep-link URL builder.

RU: Ручьём проверяемые тесты для сборки deep-link в DataHub/OpenMetadata. /
EN: Hand-checkable tests for the DataHub/OpenMetadata deep-link builder.
"""

from __future__ import annotations

import pytest

from kg_common.metadata.catalog_deeplink import (
    DeepLink,
    datahub_url,
    deeplink_for,
    openmetadata_url,
)


def test_datahub_url_percent_encodes_urn() -> None:
    """DataHub URL percent-encodes the URN and strips a trailing slash."""
    expected = "http://h:9002/dataset/urn%3Ali%3Adataset%3A%28x%29"
    assert datahub_url("http://h:9002/", "urn:li:dataset:(x)") == expected


def test_datahub_url_base_without_trailing_slash_is_identical() -> None:
    """A base without a trailing slash yields the same result."""
    with_slash = datahub_url("http://h:9002/", "urn:li:dataset:(x)")
    without_slash = datahub_url("http://h:9002", "urn:li:dataset:(x)")
    assert with_slash == without_slash


def test_openmetadata_url_joins_type_and_fqn() -> None:
    """OpenMetadata URL is ``{base}/{entity_type}/{fqn}``."""
    assert openmetadata_url("http://h:8585", "table", "svc.db.t") == (
        "http://h:8585/table/svc.db.t"
    )


def test_deeplink_for_datahub_platform() -> None:
    """``deeplink_for`` dispatches to DataHub and tags the platform."""
    link = deeplink_for("datahub", "http://h", "urn:li:dataset:(x)")
    assert isinstance(link, DeepLink)
    assert link.platform == "datahub"
    assert link.url == "http://h/dataset/urn%3Ali%3Adataset%3A%28x%29"


def test_deeplink_for_openmetadata_url_suffix() -> None:
    """OpenMetadata deep-link ends with ``/{entity_type}/{fqn}``."""
    link = deeplink_for("openmetadata", "http://h", "svc.db.t", "table")
    assert link.platform == "openmetadata"
    assert link.url.endswith("/table/svc.db.t")


def test_deeplink_for_unknown_platform_raises() -> None:
    """An unsupported platform raises ``ValueError``."""
    with pytest.raises(ValueError):
        deeplink_for("mysql", "http://h", "svc.db.t")


def test_datahub_url_empty_urn_raises() -> None:
    """An empty URN raises ``ValueError``."""
    with pytest.raises(ValueError):
        datahub_url("http://h", "")


def test_as_dict_round_trips_fields() -> None:
    """``as_dict`` returns the platform/url pair as a flat dict."""
    link = deeplink_for("openmetadata", "http://h", "svc.db.t", "table")
    assert link.as_dict() == {"platform": "openmetadata", "url": "http://h/table/svc.db.t"}
