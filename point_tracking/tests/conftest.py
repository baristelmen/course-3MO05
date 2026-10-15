"""Shared test setup: GUI tests run without opening windows (Qt "offscreen" platform)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for all GUI tests."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def qsettings(tmp_path):
    """Application settings stored in a temporary file (does not touch the user's real settings)."""
    from PySide6.QtCore import QSettings
    return QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
