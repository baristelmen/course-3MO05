"""Tests for ptrack.core.project: folder layout, project.json, step rules."""

import json
import shutil

import pytest

from ptrack.core import project
from ptrack.core.settings import DEFAULTS
from ptrack.core.tracking import Box
from test_tracking import write_shifted_video
from test_video import make_test_video

BOXES = [Box(60, 40, 40, 40), Box(60, 150, 40, 40)]


# --- names ------------------------------------------------------------------

def test_clean_project_name():
    assert project.clean_project_name("  Steel group 3 ") == "Steel_group_3"


@pytest.mark.parametrize("name", ["", "   ", "a/b", "a:b", "what?", 'x"y', "a|b", "end.", "CON", "com1", "nul.txt", "tab\there"])
def test_invalid_project_names(name):
    with pytest.raises(ValueError):
        project.clean_project_name(name)


# --- create / open / save -------------------------------------------------

def test_create_project_layout(tmp_path):
    root, data = project.create_project(tmp_path, "My test", "first try")
    assert root == tmp_path / "My_test"
    for folder in ["raw", "processed", "results", "images"]:
        assert (root / folder).is_dir()
    stored = json.loads((root / "project.json").read_text())
    assert stored["project"]["name"] == "My_test"
    assert stored["project"]["description"] == "first try"
    assert project.next_step(stored) == "imported"


def test_create_refuses_existing_folder(tmp_path):
    project.create_project(tmp_path, "A")
    with pytest.raises(ValueError):
        project.create_project(tmp_path, "A")


def test_open_by_folder_or_file(tmp_path):
    root, _ = project.create_project(tmp_path, "P")
    assert project.open_project(root)[0] == root
    assert project.open_project(root / "project.json")[0] == root
    with pytest.raises(ValueError):
        project.open_project(tmp_path)


# --- full workflow ----------------------------------------------------------

@pytest.fixture
def source_video(tmp_path):
    path = tmp_path / "source" / "MyVideo.MP4"
    path.parent.mkdir()
    shifts = [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5)]
    write_shifted_video(path, shifts)          # 5 fps, 6 frames, 320x240
    return path


def run_all_steps(tmp_path, source_video):
    root, data = project.create_project(tmp_path, "Run")
    project.import_video(root, data, source_video)
    project.process(root, data, 5, crf=18)
    project.set_boxes(root, data, BOXES, min_size=8)
    project.verify_boxes(root, data)
    project.track(root, data, DEFAULTS)
    return root, data


