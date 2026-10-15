"""Projects: one folder per analysis, with a fixed layout and a project.json file.

    <ProjectName>/
      project.json         all parameters and step states (paths relative to this folder)
      raw/input.<ext>      copy of the source video
      processed/processed.mp4
      results/results.csv, results/tracking.mp4
      images/strain_vs_time.png, images/score_vs_frame.png

A project is handled as two things: `root` (Path of the project folder) and `data` (the dict
stored in project.json). The step functions (`import_video`, `process`, `set_boxes`,
`verify_boxes`, `track`) each do one wizard step and save project.json only when the step
has finished. Long steps write to temporary files first, so a step that fails or is cancelled
leaves the project exactly as it was.

Files in use: on Windows a file open in another program (results.csv in Excel, tracking.mp4 in a
video player) cannot be replaced. Each step checks this before starting (`check_not_in_use`) and
reports a clear message instead of leaving the project half updated.

Missing files: `repair_missing_files` (called when a project is opened) undoes the steps whose
files have been deleted or moved by hand.

Step rules:
- importing a (new) video resets everything after step 1;
- processing again keeps the boxes but deletes the results;
- changing the boxes deletes the results;
- tracking again overwrites the results.
"""

import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ptrack import __version__
from ptrack.core.plots import SCORE_PLOT_FILE, STRAIN_PLOT_FILE, save_plots
from ptrack.core.processing import ProcessedFrame, process_video, select_frames, source_frame_rate
from ptrack.core.results import read_results_csv, write_results_csv, write_tracking_video
from ptrack.core.tracking import Box, track_boxes
from ptrack.core.video import read_frame_times, read_video_info

PROJECT_FILE = "project.json"
SUB_FOLDERS = ["raw", "processed", "results", "images"]
PROCESSED_FILE = "processed/processed.mp4"
RESULTS_FILE = "results/results.csv"
TRACKING_VIDEO_FILE = "results/tracking.mp4"
PLOT_FILES = [f"images/{STRAIN_PLOT_FILE}", f"images/{SCORE_PLOT_FILE}"]
STEPS = ["imported", "processed", "rois_verified", "tracked"]
REQUIRED_KEYS = ["project", "source_video", "processing", "rois", "results", "settings_used", "steps"]

INVALID_CHARACTERS = '\\/:*?"<>|'
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


# --- Name, create, open, save ---------------------------------------------------------

def clean_project_name(name):
    """Return the folder name for a project name, or raise ValueError with the reason.

    Leading/trailing spaces are removed and inner spaces become "_". Names that cannot be
    a folder on Windows, macOS and Linux are rejected (not changed).
    """
    name = name.strip().replace(" ", "_")
    if not name:
        raise ValueError("The project name is empty.")
    bad = sorted({c for c in name if c in INVALID_CHARACTERS or ord(c) < 32})
    if bad:
        shown = " ".join(repr(c) if ord(c) >= 32 else f"\\x{ord(c):02x}" for c in bad)
        raise ValueError(f"The project name contains characters that are not allowed: {shown}")
    if name.endswith("."):
        raise ValueError("The project name cannot end with a dot.")
    if name.split(".")[0].upper() in RESERVED_NAMES:
        raise ValueError(f"'{name}' is a reserved name on Windows and cannot be used.")
    return name


def create_project(parent_folder, name, description=""):
    """Create the project folder, its sub-folders and project.json. Returns (root, data)."""
    folder_name = clean_project_name(name)
    parent_folder = Path(parent_folder)
    if not parent_folder.is_dir():
        raise ValueError(f"The location does not exist: {parent_folder}")
    root = parent_folder / folder_name
    if root.exists():
        raise ValueError(f"A folder named '{folder_name}' already exists in {parent_folder}.")

    root.mkdir()
    for sub_folder in SUB_FOLDERS:
        (root / sub_folder).mkdir()

    now = _now()
    data = {
        "schema_version": 1,
        "app_version": __version__,
        "project": {"name": folder_name, "description": description, "created": now, "modified": now},
        "source_video": None,
        "processing": None,
        "rois": [],
        "results": None,
        "settings_used": None,
        "steps": {step: False for step in STEPS},
    }
    save_project(root, data)
    return root, data


