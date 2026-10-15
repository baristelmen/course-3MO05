# Point tracking

Project-based point tracking (a simplified DIC) for tensile-test videos.
**Before your first analysis, read the student guide: [docs/how_tracking_works.md](docs/how_tracking_works.md)**
(how tracking works, assumptions, default settings, practical advice).

The full specification and development route are in [plan.md](plan.md). **Status: phases 0–10 done (full workflow, sub-pixel tracking).**

## Installation (Windows, macOS, Linux)

Requires [Miniconda](https://docs.conda.io/en/latest/miniconda.html). From the repository root:

```bash
conda env create -f point_tracking/environment.yml
conda activate tp-meca
```

This creates the `tp-meca` environment with Python 3.12 from conda-forge and installs every library with pip
from `requirements.txt`.

## Checking the installation

```bash
cd point_tracking
pip install -r requirements-dev.txt
python -m pytest
```

## Folder content

| Path | Content |
|---|---|
| `ptrack/` | Application code (`core/` = computations, `gui/` = interface) |
| `settings.toml` | Tuning parameters (teacher only) |
| `docs/` | Student guide (`how_tracking_works.md`) |
| `tests/` | Automatic tests |
| `legacy/` | Original scripts, kept for verification (`compare.py` runs old and new tracking side by side) |
