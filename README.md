<!-- PROJECT LOGO -->
<br />
<div align="center">

  <h3 align="center">Méthodes expérimentales pour la mécanique – Tensile test practical work</h3>

  <p align="center">
    Controlling a tensile testing machine and measuring strain from a video with Python. <br />
    <br />
    <a href="https://github.com/baristelmen/MO105/issues">Report Bug</a>
    ·
    <a href="https://github.com/baristelmen/MO105/pulls">Request Feature</a>
  </p>
</div>

<div align="center">
<table>
  <tr>
    <th align="left">Course</th>
    <td>MEC_3MO05_TA – Méthodes expérimentales pour la mécanique</td>
  </tr>
  <tr>
    <th align="left">Level</th>
    <td>Diplôme d'Ingénieur, 1st year (1A)</td>
  </tr>
  <tr>
    <th align="left">Institution</th>
    <td>ENSTA Paris – Institut Polytechnique de Paris</td>
  </tr>
  <tr>
    <th align="left">Course responsible</th>
    <td>Corinne Rouby</td>
  </tr>
  <tr>
    <th align="left">Repository maintainer</th>
    <td><a href="https://github.com/baristelmen">Baris Telmen</a></td>
  </tr>
</table>
</div>

## Table of Contents

- [About this repository](#about-this-repository)
- [Getting started](#getting-started)
  - [Requirements](#requirements)
  - [About the data in this repository](#about-the-data-in-this-repository)
  - [Get the repository](#get-the-repository)
  - [Option A: Conda environment file (recommended)](#option-a-conda-environment-file-recommended)
  - [Option B: Manual installation](#option-b-manual-installation)
  - [Run the programs](#run-the-programs)
- [Getting help](#getting-help)
- [Contributing](#contributing)
- [License](#license)

## About this repository

This repository contains the Python programs used during the tensile test practical work of the
**MEC_3MO05_TA** course. The tensile machine of the course measures the force, but **not the displacement**:
the test is filmed (a phone is enough) and the strain is measured afterwards from the video.

- **`point_tracking/`** – a desktop application that follows marks on the specimen in the video and computes
  the strain between them (a simplified DIC). Read the [student guide](point_tracking/docs/how_tracking_works.md)
  before your first analysis.
- **`control_machine/`** – the graphical interface that drives the tensile machine and records the force
  (used on the lab computer connected to the machine).
- **`examples/`** – sample data: a test video, a tracking result and force recordings, with short analysis scripts.

Synchronising the force data with the video results is part of the practical work and is done by the students.

## Getting started

### Requirements

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (Windows, macOS or Linux). On Windows, use the
  **Anaconda Prompt** (or *Miniconda Prompt*) installed with it to type the commands below.
- About 2 GB of free disk space and a network connection for the first installation.
- For your own analysis: the video of your test, recorded with a camera or a phone on a tripod.

The libraries are published for Windows, macOS (Intel and Apple Silicon) and Linux, so the same commands work everywhere.

### About the data in this repository

> [!IMPORTANT]
> **The data in `examples/` is sample data only.** It shows the expected file formats and lets you try the
> programs, but it is **not** the data you will analyse.
>
> During the practical work you produce your own data:
>
> 1. **The force recording** from `control_machine` (a text file with time and load).
> 2. **The video of your test**, imported into a new project of the `point_tracking` application.
>
> Create one `point_tracking` project per tested specimen, in a folder of your choice.

### Get the repository

```shell
git clone https://github.com/baristelmen/MO105.git
cd MO105
```

Or [download the ZIP](https://github.com/baristelmen/MO105/archive/refs/heads/main.zip), unzip it, and open a
terminal (Anaconda Prompt on Windows) in the `MO105` folder.

Both options below create a conda environment called **`tp-meca`** with Python 3.12 from conda-forge. Every
library is then installed with pip from `point_tracking/requirements.txt`.

### Option A: Conda environment file (recommended)

**Create the environment** (once):

```shell
conda env create -f point_tracking/environment.yml
```

**Activate it** (every time you open a new terminal):

```shell
conda activate tp-meca
```

To update the environment after pulling a new version of the repository:

```shell
conda env update -f point_tracking/environment.yml --prune
```

To remove it:

```shell
conda env remove -n tp-meca
```

### Option B: Manual installation

Use this if Option A fails, or to install into an environment you manage yourself:

```shell
conda create -n tp-meca -c conda-forge --override-channels python=3.12 pip
conda activate tp-meca
pip install -r point_tracking/requirements.txt
```

The application needs **Python 3.11 or newer**. With an older Python it stops with a message explaining what to do.

> [!CAUTION]
> **`conda: command not found` or `'conda' is not recognized`?** The terminal does not know conda.
> On Windows, open the **Anaconda Prompt** from the Start menu instead of the normal terminal.
> On macOS/Linux, run `conda init` once, then close and reopen the terminal.

### Run the programs

With the `tp-meca` environment activated, from the `MO105` folder:

| Program | Command |
| --- | --- |
| Point tracking (video → strain) | `python point_tracking/app.py` |
| Machine control (lab computer only) | `python control_machine/interface.py` – needs `pip install pyserial` and the machine connected |

To check the point tracking installation, run its tests:

```shell
cd point_tracking
pip install -r requirements-dev.txt
python -m pytest
```

## Getting help

- **Problems with this repository or the programs:** open an issue on the [Issues page](https://github.com/baristelmen/MO105/issues).
  Include the steps to reproduce, the error message, and your OS and Python version (`python --version`).
- **How the tracking works, settings, good practice:** see the [student guide](point_tracking/docs/how_tracking_works.md)
  and the [point tracking README](point_tracking/README.md).
- **Conda:** see the [conda user guide](https://docs.conda.io/projects/conda/en/stable/user-guide/index.html).
- **OpenCV:** see the [OpenCV documentation](https://docs.opencv.org/).

## Contributing

Contributions are welcome! If you find an issue or have an improvement to suggest, feel free to open an issue or submit a pull request.

## License

The content of this repository (programs, course material, and documentation) is open source under the
[GNU General Public License v3.0](LICENSE). Anyone is free to use, modify, and share it under the same license.

The environment installs third-party software that remains under its own license:

| Software | License |
| --- | --- |
| [Python](https://www.python.org/) | PSF License |
| [Conda](https://github.com/conda/conda) / [conda-forge](https://conda-forge.org/) packages | BSD-3-Clause (conda); each package keeps its own license |
| [OpenCV](https://opencv.org/) (`opencv-python-headless`) | Apache-2.0 |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [Matplotlib](https://matplotlib.org/) | Matplotlib License (PSF-based) |
| [PySide6 / Qt](https://www.qt.io/qt-for-python) | LGPL-3.0 |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD-2-Clause; the bundled [FFmpeg](https://ffmpeg.org/) binary is GPL-3.0 (includes x264) |
| [pySerial](https://github.com/pyserial/pyserial) (machine control) | BSD-3-Clause |

Using this environment means accepting the licenses of these components.
