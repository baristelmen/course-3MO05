"""GUI tests for Phase 7: wizard navigation, import page, process page, cancel and close (offscreen)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from ptrack.core import project
from ptrack.gui.main_window import MainWindow
from test_video import make_test_video


def wait_for_step(qapp, page):
    """Wait until the page's background step has finished and its signals were handled."""
    while page.worker is not None:
        page.worker.wait()
        qapp.processEvents()


@pytest.fixture
def window(qapp, qsettings, tmp_path):
    root, _ = project.create_project(tmp_path, "Gui")
    window = MainWindow(qsettings=qsettings)
    window.open_project(root)
    return window


@pytest.fixture
def video(tmp_path):
    return make_test_video(tmp_path / "video.mp4", fps=10, seconds=2)


def import_video(qapp, window, video):
    page = window.project_page.pages["import"]
    page.start_import(str(video))
    wait_for_step(qapp, page)


def test_new_project_opens_on_import_page(window):
    project_page = window.project_page
    assert project_page.current_key() == "import"
    assert not (project_page.step_list.item(2).flags() & Qt.ItemIsEnabled)          # "2. Process" locked


def test_import_then_process(qapp, window, video):
    project_page = window.project_page
    import_video(qapp, window, video)
    assert window.data["steps"]["imported"]
    assert project_page.pages["import"].info_labels["frame_count"].text() == "20"
    assert project_page.current_key() == "process"            # moved on automatically

    process_page = project_page.pages["process"]
    process_page.fps_spin.setValue(50)                          # higher than the 10 FPS source
    assert not process_page.process_button.isEnabled()
    assert "higher" in process_page.fps_error_label.text()
    process_page.fps_spin.setValue(5)
    assert process_page.process_button.isEnabled()
    process_page.start_processing()
    wait_for_step(qapp, process_page)
    assert window.data["steps"]["processed"]
    assert window.data["processing"]["frame_count"] == 10
    assert project_page.current_key() == "boxes"


def test_cancel_processing_leaves_project_unchanged(qapp, window, tmp_path):
    long_video = make_test_video(tmp_path / "long.mp4", fps=30, seconds=10)
    import_video(qapp, window, long_video)
    before = (window.root / "project.json").read_text()
    page = window.project_page.pages["process"]
    page.start_processing()
    page.cancel_running()
    wait_for_step(qapp, page)
    assert "cancelled" in page.status_label.text()
    assert (window.root / "project.json").read_text() == before
    assert not window.data["steps"]["processed"]
    assert list((window.root / "processed").iterdir()) == []


def test_replace_video_asks_first(qapp, window, video, tmp_path, monkeypatch):
    import_video(qapp, window, video)
    page = window.project_page.pages["import"]
    other = make_test_video(tmp_path / "other.mov", fps=10, seconds=1)
    monkeypatch.setattr("ptrack.gui.pages.import_page.QFileDialog.getOpenFileName", lambda *a, **k: (str(other), ""))

    monkeypatch.setattr("ptrack.gui.pages.import_page.QMessageBox.question", lambda *a, **k: QMessageBox.No)
    page.choose_video()
    assert window.data["source_video"]["original_filename"] == "video.mp4"      # unchanged

    monkeypatch.setattr("ptrack.gui.pages.import_page.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    page.choose_video()
    wait_for_step(qapp, page)
    assert window.data["source_video"]["original_filename"] == "other.mov"


def test_close_while_running_asks_and_cancels(qapp, window, tmp_path, monkeypatch):
    long_video = make_test_video(tmp_path / "long.mp4", fps=30, seconds=10)
    import_video(qapp, window, long_video)
    page = window.project_page.pages["process"]
    page.start_processing()
    assert not window.file_menu.isEnabled()                     # menu locked while running

    monkeypatch.setattr("ptrack.gui.main_window.QMessageBox.question", lambda *a, **k: QMessageBox.No)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()

    monkeypatch.setattr("ptrack.gui.main_window.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    wait_for_step(qapp, page)
    assert not window.data["steps"]["processed"]
    assert list((window.root / "processed").iterdir()) == []
