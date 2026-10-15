"""Tests for ptrack.core.settings."""

import pytest

from ptrack.core.settings import DEFAULTS, SETTINGS_FILE, load_settings


def test_project_settings_file_matches_defaults():
    """The settings.toml shipped with the application contains the default values."""
    assert load_settings(SETTINGS_FILE) == DEFAULTS


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "missing.toml") == DEFAULTS


def test_value_from_file_is_used(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("[processing]\ncrf = 12\n[tracker]\nsearch_margin = 2\n")
    settings = load_settings(path)
    assert settings["processing"]["crf"] == 12
    assert settings["tracker"]["search_margin"] == 2          # int accepted for a float setting
    assert settings["roi"] == DEFAULTS["roi"]                  # untouched sections keep defaults


def test_wrong_type_and_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[processing]\ncrf = "high"\nunknown = 1\n[tracker]\nsubpixel = 1\n[other]\na = 1\n')
    assert load_settings(path) == DEFAULTS


def test_invalid_toml_gives_defaults(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("this is not toml [")
    assert load_settings(path) == DEFAULTS


# --- R1: allowed ranges --------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "[processing]\ncrf = 60\n",
    "[processing]\ndefault_target_fps = 0\n",
    "[roi]\nmin_size = 0\n",
    "[tracker]\nsearch_margin = 0\n",
    "[tracker]\nsearch_margin = -1.0\n",
    "[tracker]\nrefresh_threshold = 1.5\n",
    "[tracker]\nlost_threshold = -0.1\n",
    "[preview]\nupdate_every_n_frames = 0\n",
])
def test_values_outside_range_give_defaults(tmp_path, text):
    path = tmp_path / "settings.toml"
    path.write_text(text)
    assert load_settings(path) == DEFAULTS


def test_lost_above_refresh_threshold_gives_defaults(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("[tracker]\nrefresh_threshold = 0.4\nlost_threshold = 0.6\n")
    tracker = load_settings(path)["tracker"]
    assert (tracker["refresh_threshold"], tracker["lost_threshold"]) == (0.8, 0.5)


def test_unknown_method_gives_zncc(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[tracker]\nmethod = "magic"\n')
    assert load_settings(path)["tracker"]["method"] == "zncc"


def test_value_inside_range_is_used(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("[tracker]\nsearch_margin = 2.5\nlost_threshold = 0.3\n")
    tracker = load_settings(path)["tracker"]
    assert (tracker["search_margin"], tracker["lost_threshold"]) == (2.5, 0.3)
