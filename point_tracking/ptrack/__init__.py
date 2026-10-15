"""ptrack — project-based point tracking (simplified DIC) for tensile-test videos.

The Python version is checked here, before anything else is imported, so an old Python gives a
clear message instead of a confusing error later.
"""

import sys

__version__ = "0.1.0"
MINIMUM_PYTHON = (3, 11)


def python_version_problem(version_info=sys.version_info):
    """Return an error message if this Python is too old for the application, otherwise None."""
    if tuple(version_info[:2]) < MINIMUM_PYTHON:
        found = ".".join(str(part) for part in version_info[:3])
        needed = ".".join(str(part) for part in MINIMUM_PYTHON)
        return (f"Point tracking needs Python {needed} or newer, but this is Python {found}.\n"
                "Create the conda environment described in point_tracking/README.md "
                "(conda env create -f point_tracking/environment.yml), activate it, and start again.")
    return None


if python_version_problem() is not None:
    raise SystemExit(python_version_problem())
