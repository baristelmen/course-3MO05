"""Tests for ptrack.core.video, using small videos generated with ffmpeg."""

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from ptrack.core.video import iter_frames, read_video_info

EXAMPLE_VIDEO = Path(__file__).parents[2] / "examples" / "tracking" / "essai_2.mp4"


def make_test_video(path, width=320, height=240, fps=10, seconds=2, rotation=None):
    """Write a synthetic H.264 test video; `rotation` stores a display rotation in the file."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-v", "error", "-y",
               "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}",
               "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(command, check=True)
    if rotation is not None:
        rotated = path.with_name("rotated_" + path.name)
        subprocess.run([ffmpeg, "-v", "error", "-y", "-display_rotation", str(rotation),
                        "-i", str(path), "-c", "copy", str(rotated)], check=True)
        return rotated
    return path


def test_read_video_info(tmp_path):
    video = make_test_video(tmp_path / "test.mp4", fps=10, seconds=2)
    info = read_video_info(video)
    assert (info.width, info.height) == (320, 240)
    assert info.frame_count == 20
    assert info.fps_nominal == pytest.approx(10)
    assert info.duration_s == pytest.approx(2.0, abs=0.01)
    assert info.is_vfr is False
    assert info.container == "mp4"
    assert info.rotation == 0


def test_rotated_video_is_upright(tmp_path):
    video = make_test_video(tmp_path / "test.mp4", width=320, height=240, rotation=90)
    info = read_video_info(video)
    assert (info.width, info.height) == (240, 320)
    _, _, frame = next(iter_frames(video))
    assert frame.shape == (320, 240, 3)


def test_iter_frames_gives_increasing_timestamps(tmp_path):
    video = make_test_video(tmp_path / "test.mp4", fps=10, seconds=1)
    frames = list(iter_frames(video))
    assert [index for index, _, _ in frames] == list(range(10))
    times = [time for _, time, _ in frames]
    assert times[0] == pytest.approx(0.0)
    assert times[-1] == pytest.approx(0.9, abs=0.01)


def test_missing_video_raises(tmp_path):
    with pytest.raises(ValueError):
        read_video_info(tmp_path / "missing.mp4")


@pytest.mark.skipif(not EXAMPLE_VIDEO.exists(), reason="example video not available")
def test_example_video_has_irregular_timing():
    """essai_2.mp4 (phone video) has dropped frames: its frame timing is not constant."""
    info = read_video_info(EXAMPLE_VIDEO)
    assert (info.width, info.height) == (1280, 720)
    assert info.frame_count == 808
    assert info.is_vfr is True


def test_read_frame_matches_sequential_reading(tmp_path):
    from ptrack.core.video import read_frame
    video = make_test_video(tmp_path / "test.mp4", fps=10, seconds=2)
    frames = [image for _, _, image in iter_frames(video)]
    for index in (0, 7, 19):
        assert (read_frame(video, index) == frames[index]).all()