def open_project(path):
    """Open a project from its folder or its project.json. Returns (root, data).

    The root is always the folder that contains project.json, wherever it has been moved.
    """
    path = Path(path)
    project_file = path if path.name == PROJECT_FILE else path / PROJECT_FILE
    if not project_file.is_file():
        raise ValueError(f"No {PROJECT_FILE} found in {path}.")
    with open(project_file, encoding="utf-8") as f:
        data = json.load(f)
    missing = [key for key in REQUIRED_KEYS if key not in data]
    missing += [f"steps.{step}" for step in STEPS if step not in data.get("steps", {})]
    if missing:
        raise ValueError(f"{project_file} is damaged (missing: {', '.join(missing)}).")
    return project_file.parent, data


def save_project(root, data):
    """Write project.json safely: write a temporary file, then replace the old one in one operation."""
    data["project"]["modified"] = _now()
    data["app_version"] = __version__
    temporary = Path(root) / (PROJECT_FILE + ".tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(temporary, Path(root) / PROJECT_FILE)


def set_description(root, data, description):
    """Change the free-text description and save."""
    data["project"]["description"] = description
    save_project(root, data)


def next_step(data):
    """Return the first step that is not done ("imported", "processed", …), or None if all are done."""
    for step in STEPS:
        if not data["steps"][step]:
            return step
    return None


def repair_missing_files(root, data):
    """Check that the files of the completed steps exist; undo the steps whose files are missing.

    Returns a list of messages for the user (empty list = everything is there).
    project.json is saved only if something was changed.
    """
    root = Path(root)
    for sub_folder in SUB_FOLDERS:                  # a deleted sub-folder is simply created again
        (root / sub_folder).mkdir(exist_ok=True)
    steps = data["steps"]
    messages = []
    if steps["imported"] and not (root / data["source_video"]["file"]).is_file():
        messages.append(f"The source video ({data['source_video']['file']}) is missing: import the video again.")
        data["source_video"] = None
        data["processing"] = None
        data["rois"] = []
        data["results"] = None
        data["steps"] = {step: False for step in STEPS}
    elif steps["processed"] and not (root / PROCESSED_FILE).is_file():
        messages.append(f"The processed video ({PROCESSED_FILE}) is missing: process the video again "
                        "(the boxes are kept).")
        data["processing"] = None
        steps["processed"] = False
        _delete_results(root, data)
    elif steps["tracked"] and not all((root / f).is_file() for f in (RESULTS_FILE, TRACKING_VIDEO_FILE)):
        messages.append("Some result files are missing: run the tracking again.")
        _delete_results(root, data)
    if messages:
        save_project(root, data)
    return messages


def check_not_in_use(paths):
    """Raise ValueError if one of the existing files cannot be modified (e.g. open in Excel on Windows)."""
    for path in paths:
        if Path(path).exists():
            try:
                with open(path, "r+b"):
                    pass
            except PermissionError as error:
                raise ValueError(_in_use_message(path)) from error


# --- Step 1: import the video --------------------------------------------------------

def import_video(root, data, source_path, progress=None):
    """Copy the source video to raw/input.<ext>, read its info, reset all later steps, save.

    If the project already has a video, it is replaced (the GUI warns the user before calling this).
    `progress`, if given, is called as progress(frames_done, frames_expected) while reading the video.
    Limitation (docs/how_tracking_works.md §10): the copy has no progress callback, so it cannot be cancelled midway.
    """
    root = Path(root)
    source_path = Path(source_path)
    for sub_folder in SUB_FOLDERS:                  # in case a sub-folder was deleted by hand
        (root / sub_folder).mkdir(exist_ok=True)
    check_not_in_use([path for folder in SUB_FOLDERS for path in (root / folder).iterdir() if path.is_file()])
    extension = source_path.suffix.lower()
    temporary = root / "raw" / ("input.tmp" + extension)
    shutil.copyfile(source_path, temporary)
    try:
        info = read_video_info(temporary, progress)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    # The new video is valid: remove everything that belonged to the previous one.
    for sub_folder in ["raw", "processed", "results", "images"]:
        for old_file in (root / sub_folder).iterdir():
            if old_file != temporary:
                _remove(old_file)
    final_path = root / "raw" / ("input" + extension)
    os.replace(temporary, final_path)

    info_dict = asdict(info)
    del info_dict["file_name"]           # the stored file is given by "file" below
    info_dict["original_filename"] = source_path.name
    data["source_video"] = {"file": f"raw/{final_path.name}", **info_dict}
    data["processing"] = None
    data["rois"] = []
    data["results"] = None
    data["settings_used"] = None
    data["steps"] = {step: False for step in STEPS}
    data["steps"]["imported"] = True
    save_project(root, data)


# --- Step 2: process to the target FPS -----------------------------------------------

def process(root, data, target_fps, crf, progress=None):
    """Write processed/processed.mp4 at `target_fps`, keep the boxes, delete the results, save."""
    _require(data, "imported")
    root = Path(root)
    check_not_in_use([root / PROCESSED_FILE] + _result_paths(root))
    source = data["source_video"]
    temporary = root / "processed" / "processed.tmp.mp4"
    frames = process_video(root / source["file"], temporary, target_fps, crf,
                           source_frame_rate(source["fps_nominal"], source.get("fps_measured", 0.0)), progress)
    try:
        _delete_results(root, data)
        os.replace(temporary, root / PROCESSED_FILE)
    except PermissionError as error:
        temporary.unlink(missing_ok=True)
        save_project(root, data)              # results may already be deleted: record it
        raise ValueError(_in_use_message(error.filename)) from error

    data["processing"] = {
        "target_fps": target_fps,
        "file": PROCESSED_FILE,
        "codec": "h264",
        "crf": crf,
        "frame_count": len(frames),
    }
    data["steps"]["processed"] = True
    save_project(root, data)


def processed_frames(root, data, progress=None):
    """Return the source frame and time of every processed frame (list of `ProcessedFrame`).

    The mapping is not stored: it is recomputed from the timestamps of raw/input.<ext> and the
    target FPS, with the same frame choice as during processing, so it is always identical.
    Raises ValueError if the result does not match the processed video's frame count.
    `progress`, if given, is called as progress(frames_done, frames_expected) while scanning.
    """
    times_s, _, _ = read_frame_times(Path(root) / data["source_video"]["file"], progress)
    selected = select_frames(times_s, data["processing"]["target_fps"])
    if len(selected) != data["processing"]["frame_count"]:
        raise ValueError("The raw and processed videos do not match "
                         f"({len(selected)} frames expected, {data['processing']['frame_count']} processed). "
                         "Process the video again.")
    return [ProcessedFrame(k, index, float(times_s[index])) for k, index in enumerate(selected)]


# --- Step 3/4: boxes ---------------------------------------------------------------------

def check_boxes(boxes, frame_width, frame_height, min_size):
    """Return a list of problems (empty list = boxes are valid)."""
    problems = []
    if len(boxes) < 2:
        problems.append("At least 2 boxes are needed (strain is measured between pairs of boxes).")
    for number, box in enumerate(boxes, start=1):
        if box.w < min_size or box.h < min_size:
            problems.append(f"Box {number} is smaller than {min_size}x{min_size} px.")
        if box.x < 0 or box.y < 0 or box.x + box.w > frame_width or box.y + box.h > frame_height:
            problems.append(f"Box {number} is not entirely inside the {frame_width}x{frame_height} frame.")
    return problems


def set_boxes(root, data, boxes, min_size):
    """Store the boxes (numbered 1, 2, … in list order), mark them not verified, delete the results, save."""
    _require(data, "processed")
    problems = check_boxes(boxes, data["source_video"]["width"], data["source_video"]["height"], min_size)
    if problems:
        raise ValueError(" ".join(problems))
    check_not_in_use(_result_paths(Path(root)))
    _delete_results(Path(root), data)
    data["rois"] = [{"id": number, "x": b.x, "y": b.y, "w": b.w, "h": b.h} for number, b in enumerate(boxes, start=1)]
    data["steps"]["rois_verified"] = False
    save_project(root, data)


def get_boxes(data):
    """Return the stored boxes as a list of `Box`."""
    return [Box(r["x"], r["y"], r["w"], r["h"]) for r in data["rois"]]


def verify_boxes(root, data):
    """Mark the boxes as verified by the user (step 4) and save."""
    _require(data, "processed")
    if len(data["rois"]) < 2:
        raise ValueError("At least 2 boxes are needed.")
    data["steps"]["rois_verified"] = True
    save_project(root, data)


# --- Step 5: track -------------------------------------------------------------------------

def track(root, data, settings, progress=None, on_frame=None):
    """Track the verified boxes, write results.csv, tracking.mp4 and the plots (overwriting old results), save.

    `settings` is the dict from `load_settings()`; the values used are copied into project.json.
    `progress`, if given, is called as progress(stage, frames_done) with stage "scan" (reading the
    timestamps of the source video), "tracking" or "video".
    `on_frame` is passed to `track_boxes` (live preview).
    """
    _require(data, "rois_verified")
    root = Path(root)
    tracker = settings["tracker"]
    processed_path = root / PROCESSED_FILE
    boxes = get_boxes(data)
    check_not_in_use(_result_paths(root))

    def scan_progress(done, expected):
        if progress is not None:
            progress("scan", done)

    frames = processed_frames(root, data, scan_progress)    # check the mapping before the long tracking work

    def tracking_progress(done):
        if progress is not None:
            progress("tracking", done)

    def video_progress(done):
        if progress is not None:
            progress("video", done)

    result = track_boxes(processed_path, boxes, tracker["search_margin"], subpixel=tracker["subpixel"],
                         refresh_threshold=tracker["refresh_threshold"], lost_threshold=tracker["lost_threshold"],
                         progress=tracking_progress, on_frame=on_frame)

    csv_temporary = root / "results" / "results.tmp.csv"
    video_temporary = root / "results" / "tracking.tmp.mp4"
    plot_temporaries = []
    try:
        write_results_csv(csv_temporary, frames, result)
        write_tracking_video(processed_path, video_temporary, boxes, result, tracker["lost_threshold"],
                             data["processing"]["target_fps"], settings["processing"]["crf"],
                             progress=video_progress)
        plot_temporaries = save_plots(root / "images", read_results_csv(csv_temporary),
                                      tracker["refresh_threshold"], tracker["lost_threshold"], suffix=".tmp")
    except BaseException:
        for temporary in [csv_temporary, video_temporary] + plot_temporaries:
            temporary.unlink(missing_ok=True)
        raise
    replacements = [(csv_temporary, root / RESULTS_FILE), (video_temporary, root / TRACKING_VIDEO_FILE)]
    replacements += [(temporary, root / final) for temporary, final in zip(plot_temporaries, PLOT_FILES)]
    try:
        for temporary, final in replacements:
            os.replace(temporary, final)
    except PermissionError as error:
        # A file was in use: do not leave a mix of old and new results.
        for temporary, _ in replacements:
            temporary.unlink(missing_ok=True)
        try:
            _delete_results(root, data)
        except PermissionError:
            pass                               # still in use: repair_missing_files fixes it at next opening
        save_project(root, data)
        raise ValueError(_in_use_message(error.filename)) from error

    data["results"] = {
        "file": RESULTS_FILE,
        "tracking_video": TRACKING_VIDEO_FILE,
        "plots": PLOT_FILES,
        "tracked_at": _now(),
        # number of template refreshes of each box (not in results.csv)
        "refreshes_per_box": [int(n) for n in result.refreshed.sum(axis=0)],
    }
    data["settings_used"] = settings
    data["steps"]["tracked"] = True
    save_project(root, data)
    return result


# --- Internal helpers --------------------------------------------------------------------

def _require(data, step):
    if not data["steps"][step]:
        raise ValueError(f"This step needs the '{step}' step to be done first.")


def _result_paths(root):
    """All result files of a project (results.csv, tracking.mp4, plots)."""
    return [root / RESULTS_FILE, root / TRACKING_VIDEO_FILE] + [root / p for p in PLOT_FILES]


def _in_use_message(path):
    return (f"{Path(path).name} cannot be modified: it is probably open in another program "
            "(Excel, a video player, …). Close it and try again.")


def _delete_results(root, data):
    """Delete result files and mark tracking as not done (data is saved by the caller)."""
    for path in _result_paths(root):
        path.unlink(missing_ok=True)
    data["results"] = None
    data["steps"]["tracked"] = False


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _now():
    return datetime.now().isoformat(timespec="seconds")
