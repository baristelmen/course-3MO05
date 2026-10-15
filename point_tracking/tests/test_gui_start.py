"""GUI tests for Phase 6: new-project dialog, start page, main window (run offscreen)."""

import json

from PySide6.QtWidgets import QDialogButtonBox

from ptrack.core import project
from ptrack.gui.main_window import MainWindow
from ptrack.gui.new_project_dialog import NewProjectDialog


def create_button(dialog):
    return dialog.buttons.button(QDialogButtonBox.Ok)


def test_dialog_validates_name(qapp, tmp_path):
    dialog = NewProjectDialog(default_location=str(tmp_path))
    assert not create_button(dialog).isEnabled()                 # empty name
    dialog.name_edit.setText("bad:name")
    assert not create_button(dialog).isEnabled()
    assert "not allowed" in dialog.error_label.text()
    dialog.name_edit.setText("Steel group 3")
    assert create_button(dialog).isEnabled()
    assert dialog.folder_label.text().endswith("Steel_group_3")


def test_dialog_creates_project(qapp, tmp_path):
    dialog = NewProjectDialog(default_location=str(tmp_path))
    dialog.name_edit.setText("My test")
    dialog.description_edit.setPlainText("hello")
    dialog.create()
    assert dialog.root == tmp_path / "My_test"
    assert json.loads((dialog.root / "project.json").read_text())["project"]["description"] == "hello"


def test_dialog_stays_open_on_error(qapp, tmp_path):
    project.create_project(tmp_path, "Twice")
    dialog = NewProjectDialog(default_location=str(tmp_path))
    dialog.name_edit.setText("Twice")
    dialog.create()
    assert dialog.root is None
    assert "already exists" in dialog.error_label.text()

    dialog.location_edit.setText(str(tmp_path / "missing"))
    dialog.name_edit.setText("Other")
    dialog.create()
    assert "does not exist" in dialog.error_label.text()


def test_open_project_and_recent_list(qapp, qsettings, tmp_path):
    root, _ = project.create_project(tmp_path, "Alpha", "desc")
    window = MainWindow(qsettings=qsettings)
    assert window.stack.currentWidget() is window.start_page

    window.open_project(root)
    assert window.stack.currentWidget() is window.project_page
    assert window.project_page.pages['overview'].name_label.text() == "Alpha"
    assert "Alpha" in window.windowTitle()
    assert window.recent_projects() == [str(root)]

    window.close_project()
    assert window.stack.currentWidget() is window.start_page
    assert window.start_page.recent_list.count() == 1


def test_recent_list_skips_deleted_projects(qapp, qsettings, tmp_path):
    first, _ = project.create_project(tmp_path, "First")
    second, _ = project.create_project(tmp_path, "Second")
    window = MainWindow(qsettings=qsettings)
    window.open_project(first)
    window.open_project(second)
    assert window.recent_projects() == [str(second), str(first)]     # most recent first
    (first / "project.json").unlink()
    assert window.recent_projects() == [str(second)]


def test_open_invalid_folder_keeps_start_page(qapp, qsettings, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr("ptrack.gui.main_window.QMessageBox.warning", lambda *args: shown.append(args))
    window = MainWindow(qsettings=qsettings)
    window.open_project(tmp_path)                                     # no project.json here
    assert shown and window.stack.currentWidget() is window.start_page


def test_save_description(qapp, qsettings, tmp_path):
    root, _ = project.create_project(tmp_path, "Desc")
    window = MainWindow(qsettings=qsettings)
    window.open_project(root)
    window.project_page.pages['overview'].description_edit.setPlainText("Group 3, steel")
    window.project_page.pages['overview'].save_description()
    assert project.open_project(root)[1]["project"]["description"] == "Group 3, steel"
