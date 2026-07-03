"""Tests for me/settings validation + defaults merge (§14.15).

Hermetic and dependency-free. Every assertion is a concrete hand-computed
value: rejection of unknown keys, out-of-range / bad-type ``page_size``,
unsupported locales; the pass-through of a valid patch; the defaults ←
current ← patch overlay precedence; and the round-trip shape of
:meth:`UserSettings.as_dict`.
"""

from __future__ import annotations

import pytest
from api_gateway.me_settings import (
    ALLOWED_LOCALES,
    ALLOWED_SETTING_KEYS,
    DEFAULT_SETTINGS,
    UserSettings,
    merge_settings,
    validate_settings,
)


def test_constants_have_expected_membership() -> None:
    assert set(ALLOWED_SETTING_KEYS) == {
        "theme",
        "locale",
        "page_size",
        "default_layout",
        "graph_mode",
    }
    assert set(ALLOWED_LOCALES) == {"en", "ru"}
    # Every default key is itself an allowed key.
    assert set(DEFAULT_SETTINGS).issubset(ALLOWED_SETTING_KEYS)


def test_validate_rejects_unknown_key() -> None:
    with pytest.raises(ValueError):
        validate_settings({"bogus": 1})


def test_validate_rejects_page_size_zero() -> None:
    with pytest.raises(ValueError):
        validate_settings({"page_size": 0})


def test_validate_rejects_page_size_above_max() -> None:
    with pytest.raises(ValueError):
        validate_settings({"page_size": 201})


def test_validate_accepts_page_size_bounds() -> None:
    assert validate_settings({"page_size": 1}) == {"page_size": 1}
    assert validate_settings({"page_size": 200}) == {"page_size": 200}


def test_validate_accepts_page_size_mid_range() -> None:
    assert validate_settings({"page_size": 50}) == {"page_size": 50}


def test_validate_rejects_bool_page_size() -> None:
    # bool is an int subclass but must not slip through as a page size.
    with pytest.raises(ValueError):
        validate_settings({"page_size": True})


def test_validate_rejects_non_int_page_size() -> None:
    with pytest.raises(ValueError):
        validate_settings({"page_size": "50"})


def test_validate_rejects_unsupported_locale() -> None:
    with pytest.raises(ValueError):
        validate_settings({"locale": "de"})


def test_validate_accepts_supported_locales() -> None:
    assert validate_settings({"locale": "en"}) == {"locale": "en"}
    assert validate_settings({"locale": "ru"}) == {"locale": "ru"}


def test_validate_empty_patch_is_empty_dict() -> None:
    assert validate_settings({}) == {}


def test_validate_returns_copy_not_input() -> None:
    patch = {"theme": "dark"}
    out = validate_settings(patch)
    assert out == {"theme": "dark"}
    assert out is not patch


def test_merge_empty_yields_all_defaults() -> None:
    settings = merge_settings({}, {})
    assert settings.values["theme"] == DEFAULT_SETTINGS["theme"]
    assert settings.values == DEFAULT_SETTINGS
    # Merge must not alias the module-level defaults dict.
    assert settings.values is not DEFAULT_SETTINGS


def test_merge_patch_overrides_current() -> None:
    settings = merge_settings({"theme": "light"}, {"theme": "dark"})
    assert settings.values["theme"] == "dark"


def test_merge_current_overrides_defaults() -> None:
    settings = merge_settings({"theme": "light"}, {})
    assert settings.values["theme"] == "light"


def test_merge_layers_all_three_sources() -> None:
    settings = merge_settings({"locale": "ru", "page_size": 10}, {"page_size": 100})
    # Default kept, current wins over default, patch wins over current.
    assert settings.values["theme"] == DEFAULT_SETTINGS["theme"]
    assert settings.values["locale"] == "ru"
    assert settings.values["page_size"] == 100


def test_merge_validates_patch() -> None:
    with pytest.raises(ValueError):
        merge_settings({}, {"page_size": 0})
    with pytest.raises(ValueError):
        merge_settings({}, {"bogus": 1})


def test_user_settings_as_dict_round_trip() -> None:
    assert UserSettings({"a": 1}).as_dict() == {"a": 1}


def test_user_settings_as_dict_is_copy() -> None:
    settings = UserSettings({"a": 1})
    out = settings.as_dict()
    out["a"] = 999
    # Mutating the returned dict must not corrupt the frozen snapshot.
    assert settings.values["a"] == 1
