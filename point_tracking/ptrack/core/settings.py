"""Application settings: read `settings.toml`, fall back to built-in defaults.

The settings file is controlled by the teacher. If it is missing, or a value is missing, has the
wrong type or is outside its allowed range (RANGES), the default value below is used and a
warning is logged.
"""

import copy
import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# point_tracking/settings.toml (this file is point_tracking/ptrack/core/settings.py)
SETTINGS_FILE = Path(__file__).resolve().parents[2] / "settings.toml"

DEFAULTS = {
    "processing": {
        "crf": 18,
        "default_target_fps": 5,
    },
    "roi": {
        "default_width": 50,
        "default_height": 50,
        "min_size": 8,
        "min_texture": 8.0,
    },
    "tracker": {
        "method": "zncc",
        "search_margin": 1.0,
        "subpixel": True,
        "refresh_threshold": 0.8,
        "lost_threshold": 0.5,
    },
    "preview": {
        "update_every_n_frames": 5,
    },
}


# Allowed (minimum, maximum) of each number, both included.
RANGES = {
    ("processing", "crf"): (0, 51),
    ("processing", "default_target_fps"): (1, 1000),
    ("roi", "default_width"): (1, 10000),
    ("roi", "default_height"): (1, 10000),
    ("roi", "min_size"): (1, 1000),
    ("roi", "min_texture"): (0.0, 255.0),
    ("tracker", "search_margin"): (0.1, 10.0),
    ("tracker", "refresh_threshold"): (0.0, 1.0),
    ("tracker", "lost_threshold"): (0.0, 1.0),
    ("preview", "update_every_n_frames"): (1, 100000),
}


def load_settings(path=SETTINGS_FILE):
    """Return the settings as a nested dict {section: {key: value}}.

    Every key of DEFAULTS is always present in the result. A value from the file is used
    only if it has the same type as the default (an int is accepted where a float is expected).
    """
    settings = copy.deepcopy(DEFAULTS)

    path = Path(path)
    if not path.exists():
        logger.warning("Settings file not found (%s), using defaults.", path)
        return settings

    try:
        with open(path, "rb") as f:
            from_file = tomllib.load(f)
    except tomllib.TOMLDecodeError as error:
        logger.warning("Settings file %s is not valid TOML (%s), using defaults.", path, error)
        return settings

    for section, values in from_file.items():
        if section not in DEFAULTS or not isinstance(values, dict):
            logger.warning("Unknown settings section [%s] ignored.", section)
            continue
        for key, value in values.items():
            if key not in DEFAULTS[section]:
                logger.warning("Unknown setting %s.%s ignored.", section, key)
                continue
            default = DEFAULTS[section][key]
            if not _same_type(value, default):
                logger.warning("Setting %s.%s = %r has the wrong type, using default %r.",
                               section, key, value, default)
                continue
            low, high = RANGES.get((section, key), (None, None))
            if low is not None and not low <= value <= high:
                logger.warning("Setting %s.%s = %r is outside %s … %s, using default %r.",
                               section, key, value, low, high, default)
                continue
            settings[section][key] = value

    tracker = settings["tracker"]
    if tracker["method"] != "zncc":
        logger.warning("Unknown tracker.method %r, using 'zncc'.", tracker["method"])
        tracker["method"] = "zncc"
    if tracker["lost_threshold"] > tracker["refresh_threshold"]:
        logger.warning("tracker.lost_threshold (%s) is higher than tracker.refresh_threshold (%s), using the "
                       "defaults for both.", tracker["lost_threshold"], tracker["refresh_threshold"])
        tracker["lost_threshold"] = DEFAULTS["tracker"]["lost_threshold"]
        tracker["refresh_threshold"] = DEFAULTS["tracker"]["refresh_threshold"]
    return settings


def _same_type(value, default):
    """True if `value` can replace `default` (bool and int are kept apart; int is fine for float)."""
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(value, bool) and isinstance(default, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float))
    return isinstance(value, type(default))
