# Release notes

## Point tracking 2.0.0

A complete rewrite of the point tracking tool used in the tensile-test practical work. The scripts are
replaced by a desktop application that follows marks on the specimen in a video and computes the strain
between them (a simplified DIC).

### Highlights

- **Graphical application** (PySide6) for Windows, macOS and Linux, organised as a step-by-step wizard:
  import video → process → define boxes → verify → track → results.
- **Projects**: one folder per specimen, with a fixed layout (`raw/`, `processed/`, `results/`, `images/`)
  and a `project.json` that records every parameter. Projects can be moved, renamed or zipped.
- **Videos from any camera or phone** (mp4, mov, mkv, avi, webm, H.264, HEVC, rotated, variable frame rate).
  Frame times are read from the file, not computed from the frame rate.
- **Conversion to a target frame rate** with exact timing and the same resolution (H.264, CRF 18).
- **Sub-pixel tracking**: about 0.04 px typical error instead of 0.3 px with whole pixels, so small
  (elastic) strains become measurable.
- **Robust template refresh**: only when the match quality drops, instead of every 50 frames (less drift).
- **Strain for every pair of boxes**, measured along the line between the box centres (independent of
  camera tilt).
- **Results**: `results.csv` (frame numbers, time, positions, displacements, scores, strains),
  `tracking.mp4` with the boxes drawn, and the plots `strain_vs_time.png` and `score_vs_frame.png`.
- **Results page** with three tabs: summary (analysis info, warnings, quality of each box, final strains),
  interactive plots, and a frame browser.
- **Student guide**: [docs/how_tracking_works.md](docs/how_tracking_works.md) explains the method, the
  assumptions, the default settings and how to get reliable results.

### Installation

```bash
conda env create -f point_tracking/environment.yml
conda activate tp-meca
python point_tracking/app.py
```

Requires Python 3.11 or newer (the conda environment installs 3.12).

### Changes from the previous version

- The original scripts (`Tracking_Video_ZNCC.py`, `function_Tracking_video.py`, `convertfiles.py`) have been
  removed. They remain available in the git history at the tag `legacy-code-transition`.
- `results.csv` has a new format (comma-separated, centre positions, scores and strains). Synchronisation
  with the force data is still done by the students, using the `time_s` column.
- Tuning parameters are in `point_tracking/settings.toml` (for the teacher).

### Known limitations

- Cancel cannot interrupt the copy of a very large video during import; it acts once the copy is finished.
- Boxes are edited with the keyboard (x, y, width, height); mouse drawing is planned.
- Displacements are in pixels (no pixel → mm calibration yet); strains need no calibration.
- Two boxes with the same centre give `nan` strain for that pair.
- `results.csv` uses a comma and a decimal point: see the student guide §2 to open it in a French spreadsheet.
- Tested on macOS. Windows and Linux are supported but not yet fully verified (in particular files open in
  another program and paths containing accents on Windows).
