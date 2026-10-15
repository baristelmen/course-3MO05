"""Tests for the command-line program (python -m ptrack.cli …), run as a separate process."""

import subprocess
import sys
from pathlib import Path

import pytest

from test_tracking import write_shifted_video

POINT_TRACKING = Path(__file__).parent.parent
COMMANDS = ["info", "process", "track", "run", "project-new", "project-import", "project-process",
            "project-boxes", "project-track", "project-status", "project-run"]


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "ptrack.cli", *map(str, args)], cwd=POINT_TRACKING,
                          capture_output=True, text=True)


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_has_help(command):
    assert run_cli(command, "--help").returncode == 0


def test_track_and_run_commands(tmp_path):
    video = tmp_path / "video.mp4"
    write_shifted_video(video, [(0, k) for k in range(5)])
    boxes = ["--box", "60,40,40,40", "--box", "60,150,40,40"]

    track = run_cli("track", video, *boxes)
    assert track.returncode == 0, track.stderr
    assert "Frames tracked: 5" in track.stdout

    run = run_cli("run", video, "--fps", 5, *boxes, "--out-dir", tmp_path / "out")
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "out" / "results.csv").is_file()


def test_error_is_a_message_not_a_traceback(tmp_path):
    result = run_cli("info", tmp_path / "missing.mp4")
    assert result.returncode == 1
    assert "Error: Cannot open the video file" in result.stderr
    assert "Traceback" not in result.stderr
