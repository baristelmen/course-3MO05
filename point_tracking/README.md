# Point tracking

Project-based point tracking (a simplified DIC) for tensile-test videos.
**Before your first analysis, read the student guide: [docs/how_tracking_works.md](docs/how_tracking_works.md)**
(how tracking works, assumptions, default settings, practical advice).

**Version 2.0.0** — see [RELEASE_NOTES.md](RELEASE_NOTES.md).

## Installation (Windows, macOS, Linux)

Requires [Miniconda](https://docs.conda.io/en/latest/miniconda.html). From the repository root:

```bash
conda env create -f point_tracking/environment.yml
conda activate tp-meca
```

This creates the `tp-meca` environment with Python 3.12 from conda-forge and installs every library with pip
from `requirements.txt`.

## Starting the application

```bash
conda activate tp-meca
python point_tracking/app.py
```

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

The original scripts (before version 2.0.0) are no longer in this folder. They are kept in the git history
at the tag `legacy-code-transition` (`git switch --detach legacy-code-transition` to look at them).
