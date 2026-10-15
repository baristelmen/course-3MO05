"""GUI tests for Phase 8: box editor and verify page (offscreen)."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ptrack.core import project
from ptrack.core.settings import DEFAULTS
from ptrack.core.tracking import Box
from ptrack.gui.main_window import MainWindow
from test_tracking import write_shifted_video


@pytest.fixture
def window(qapp, qsettings, tmp_path):
    """A window with a project already imported and processed (320x240 video)."""
    video = tmp_path / "video.mp4"
    write_shifted_video(video, [(0, k) for k in range(6)])
    root, data = project.create_project(tmp_path, "Boxes")
    project.import_video(root, data, video)
    project.process(root, data, 5, crf=18)
    window = MainWindow(qsettings=qsettings)
    window.open_project(root)
    return window


def boxes_page(window):
    return window.project_page.pages["boxes"]


def test_opens_on_box_editor(window):
    assert window.project_page.current_key() == "boxes"
    assert boxes_page(window).boxes == []
    assert not boxes_page(window).save_button.isEnabled()


def test_add_box_is_centred_with_default_size(window):
    page = boxes_page(window)
    page.add_box()
    assert page.boxes == [Box(135, 95, 50, 50)]                # (320-50)//2, (240-50)//2
    assert "At least 2 boxes" in page.problems_label.text()
    page.add_box()
    assert page.save_button.isEnabled()                         # overlapping boxes are allowed
    assert page.box_list.currentRow() == 1                      # the new box is selected


def test_edit_fields_and_validation(window):
    page = boxes_page(window)
    page.add_box()
    page.add_box()
    page.spins["x"].setValue(10)
    page.spins["y"].setValue(20)
    assert page.boxes[1] == Box(10, 20, 50, 50)
    assert page.box_list.item(1).text().startswith("Box 2:  x=10  y=20")
    page.spins["x"].setValue(300)                               # 300 + 50 > 320
    assert "not entirely inside" in page.problems_label.text()
    assert not page.save_button.isEnabled()
    page.spins["x"].setValue(10)
    page.spins["w"].setValue(4)                                 # smaller than min_size 8
    assert "smaller than" in page.problems_label.text()


def test_delete_renumbers(window):
    page = boxes_page(window)
    for _ in range(3):
        page.add_box()
    page.box_list.setCurrentRow(2)
    page.spins["y"].setValue(10)                                # mark box 3
    page.box_list.setCurrentRow(0)
    page.delete_box()
    assert len(page.boxes) == 2
    assert page.boxes[1].y == 10                                # former box 3 is now box 2
    assert page.box_list.item(1).text().startswith("Box 2:")


def test_save_verify_and_back(window):
    page = boxes_page(window)
    page.add_box()
    page.add_box()
    page.spins["y"].setValue(150)
    page.save()
    data = window.data
    assert [(r["id"], r["y"]) for r in data["rois"]] == [(1, 95), (2, 150)]
    assert window.project_page.current_key() == "verify"
    verify = window.project_page.pages["verify"]
    assert "2 boxes → 1 strain pairs" in verify.summary_label.text()

    verify.back_requested.emit()
    assert window.project_page.current_key() == "boxes"
    assert boxes_page(window).boxes == [Box(135, 95, 50, 50), Box(135, 150, 50, 50)]   # saved boxes reloaded

    window.project_page.go_to("verify")
    verify.accept()                                             # also starts tracking automatically
    assert data["steps"]["rois_verified"]
    assert project.open_project(window.root)[1]["steps"]["rois_verified"]
    assert window.project_page.current_key() == "track"
    track_page = window.project_page.pages["track"]
    while track_page.worker is not None:
        track_page.worker.wait()
        QApplication.processEvents()


def test_changing_boxes_with_results_asks_first(window, monkeypatch):
    root, data = window.root, window.data
    project.set_boxes(root, data, [Box(60, 40, 40, 40), Box(60, 150, 40, 40)], min_size=8)
    project.verify_boxes(root, data)
    project.track(root, data, DEFAULTS)
    window.project_page.refresh_pages()
    page = boxes_page(window)
    page.box_list.setCurrentRow(0)
    page.spins["x"].setValue(70)

    monkeypatch.setattr("ptrack.gui.pages.boxes_page.QMessageBox.question", lambda *a, **k: QMessageBox.No)
    page.save()
    assert data["steps"]["tracked"] and data["rois"][0]["x"] == 60          # nothing changed

    monkeypatch.setattr("ptrack.gui.pages.boxes_page.QMessageBox.question", lambda *a, **k: QMessageBox.Yes)
    page.save()
    assert not data["steps"]["tracked"] and data["rois"][0]["x"] == 70
    assert not (root / "results" / "results.csv").exists()


def test_plain_box_gets_a_warning_but_can_be_saved(window):
    page = boxes_page(window)
    page.add_box()
    page.add_box()
    assert page.warnings_label.text() == ""                      # speckle everywhere
    page.gray[:, :] = 128                                        # pretend the frame is plain
    page.check()
    assert page.warnings_label.text().startswith("Box 1 is on a plain area")
    assert page.save_button.isEnabled()                          # only a warning
