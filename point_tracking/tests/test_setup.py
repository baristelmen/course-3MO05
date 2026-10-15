"""Phase 0 checks: the environment has every library and the settings file is valid."""

import subprocess
import tomllib
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent.parent / "settings.toml"


def test_libraries_import():
    import cv2
    import imageio_ffmpeg
    import numpy
    import PySide6

    assert int(cv2.__version__.split(".")[0]) >= 4


def test_ffmpeg_has_h264_encoder():
    """The ffmpeg executable shipped with imageio-ffmpeg must be able to write H.264 (libx264)."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    assert "libx264" in output


def test_settings_file_parses():
    with open(SETTINGS_FILE, "rb") as f:
        settings = tomllib.load(f)
    assert settings["processing"]["crf"] == 18
    assert settings["processing"]["default_target_fps"] == 5
    assert settings["tracker"]["method"] == "zncc"


def test_ptrack_package_imports():
    import ptrack
    import ptrack.core
    import ptrack.gui

    assert ptrack.__version__


def test_python_version_check():
    from ptrack import python_version_problem
    assert python_version_problem((3, 12, 1)) is None
    assert python_version_problem((3, 11, 0)) is None
    message = python_version_problem((3, 10, 14))
    assert "needs Python 3.11 or newer, but this is Python 3.10.14" in message
