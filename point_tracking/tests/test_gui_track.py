"""GUI tests for Phase 9: automatic tracking, live preview, results page (offscreen)."""

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from ptrack.core import project
from ptrack.core.tracking import Box
from ptrack.gui.main_window import MainWindow
from test_gui_steps import wait_for_step
from test_tracking import write_shifted_video


@pytest.fixture
def window(qapp, qsettings, tmp_path):
    """A window whose project has boxes saved (not yet accepted). Video: 320x240, 40 frames, moving down 1 px per frame (20 px max)."""
    video = tmp_path / "video.mp4"
    write_shifted_video(video, [(0, k % 20) for k in range(40)])
    root, data = project.create_project(tmp_path, "Track")
    project.import_video(root, data, video)
    project.process(root, data, 5, crf=18)
    project.set_boxes(root, data, [Box(60, 40, 40, 40), Box(60, 150, 40, 40)], min_size=8)
    window = MainWindow(qsettings=qsettings)
    window.open_project(root)
    return window


def accept_and_track(qapp, window):
    window.project_page.go_to("verify")
    window.project_page.pages["verify"].accept()
    wait_for_step(qapp, window.project_page.pages["track"])


def test_accept_starts_tracking_and_shows_results(qapp, window):
    accept_and_track(qapp, window)
    pages = window.project_page.pages
    assert window.data["steps"]["tracked"]
    assert window.project_page.current_key() == "results"
    assert pages["track"].scores_label.text().startswith("Scores:")          # live preview was shown
    assert pages["track"].view.pixmap_item is not None

    results = pages["results"]
    assert [results.tabs.tabText(i) for i in range(3)] == ["Summary", "Plots", "Frames"]
    assert results.info_labels["project"].text() == "Track"
    assert results.info_labels["frames"].text().startswith("40 frames, 7.80 s")
    assert not results.warnings_box.isVisibleTo(results)                       # nothing to warn about
    # quality grid: header row + 2 boxes (+ note); "Frames lost" of box 1 is 0
    assert results.quality_grid.itemAtPosition(1, 4).widget().text() == "0"
    assert results.quality_grid.itemAtPosition(1, 5).widget().text() == "0"   # no template refresh
    strain_text = results.strain_grid.itemAtPosition(0, 0).widget().text()
    assert strain_text.startswith("<b>1–2</b>")
    assert abs(float(strain_text.split(":")[1].split()[0])) < 1e-3           # rigid motion (sub-pixel noise only)
    # plots: one checkbox per pair, PNG files saved in images/
    assert [c.text() for c in results.pair_checks] == ["1–2"]
    assert (window.root / "images" / "strain_vs_time.png").stat().st_size > 10_000
    assert (window.root / "images" / "score_vs_frame.png").stat().st_size > 10_000
    # frames tab: opens on the last frame, slider moves through the frames
    assert results.frame_spin.value() == 39
    results.frame_slider.setValue(10)
    assert results.frame_label.text().startswith("Frame 10  ·  2.00 s")


def test_reopened_project_shows_results(qapp, qsettings, window):
    accept_and_track(qapp, window)
    root = window.root
    other = MainWindow(qsettings=qsettings)
    other.open_project(root)
    assert other.project_page.current_key() == "results"
    assert other.project_page.pages["results"].info_labels["project"].text() == "Track"
    assert len(other.project_page.pages["results"].pair_checks) == 1


def test_run_again_asks_first(qapp, window, monkeypatch):
    accept_and_track(qapp, window)
    track = window.project_page.pages["track"]
    csv_path = window.root / "results" / "results.csv"
    before = csv_path.stat().st_mtime_ns

    monkeypatch.setattr("ptrack.gui.pages.track_page.QMessageBox.question", lambda *a, **k: QMessageBox.No)
    track.start_tracking()
    assert track.worker is None and csv_path.stat().st_mtime_ns == before

    monkeypatch.setattr("ptrack.gui.pages.track_page.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    track.start_tracking()
    wait_for_step(qapp, track)
    assert csv_path.stat().st_mtime_ns != before


def test_quit_during_tracking_discards_step(qapp, window, monkeypatch):
    window.project_page.go_to("verify")
    window.project_page.pages["verify"].accept()
    track = window.project_page.pages["track"]
    assert track.worker is not None
    assert not track.progress_panel.cancel_button.isVisible()                  # no Stop button

    monkeypatch.setattr("ptrack.gui.main_window.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    wait_for_step(qapp, track)
    assert not window.data["steps"]["tracked"]
    assert not (window.root / "results" / "results.csv").exists()
    assert not list(window.root.rglob("*.tmp*"))


def test_frames_slider_loads_on_release(qapp, window):
    accept_and_track(qapp, window)
    results = window.project_page.pages["results"]
    assert not results.frame_slider.hasTracking()
    results.show_frame_number(5)                                 # dragging: label only
    assert "release the slider" in results.frame_label.text()
    results.frame_slider.setValue(5)                             # released
    assert results.frame_label.text().startswith("Frame 5  ·")


def test_open_project_with_missing_files(qapp, qsettings, window, monkeypatch):
    accept_and_track(qapp, window)
    root = window.root
    (root / "processed" / "processed.mp4").unlink()
    shown = []
    monkeypatch.setattr("ptrack.gui.main_window.QMessageBox.information", lambda *a: shown.append(a[2]))
    other = MainWindow(qsettings=qsettings)
    other.open_project(root)
    assert shown and "processed video" in shown[0]
    assert other.stack.currentWidget() is other.project_page
    assert other.project_page.current_key() == "process"


def test_project_that_cannot_be_displayed_returns_to_start(qapp, qsettings, window, monkeypatch):
    warnings = []
    monkeypatch.setattr("ptrack.gui.main_window.QMessageBox.warning", lambda *a: warnings.append(a[2]))
    other = MainWindow(qsettings=qsettings)

    def broken(root, data):
        raise ValueError("cannot read")

    monkeypatch.setattr(other.project_page, "show_project", broken)
    other.open_project(window.root)
    assert warnings and "cannot be displayed" in warnings[0]
    assert other.stack.currentWidget() is other.start_page
    assert other.root is None