def test_full_workflow(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    assert (root / "raw" / "input.mp4").is_file()
    assert (root / "processed" / "processed.mp4").is_file()
    assert (root / "results" / "results.csv").is_file()
    assert (root / "results" / "tracking.mp4").is_file()
    assert project.next_step(data) is None
    assert data["source_video"]["original_filename"] == "MyVideo.MP4"
    assert data["processing"]["frame_count"] == 6
    assert [r["id"] for r in data["rois"]] == [1, 2]
    assert data["settings_used"] == DEFAULTS
    assert (root / "images" / "strain_vs_time.png").is_file()
    assert (root / "images" / "score_vs_frame.png").is_file()
    assert data["results"]["refreshes_per_box"] == [0, 0]
    assert not list(root.rglob("*.tmp*"))                     # no temporary files left


def test_recomputed_mapping_matches_processing(tmp_path, source_video):
    """The frame mapping rebuilt from the raw video equals the one produced while processing."""
    from ptrack.core.processing import process_video
    root, data = run_all_steps(tmp_path, source_video)
    expected = process_video(root / data["source_video"]["file"], tmp_path / "check.mp4", 5, 18,
                             data["source_video"]["fps_nominal"])
    assert project.processed_frames(root, data) == expected
    assert "frames" not in data["processing"]


def test_mismatched_frame_count_is_detected(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    data["processing"]["frame_count"] += 1
    with pytest.raises(ValueError):
        project.track(root, data, DEFAULTS)


def test_project_can_be_moved(tmp_path, source_video):
    root, _ = run_all_steps(tmp_path, source_video)
    moved = tmp_path / "elsewhere" / "Renamed"
    moved.parent.mkdir()
    shutil.move(root, moved)
    new_root, data = project.open_project(moved)
    assert new_root == moved
    project.track(new_root, data, DEFAULTS)                     # works from the new place
    assert (moved / "results" / "results.csv").is_file()


def test_new_fps_keeps_boxes_and_deletes_results(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    project.process(root, data, 1, crf=18)
    assert len(data["rois"]) == 2 and data["steps"]["rois_verified"]
    assert not data["steps"]["tracked"]
    assert not (root / "results" / "results.csv").exists()


def test_new_boxes_delete_results(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    project.set_boxes(root, data, [Box(10, 10, 30, 30), Box(200, 100, 30, 30)], min_size=8)
    assert not data["steps"]["rois_verified"] and not data["steps"]["tracked"]
    assert not (root / "results" / "tracking.mp4").exists()
    assert list((root / "images").iterdir()) == []                # plots deleted with the results


def test_new_video_resets_everything(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    other = make_test_video(tmp_path / "other.mov", fps=10, seconds=1)
    project.import_video(root, data, other)
    assert data["steps"] == {"imported": True, "processed": False, "rois_verified": False, "tracked": False}
    assert data["rois"] == [] and data["processing"] is None
    assert sorted(p.name for p in (root / "raw").iterdir()) == ["input.mov"]
    assert list((root / "processed").iterdir()) == []
    assert list((root / "results").iterdir()) == []


def test_failed_step_leaves_project_unchanged(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    before = (root / "project.json").read_text()
    with pytest.raises(ValueError):
        project.process(root, data, 50, crf=18)                    # higher than the source FPS
    assert (root / "project.json").read_text() == before
    assert (root / "processed" / "processed.mp4").is_file()
    assert not list(root.rglob("*.tmp*"))


def test_box_rules(tmp_path, source_video):
    root, data = project.create_project(tmp_path, "Boxes")
    project.import_video(root, data, source_video)
    project.process(root, data, 5, crf=18)
    with pytest.raises(ValueError):                                # only one box
        project.set_boxes(root, data, [Box(10, 10, 20, 20)], min_size=8)
    with pytest.raises(ValueError):                                # outside the 320x240 frame
        project.set_boxes(root, data, [Box(10, 10, 20, 20), Box(310, 10, 20, 20)], min_size=8)
    with pytest.raises(ValueError):                                # too small
        project.set_boxes(root, data, [Box(10, 10, 20, 20), Box(50, 10, 4, 20)], min_size=8)


def test_steps_must_be_in_order(tmp_path):
    root, data = project.create_project(tmp_path, "Order")
    with pytest.raises(ValueError):
        project.process(root, data, 5, crf=18)
    with pytest.raises(ValueError):
        project.track(root, data, DEFAULTS)


# --- B1: missing files and damaged project.json ------------------------------------------

def test_missing_processed_video_is_repaired(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    (root / "processed" / "processed.mp4").unlink()
    root, data = project.open_project(root)
    messages = project.repair_missing_files(root, data)
    assert len(messages) == 1 and "processed video" in messages[0]
    assert data["steps"] == {"imported": True, "processed": False, "rois_verified": True, "tracked": False}
    assert len(data["rois"]) == 2                                  # boxes kept
    assert not (root / "results" / "results.csv").exists()
    assert project.open_project(root)[1]["steps"]["processed"] is False      # saved


def test_missing_results_are_repaired(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    (root / "results" / "tracking.mp4").unlink()
    messages = project.repair_missing_files(root, data)
    assert "result files are missing" in messages[0]
    assert not data["steps"]["tracked"] and data["steps"]["rois_verified"]
    assert list((root / "images").iterdir()) == []


def test_missing_source_video_resets_project(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    (root / "raw" / "input.mp4").unlink()
    shutil.rmtree(root / "images")                                  # a deleted sub-folder is created again
    messages = project.repair_missing_files(root, data)
    assert "source video" in messages[0]
    assert data["steps"] == {step: False for step in project.STEPS} and data["rois"] == []
    assert (root / "images").is_dir()


def test_complete_project_needs_no_repair(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    before = (root / "project.json").read_text()
    assert project.repair_missing_files(root, data) == []
    assert (root / "project.json").read_text() == before            # not rewritten


def test_damaged_project_file_is_rejected(tmp_path):
    root, data = project.create_project(tmp_path, "Damaged")
    del data["steps"]
    (root / "project.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="damaged"):
        project.open_project(root)
    (root / "project.json").write_text("{ not json")
    with pytest.raises(ValueError):
        project.open_project(root)


# --- B2: files in use (simulated with read-only files) ----------------------------------

@pytest.fixture
def make_read_only():
    """Make files read-only (a file open in Excel behaves the same way on Windows); restored after the test."""
    paths = []

    def make(path):
        path.chmod(0o444)
        paths.append(path)

    yield make
    for path in paths:
        path.chmod(0o644)


def test_track_refuses_when_results_file_is_in_use(tmp_path, source_video, make_read_only):
    root, data = run_all_steps(tmp_path, source_video)
    make_read_only(root / "results" / "results.csv")
    before = (root / "project.json").read_text()
    with pytest.raises(ValueError, match="results.csv cannot be modified"):
        project.track(root, data, DEFAULTS)
    assert (root / "project.json").read_text() == before
    assert not list(root.rglob("*.tmp*"))


def test_process_and_boxes_refuse_when_results_file_is_in_use(tmp_path, source_video, make_read_only):
    root, data = run_all_steps(tmp_path, source_video)
    make_read_only(root / "results" / "tracking.mp4")
    with pytest.raises(ValueError, match="tracking.mp4 cannot be modified"):
        project.process(root, data, 1, crf=18)
    with pytest.raises(ValueError, match="tracking.mp4 cannot be modified"):
        project.set_boxes(root, data, [Box(10, 10, 30, 30), Box(200, 100, 30, 30)], min_size=8)
    assert data["steps"]["tracked"] and data["processing"]["target_fps"] == 5        # nothing changed
    assert not list(root.rglob("*.tmp*"))


def test_file_locked_while_replacing_leaves_no_mixed_results(tmp_path, source_video, monkeypatch):
    """If a result file cannot be replaced at the very end, old and new results are never mixed."""
    root, data = run_all_steps(tmp_path, source_video)
    real_replace = project.os.replace

    def replace(source, target):
        if str(target).endswith("tracking.mp4"):
            raise PermissionError(13, "in use", str(target))
        real_replace(source, target)

    monkeypatch.setattr(project.os, "replace", replace)
    with pytest.raises(ValueError, match="tracking.mp4 cannot be modified"):
        project.track(root, data, DEFAULTS)
    assert not data["steps"]["tracked"]
    assert project.open_project(root)[1]["steps"]["tracked"] is False
    assert not (root / "results" / "results.csv").exists()
    assert not list(root.rglob("*.tmp*"))


# --- B3: the timestamp scans report progress, so they can be cancelled ------------------

def test_tracking_reports_scan_stage(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)
    stages = []
    project.track(root, data, DEFAULTS, progress=lambda stage, done: stages.append(stage))
    assert stages[0] == "scan" and "tracking" in stages and stages[-1] == "video"


def test_cancel_during_tracking_scan(tmp_path, source_video):
    root, data = run_all_steps(tmp_path, source_video)

    class Cancelled(Exception):
        pass

    def progress(stage, done):
        if stage == "scan":
            raise Cancelled()

    with pytest.raises(Cancelled):
        project.track(root, data, DEFAULTS, progress=progress)
    assert data["steps"]["tracked"]                     # previous results untouched
    assert not list(root.rglob("*.tmp*"))
