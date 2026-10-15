# Point Tracking — Refactor Plan

Status: **approved — phases 0–10 implemented** (Phase 10 done, awaiting review).

Scope: everything happens inside `point_tracking/`. `control_machine/` and `examples/` are not touched.

---

## 1. Goal

Replace the current script-based point tracker with a cross-platform Python desktop
application that performs a simplified DIC (Digital Image Correlation) workflow, organised
in **projects**:

1. Create (or open) a project. A project is a folder with a fixed internal structure.
2. Import a video from any source (iPhone, Android, reflex camera, …). It is copied into the project and its metadata is shown.
3. Convert it to a target FPS (same resolution) and save the processed video as a real file.
4. Show the reference frame (first processed frame) in full; the user adds one or more boxes (ROIs) with an **Add box** button and adjusts their position and size.
5. The user verifies the ROIs, or goes back to edit them.
6. Tracking starts automatically after verification.
7. Compute the displacement of each ROI (centre point) and the deformation (strain).
8. Write a results CSV in the project (figures are a TODO).
9. Save the project file so the project can be reopened later.

The tool is **video-only**. Synchronisation with force data is intentionally left to the
students (manual post-processing).

---

## 2. Decisions taken

| Topic | Decision |
|---|---|
| Target platforms | Windows, macOS (Intel + Apple Silicon), Linux |
| Python installation | **Miniconda** creates a conda env with Python from **conda-forge** (`--override-channels`); **all libraries installed with pip** from `requirements.txt` |
| Environment scope | `point_tracking` only (own `environment.yml`, `requirements.txt`, README) |
| GUI toolkit | **PySide6 (Qt)** |
| Video I/O | **OpenCV reads** (timestamps, rotation) and tracks; **ffmpeg from `imageio-ffmpeg` writes** H.264 videos. PyAV dropped (its bundled `libavdevice` clashes with OpenCV's on macOS) |
| Coding style | No over-abstraction: plain functions, simple dataclasses, no base classes/interfaces; short docstrings; small phases the teacher can read and try one by one (§13) |
| GUI language | English only |
| Projects | One folder per project, folder name = project name, fixed sub-folders and fixed file names (§6) |
| Paths in project file | All **relative** to the project root; root = folder containing the project file |
| Source video | **Copied** into the project as `raw/input.<ext>` (portability). Can be **replaced** later after a warning; replacing it **resets all later steps** (like a new project). Intended use: one project per tested specimen |
| Processed video | **Real file** `processed/processed.mp4`; students may use it for their own processing |
| Software parameters | All tuning values (CRF, tracker settings, thresholds, preview rate, default box size) live in **one application-wide settings file** `settings.toml` (§8.5), **controlled by the teacher**; not shown or editable in the GUI; the values used are copied into `project.json` |
| Compression quality | H.264 **CRF 18** (in `settings.toml`) |
| Project file | `project.json` in the project root |
| Project name | Spaces replaced by `_`; result is the folder name. Names with invalid characters are **rejected with a message** |
| Description | One optional free-text field (structured fields are a TODO) |
| Re-running tracking | Overwrites existing results **after a confirmation dialog** |
| Frame mapping | No separate `frame_map.csv`; frame numbers are columns of `results.csv` |
| Target FPS > source FPS | **Rejected** with an error message; GUI stays open, user cannot continue until a valid FPS is given |
| Reference frame | **Fixed to frame 0** of the processed video (not user-selectable) |
| Time | Frame 0 = time 0. Times of all frames come from the **original video timestamps**, plus frame number columns (§9.1) |
| Results CSV | One file `results/results.csv`: frame numbers, time, and per ROI centre, displacement, score, plus strain of all pairs as **extra columns** |
| Figures | **None for now** (TODO, to be decided later). `images/` folder is still created |
| ROI editing | Boxes stored in `project.json`; created with **Add box** (default: centred, 50×50 px), edited by typing `x, y` (**top-left corner**), `w, h`; **no mouse interaction** (TODO); boxes renumbered after deletion (§7.1) |
| Target FPS | **Integer only**, default **5**, editable |
| Tracking run | Always runs to the last frame; **no Stop button** |
| Tracking video | Saved as `results/tracking.mp4` (processed video with tracked boxes drawn) for visual verification with the student's own video player; the results page only shows where it is saved. In-app player is a TODO (§9.2) |
| Closing during a step | Confirmation dialog; the unfinished step is **discarded** (nothing recorded). A step is written to `project.json` only when it completes |
| Changing target FPS | Boxes **kept** (frame 0 unchanged); only tracking results reset |
| Results after a change | Any change in step 2 or 3 **deletes existing results immediately, after a warning**; results on disk always match `project.json` |
| Lost points | Detected from the ZNCC score; score of every box for every frame in `results.csv`; lost points reported on the results page |
| Overlapping boxes | Accepted; the user is responsible for placing the boxes |
| Minimum boxes | **2** (strain needs a pair); single-box displacement mode is a TODO |
| Deformation | Unitless engineering strain from the **Euclidean distance between ROI centres**, computed for **all pairs** (independent of camera tilt / orientation); no px→mm calibration needed |
| px→mm calibration | **Not implemented now**, kept as a TODO (§11, TODO) |
| Force data | Not included |
| Old scripts | Moved to `point_tracking/legacy/` for verification. `point_tracking/output.mp4` is **deleted** (the source video exists in `examples/tracking/`) |
| `examples/` | Untouched |
| File / folder names in code | Free to change |

---

## 3. Analysis of the current code

Files: `Tracking_Video_ZNCC.py` (driver), `function_Tracking_video.py` (logic),
`convertfiles.py` (resamples tracking onto force time base; out of scope for the new tool).

### 3.1 Current workflow
1. `calibrate_fps`: keeps every `round(fps_in / fps_target)`-th frame, writes `output.mp4` (`mp4v`) to the CWD.
2. `get_ref`: `cv2.selectROIs` on frame 0, shows them, terminal `y/n`; `n` exits the program.
3. `tracking_ROIs`: for each frame, `cv2.matchTemplate(TM_CCOEFF_NORMED)` (= ZNCC) of the
   reference template inside a search window 3× the ROI size around the last position;
   integer `argmax`; reference template refreshed every 50 frames.
4. `check_results`: matplotlib figure (reference points, last points, trajectories), terminal `y/n`.
5. `save_parameters`: tab-separated `time, x, y` per ROI (`x, y` = top-left corner).

### 3.2 Problems to fix
| # | Problem | Consequence |
|---|---|---|
| P1 | Integer-pixel precision only | ~0.3 % strain resolution on a 320 px gauge, too coarse for the elastic region |
| P2 | FPS conversion uses `round(fps_in/fps_target)` | e.g. 24→5 fps gives real 4.8 fps labelled 5 (4 % time error); phones record variable frame rate (VFR) |
| P3 | `frame_interval = 0` when target > source FPS | `ZeroDivisionError` |
| P4 | Lossy `mp4v` re-encode | Compression artefacts are tracked |
| P5 | No bounds check on the search window | Negative slice → crash or wrong match near the image edge |
| P6 | Periodic template refresh at integer position | Accumulated drift |
| P7 | `video.set(POS_FRAMES)` on every frame | Very slow and sometimes inaccurate on H.264/HEVC |
| P8 | Correlation score discarded | Lost points cannot be detected |
| P9 | `examples/tracking/analysis_tracking.py` computes `L/L0` and labels px as mm | Wrong quantity / units (file left untouched; the new tool computes strain correctly) |
| P10 | Hard-coded paths, terminal prompts mixed with OpenCV windows; `selectROIs` crops 4K frames on macOS | Not usable as a project-based tool; fragile on macOS |
| P11 | iPhone rotation metadata and HEVC `.mov` | Rotated or unreadable videos |
| P12 | `selectROIs` with zero ROIs crashes (`rois[0]`) | Crash |

---

## 4. Technology stack

| Library | Use |
|---|---|
| Python 3.12 (conda-forge) | Runtime |
| `numpy` | Arrays, sub-pixel fitting, strain |
| `opencv-python-headless` | Video reading (`VideoCapture`: real per-frame timestamps, automatic rotation), template matching (`matchTemplate`), drawing boxes. **Headless**: no `cv2.imshow`, avoids Qt conflicts with PySide6 |
| `imageio-ffmpeg` | Ships a ready-made `ffmpeg` executable for every OS. Frames are piped to it to write H.264 `.mp4` with CRF 18. Runs as a separate process, so no library clash with OpenCV |
| `PySide6` | GUI |
| `pytest` (dev only, `requirements-dev.txt`) | Tests |

Why not OpenCV's own `VideoWriter`: no quality (CRF) control, and the pip wheels can write H.264 only on macOS
(Windows/Linux fall back to the lossy `mp4v`). Why not PyAV: on macOS its bundled FFmpeg device library clashes
with OpenCV's (`objc: Class AVFFrameReceiver is implemented in both …`).

Rules:
- `requirements.txt` lists **package names and minimum versions only**, never build strings.
- Nothing except `python` and `pip` is installed through conda.

### 4.1 Installation (target instructions for students)
```bash
conda create -n tp-meca -c conda-forge --override-channels python=3.12 pip
conda activate tp-meca
pip install -r point_tracking/requirements.txt
python point_tracking/app.py
```
An equivalent `environment.yml` (python + pip + `-r requirements.txt`) is also provided:
`conda env create -f point_tracking/environment.yml`.

### 4.2 Cross-platform verification
A GitHub Actions workflow (`.github/workflows/point_tracking.yml` at the repository root — the only file outside
`point_tracking/`, required there by GitHub; it runs only when `point_tracking/**` changes) installs the environment and runs the tests on
Windows, macOS (Apple Silicon), macOS (Intel) and Ubuntu.

---

## 5. Code architecture

Kept deliberately flat: one module per topic, plain functions, dataclasses only to hold data.

```
point_tracking/
  plan.md
  README.md                  # install + usage
  environment.yml
  requirements.txt
  requirements-dev.txt       # + pytest
  settings.toml              # all tuning parameters (§8.5), teacher-controlled
  pytest.ini
  app.py                     # launches the GUI
  ptrack/
    __init__.py              # version
    core/                    # NO GUI imports → testable and usable from the CLI
      settings.py            # load settings.toml, fall back to defaults
      video.py               # read video info, iterate frames with timestamps (OpenCV), write frames (ffmpeg)
      processing.py          # target-FPS frame selection → processed.mp4
      tracking.py            # ZNCC tracking of the boxes (+ sub-pixel later)
      analysis.py            # displacement, strain of all pairs
      results.py             # results.csv + tracking.mp4
      project.py             # project folder, project.json, name validation, step rules
    gui/
      main_window.py
      pages/                 # one module per wizard page
    cli.py                   # small command-line entry to try each phase before the GUI exists
  legacy/                    # old scripts + reference CSV (verification only)
  tests/
```

Principle: **core never imports GUI code**. The GUI only calls core functions and displays progress.

---

## 6. Project management

### 6.1 Creating a project
The user chooses:
- **Project name** (required): becomes the folder name (spaces → `_`).
- **Parent location** (folder where the project folder is created).
- **Description** (optional single free-text field, editable later).

The application then creates:

```
<ProjectName>/
  project.json                 # project file (all parameters, relative paths)
  raw/
    input.<ext>                # copy of the source video, original extension kept
  processed/
    processed.mp4              # resampled video
  results/
    results.csv                # tracking results for all ROIs
    tracking.mp4               # processed video with tracked boxes drawn
  images/                      # created empty; reserved for figures (TODO)
```

Rules:
- Folder name = project name with spaces replaced by `_`. Leading/trailing spaces are trimmed first.
- The name is **rejected with a message** (GUI stays on the dialog) if, after that, it:
  - is empty;
  - contains a character not allowed in folder names on Windows/macOS/Linux: `\ / : * ? " < > |` or control characters;
  - ends with a dot;
  - is a reserved Windows name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`).
- If `<ProjectName>/` already exists in the chosen location, creation is refused.
- The four sub-folders are created immediately, empty.
- File names inside the project are **identical for every project** (table above).

### 6.2 Opening a project
- The user selects the project folder (or its `project.json`).
- The **project root = the folder containing `project.json`**; all other paths are resolved relative to it.
- A project can therefore be moved, renamed, copied to another computer or zipped and still open.
- A list of recently opened projects is kept in the user's application settings (not in the project).

### 6.3 Saving
- `project.json` is written automatically after every completed step, and on *File → Save*.
- A step that is not completed is never recorded. Closing the application while a step is running
  (import, processing, tracking) asks for confirmation; on confirmation the step is cancelled, its
  partial files are deleted and `project.json` stays as it was before the step started.
- Writes are atomic (write to a temp file, then rename) so a crash cannot corrupt the project file.

### 6.4 `project.json` (sketch)
```json
{
  "schema_version": 1,
  "app_version": "x.y.z",
  "project": {
    "name": "Steel_Group3",
    "description": "Free text written by the students",
    "created": "2026-10-14T18:00:00",
    "modified": "2026-10-14T18:30:00"
  },
  "source_video": {
    "file": "raw/input.mov",
    "original_filename": "IMG_0001.MOV",
    "sha256": "…",
    "container": "mov", "codec": "hevc",
    "width": 3840, "height": 2160, "rotation": 90,
    "fps_nominal": 29.97, "is_vfr": true,
    "duration_s": 62.4, "frame_count": 1870, "size_bytes": 123456789
  },
  "processing": {
    "target_fps": 5,
    "file": "processed/processed.mp4",
    "codec": "h264", "crf": 18,
    "frame_count": 312
  },
  "rois": [
    {"id": 1, "x": 540, "y": 160, "w": 40, "h": 40}
  ],
  "settings_used": {
    "roi": {"default_width": 50, "default_height": 50, "min_size": 8},
    "preview": {"update_every_n_frames": 5}
  },
  "tracker": {
    "method": "zncc",
    "search_margin": 1.0,
    "subpixel": true,
    "refresh_threshold": 0.8,
    "lost_threshold": 0.5
  },
  "results": {
    "file": "results/results.csv",
    "tracking_video": "results/tracking.mp4"
  },
  "steps": {
    "imported": true, "processed": true, "rois_verified": true, "tracked": false
  }
}
```
Only `original_filename` keeps a trace of the original name; the original absolute path is **not** stored
(portability and privacy).

### 6.5 Step state rules
- Each completed step updates `steps` in `project.json`.
- Changing an earlier step **invalidates** later steps:
  - new target FPS → warning, then processed video regenerated; **boxes kept** (frame 0 is the same image); results deleted;
  - boxes edited → warning, then results deleted;
  - rule: if results exist on disk, they always match `project.json` (no "outdated" state);
  - re-running tracking when results exist → **confirmation dialog**, then `results/` and `images/` are overwritten.
- Reopening a project resumes at the first incomplete step.
- **Replacing the source video** (step 1 again): a warning dialog explains that everything after
  step 1 will be lost. On confirmation the project is reset as if new (name and description kept):
  `raw/input.<ext>` is replaced (old file deleted, even if the extension differs), `processed/`,
  `results/` and `images/` are emptied, `processing`, `rois`, `tracker` results and all `steps`
  after *imported* are cleared.

---

## 7. User workflow (GUI wizard)

| Step | Page | What happens | Saved |
|---|---|---|---|
| 0 | Start | **New project** (name, location, description) or **Open project** / recent list | folder tree, `project.json` |
| 1 | Import video | Choose any video file (re-import = replace, with warning) → copied to `raw/input.<ext>` (progress bar); metadata shown: container, codec, resolution, rotation, nominal FPS, VFR flag, duration, frame count, file size | `source_video` |
| 2 | Process | Enter target FPS (integer, default 5). If target > source FPS: **error shown, Next disabled**, GUI stays open. Otherwise encode with progress bar and Cancel; resulting frame count and file size shown | `processed/`, `processing` |
| 3 | Define ROIs | Reference frame (frame 0 of the processed video) shown **in full** (fit to window, zoom/pan); boxes added and edited with the ROI editor (§7.1) | `rois` (draft) |
| 4 | Verify | Overlay of all boxes with their **numbers drawn on each box**; **Accept** → step 5, **Back** → step 3 | `rois`, `steps.rois_verified` |
| 5 | Track | Starts automatically (asks confirmation first if results already exist); progress bar, live preview (every N frames, downscaled), per-ROI score; runs until the last frame (no Stop button) | `results/results.csv` |
| 6 | Results | Three tabs — **Summary**: analysis info (project, description, source video, target FPS, frames + duration, tracking date, file links), warnings (lost boxes, repeated frames), quality per box (lowest score + frame, mean score excluding frame 0, frames lost, template refreshes), final strain of each pair as labels · **Plots** (matplotlib, side by side): strain vs time with a check box per pair, score vs frame with the 0.8/0.5 lines, both also saved to `images/` · **Frames**: slider through `results/tracking.mp4`. | — |

### 7.1 ROI editor (step 3)
- Keyboard / form based only. **No mouse drawing** (TODO, §11). The reference frame is always frame 0, so there is no frame selection.
- **Add box** creates a new box with default values: **50×50 px, centred in the frame**
  (`x = (W − 50) / 2`, `y = (H − 50) / 2`, rounded down), and gives it the next number.
- Each box has four editable integer fields in native video pixels:
  `x`, `y` = **top-left corner**, `w` = width, `h` = height.
- Changing a field redraws the box immediately; the selected box is highlighted; each box shows its number on the frame.
- A list shows all boxes (number, x, y, w, h); selecting a row selects the box for editing.
- **Delete box** removes the selected box; remaining boxes are **renumbered** 1, 2, 3, … in their current order.
- Validation (invalid values shown in red, *Next* disabled):
  - the box lies entirely inside the frame;
  - minimum size (e.g. 8×8 px);
  - **at least 2 boxes**.

---

## 8. Algorithms

### 8.1 Video reading and writing (`core/video.py`)
- Reading: OpenCV `VideoCapture`, sequential `read()` only (no per-frame seeking).
- Real per-frame timestamp from `CAP_PROP_POS_MSEC` after each `read()` (handles VFR; verified: `essai_2.mp4` is VFR).
- Rotation: OpenCV applies the rotation metadata automatically (`CAP_PROP_ORIENTATION_AUTO`), so frames are upright.
- Writing: frames piped to the `ffmpeg` executable from `imageio-ffmpeg` (`libx264`, CRF from settings, `yuv420p`, constant FPS).

### 8.2 Processing to target FPS (`core/resample.py`)
- Validation: `target_fps` is an integer, `1 ≤ target_fps ≤ round(source_fps)`, otherwise error (GUI does not proceed).
  The source rate is rounded so a "30 fps" phone video (29.97 in the file) accepts 30.
- Odd frame sizes (rare): H.264 needs even sizes, so one black column/row is added on the right/bottom; pixel coordinates are unchanged.
- If the source has a gap longer than `1 / target_fps`, the same source frame is written twice (keeps the constant frame rate).
- Target times `t_k = t_0 + k / target_fps`, `k = 0, 1, …` while `t_k ≤` last source timestamp,
  where `t_0` = timestamp of the first source frame.
- For each `t_k`, select the source frame with the nearest real timestamp (single sequential pass).
- Encode H.264 `.mp4` through ffmpeg (§8.1), constant frame rate = `target_fps`, same resolution as the source **after rotation is applied**
  (e.g. a portrait iPhone video stored as 3840×2160 with rotation 90° becomes 2160×3840), `yuv420p`.
- Compression quality: **CRF 18** (see §8.2.1), read from `settings.toml`.
- The mapping processed frame → source frame / source timestamp is **not stored**: at tracking time it is
  recomputed from the timestamps of `raw/input.<ext>` and `target_fps` (same deterministic frame choice),
  checked against `processing.frame_count`, and written as columns of `results.csv`.

#### 8.2.1 What CRF means
H.264 is a lossy compression. **CRF** (Constant Rate Factor) is the single number that sets the
quality/size trade-off: 0 = lossless (very large), 18 ≈ visually lossless, 23 = FFmpeg default,
higher = smaller file but fine texture is blurred. Resolution is not affected. Because tracking
relies on fine surface texture (speckle), too much compression degrades results.
Decision: CRF 18, stored in `settings.toml` (§8.5), not exposed in the GUI.

### 8.3 Tracking (`core/tracking.py`)
- Reference = frame 0 of the processed video (fixed).
- Grey-scale conversion once per frame; operate on cropped search window only.
- Search window = ROI expanded by `search_margin × (w, h)` on each side, **clipped to the image**.
- `cv2.matchTemplate(TM_CCOEFF_NORMED)` → integer peak.
- **Sub-pixel**: parabola through the peak score and its two neighbours, separately in x and y
  (`parabola_top`, `subpixel_offset`). Measured on synthetic shifts (4 boxes, 40 random shifts):
  RMS error 0.030 px without compression, **0.039 px at CRF 18**, 0.048 px at CRF 23 (largest error
  about 0.12 px at CRF 18); whole-pixel tracking: 0.30 px RMS. A Gaussian fit was tried and was not better.
- Reference template strategy: track against the frame-0 template; refresh the template only
  when `lost_threshold ≤ score < refresh_threshold` (below `lost_threshold` the image is probably not
  the mark any more, so the last good template is kept), cut at the sub-pixel position with
  bilinear interpolation (`cv2.getRectSubPix`)
  (replaces the original fixed refresh every 50 frames, which accumulates drift).

#### 8.3.1 Why refresh the template, and why only on a low score
- Without refresh, every frame is compared with the box image of frame 0. This works as long as the
  speckle inside the box still looks the same. Large strain, necking, rotation or surface changes alter
  the image; the score drops and the match can jump to a wrong place. Refreshing (new template = box
  image in a recent frame) keeps comparing like with like.
- Cost: each refresh cuts the new template at the current tracked position, including its error. The
  error becomes the new zero and adds up at every refresh (drift).
- Measured on `essai_2.mp4` (808 frames, three 40×40 boxes), final vertical movement of box 2 / box 3:
  never refreshed 49 / 49 px (lowest score 0.956); every 50 frames 48 / 51 px; every 5 frames 36 / 30 px
  (strong drift).
- Decision: refresh **only when the score drops below `refresh_threshold`** (and, from Phase 10, at the
  sub-pixel position). Small-strain tests are then never refreshed (no drift); large-strain tests are
  refreshed only when needed. The fixed "every N frames" refresh is kept only for `legacy/compare.py`.
- Store per frame and per ROI: centre `(cx, cy)`, ZNCC score.
- A box is reported as **lost** in a frame when its score < `lost_threshold` (from `settings.toml`). Tracking does not stop.
- Centre = top-left + (w/2, h/2).

### 8.4 Analysis (`core/analysis.py`)
- Displacement per ROI (px): `ux = cx − cx0`, `uy = cy − cy0`.
- Strain between a pair of ROIs (i, j), unitless:
  - `L = sqrt((cx_j − cx_i)² + (cy_j − cy_i)²)` (Euclidean distance between centres) at each frame, `L0` = at frame 0;
  - engineering strain `ε = (L − L0) / L0`.
  - Using the distance between centres makes the result independent of camera tilt and of
    the specimen being horizontal or vertical in the frame.
- Computed for **all pairs** `i < j`: `n` ROIs → `n(n−1)/2` strain series (3 ROIs → 3, 5 → 10, 10 → 45).

### 8.5 Settings file (`point_tracking/settings.toml`)
One application-wide, human-readable file with every tuning value, **edited only by the teacher** (students never change it; there is no per-project copy), read at start-up (Python's built-in `tomllib`).
Values used for a run are copied into `project.json`, so a project stays reproducible even if the settings change later.

```toml
[processing]
crf = 18                    # H.264 quality (lower = better quality, bigger file)
default_target_fps = 5

[roi]
default_width = 50          # px, new box size
default_height = 50
min_size = 8                # px

[tracker]
method = "zncc"
search_margin = 1.0         # search window = box ± margin × box size (original code: scaling_ZR = 1)
subpixel = true
refresh_threshold = 0.8     # template refreshed when score drops below this
lost_threshold = 0.5        # below this score a box counts as lost

[preview]
update_every_n_frames = 5   # live preview refresh during tracking
```
If the file is missing or a value is invalid, built-in defaults (the values above) are used and a warning is logged.

---

## 9. Output files

### 9.1 `results/results.csv`
Comma-separated, one header row, one row per processed frame, **all ROIs** in the same file:
```
processed_frame, source_frame, time_s,
roi1_cx, roi1_cy, roi1_ux, roi1_uy, roi1_score,
roi2_cx, roi2_cy, roi2_ux, roi2_uy, roi2_score,
…,
strain_1_2, strain_1_3, strain_2_3, …
```
- `processed_frame`: index in `processed.mp4` (0 = reference frame).
- `source_frame`: index of the same frame in `raw/input.<ext>`.
- `time_s`: timestamp of the frame in the **original video**, shifted so that frame 0 = 0 s.
- `roiN_cx`, `roiN_cy`: centre of ROI N in px (sub-pixel from Phase 10).
- `roiN_ux`, `roiN_uy`: displacement of the centre from frame 0, in px.
- `roiN_score`: ZNCC correlation score of box N in this frame (1 = perfect match; below `lost_threshold` = point considered lost).
- `strain_i_j`: engineering strain between ROIs i and j (unitless), all pairs `i < j` (at least one pair, since 2 boxes are required).

### 9.2 Tracking video (`results/tracking.mp4`)
- Same resolution, FPS and codec settings (CRF from `settings.toml`) as `processed.mp4`.
- Every box drawn at its tracked position with its number; boxes below `lost_threshold` in that frame drawn in red.
- Written after tracking, in one extra pass over the processed video (keeps tracking and drawing separate).
- Not played inside the application; the results page shows its path and the *Open project folder* button.

### 9.3 Figures (`images/`)
Written at the end of tracking (temporary files, renamed on success; deleted with the results):
- `strain_vs_time.png` — strain of every pair vs time;
- `score_vs_frame.png` — ZNCC score of every box vs processed frame, with `refresh_threshold` and `lost_threshold`.
Displacement plots are intentionally not drawn (displacements are in pixels, no calibration).
The number of template refreshes per box and the tracking date are stored in `project.json` → `results`.

---

## 10. Performance measures
- Single sequential decode pass; no seeking (fixes P7).
- Tracking reads the processed video (fewer frames to decode).
- Grey conversion once, cropped search windows only.
- Tracking runs in a worker thread (Qt `QThread`); GUI stays responsive.
- Live preview throttled (every N frames, downscaled).

---

## 11. Phased route

Small phases. After each one the teacher reads the code, runs the tests and tries it (command given per phase).
The next phase starts only after approval.

| Phase | Content | How to try it |
|---|---|---|
| **0 — Setup** | `legacy/` (old scripts + reference CSV), delete `output.mp4`; `requirements*.txt`, `environment.yml`, `settings.toml`, `pytest.ini`; empty package; smoke tests (libraries import, ffmpeg has `libx264`, settings file parses); CI workflow | `python -m pytest point_tracking` |
| **1 — Settings + video info** | `settings.py` (load `settings.toml` + defaults), `video.py` (read metadata, iterate frames with timestamps); `cli.py info` | `python -m ptrack.cli info <video>` |
| **2 — Processing** | `video.py` ffmpeg writer, `processing.py` (frame selection by timestamp, FPS validation); `cli.py process` | `python -m ptrack.cli process <video> --fps 5 --out <file>` |
| **3 — Tracking (integer)** | `tracking.py` (ZNCC, clipped search window, scores); legacy-equivalent mode (refresh every 50 frames) for comparison with `legacy/` | `python -m ptrack.cli track <processed> --box x,y,w,h --box …` |
| **4 — Analysis + results** | `analysis.py` (displacement, strain of all pairs), `results.py` (`results.csv`, `tracking.mp4`) | same command, writes the CSV and video |
| **5 — Projects** | `project.py` (create/open/save, name validation, relative paths, step rules); `cli.py run <project>` | `python -m ptrack.cli new …` / `run …` |
| **6 — GUI: shell + start page** | Main window, new/open project, description | `python point_tracking/app.py` |
| **7 — GUI: import + process pages** | Video info page, FPS page, progress, cancel / close confirmation | app |
| **8 — GUI: ROI editor + verify** | Frame view (fit/zoom), Add/Delete box, x/y/w/h fields, validation, verify page | app |
| **9 — GUI: track + results pages** | Worker thread, live preview, results summary | app |
| **10 — Accuracy** | Sub-pixel peak, score-based template refresh; synthetic-shift test (< 0.1 px) | tests + app |

### TODO (not scheduled)
- Video player on the results page to play `results/tracking.mp4` inside the application.
- ROI editor: mouse drawing / moving / resizing of boxes.
- Single-box mode (displacement only, no strain).
- More figures if needed (trajectories on the reference frame); displacement plots only after a px→mm calibration.
- px→mm calibration (draw a line over a known length).
- Structured project description: students, group, date, material, specimen.
- Noise-floor estimate from static frames.
- Grid mode (strain field), Lucas–Kanade and IC-GN trackers.
- Standalone builds with PyInstaller.

---

## 12. Open questions

None. New questions found during implementation are added here and discussed before coding them.

---

## 13. Coding rules

(Student-facing explanation of the method, assumptions and settings: `docs/how_tracking_works.md`.)
- Readability first: explicit loops and plain functions are preferred over clever helpers.
- No base classes, interfaces, plugin systems or factories. Dataclasses only to group data.
- Every module starts with a short docstring saying what it does; every public function/class has a short docstring
  (purpose, arguments, return value). No excessive comments.
- One phase = one reviewable change. Tests added for the core in the same phase.

---

## 14. Known limitations

| # | Limitation | Where | Effect | Possible fix (not scheduled) |
|---|---|---|---|---|
| L2 | **Files in use on Windows** are detected before each step (`check_not_in_use`) and while replacing results; verified on macOS by simulation (read-only files, failing replace), **not yet on Windows**. | `core/project.py` | Clear message, project never half updated | — |
| L3 | **Accents in paths on Windows**: OpenCV may not open files whose path contains non-ASCII characters on Windows. Works on macOS (tested with `dossier élève/vidéo.mp4`). **To verify on Windows.** | `core/video.py` | Import would fail with "Cannot open the video file" | Message advising a path without accents, or a workaround |
| L4 | **Two boxes with the same centre** give `nan` strain for that pair (L0 = 0). Decision: student's responsibility; verified that the application does not crash or freeze (results page shows `+nan`). | `core/analysis.py` | `nan` in `results.csv` for that pair | — |
| L5 | **Lost boxes still feed the strain**: positions in frames below `lost_threshold` are kept in `results.csv` (reported as lost, not removed). Decision: keep. | `core/results.py` | Strain unreliable in those frames | — |
| L6 | **`results.csv` in a French spreadsheet** (comma separator, decimal point) opens in one column on double-click. Decision: explained in the student guide §2 (import steps); no second file. | `docs/how_tracking_works.md` | — | — |
| L1 | **Cancel cannot interrupt the copy of the video during import.** Step 1 first copies the source file into `raw/` (`shutil.copyfile`, no progress callback), then reads it frame by frame. Cancel is checked at each frame, so it only takes effect once reading has started. | `core/project.py` `import_video`, `gui/pages/import_page.py` | For a very large file (several GB), pressing Cancel (or quitting) during the copy waits until the copy ends (a few seconds), then the import is cancelled and the copied file deleted. The project is never left in a broken state. | Copy in chunks with a progress callback, so Cancel is checked during the copy too. |
