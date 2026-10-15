"""Tests for ptrack.core.processing and the ffmpeg VideoWriter."""

import numpy as np
import pytest

from ptrack.core.processing import check_target_fps, process_video, select_frames
from ptrack.core.video import VideoWriter, iter_frames, read_video_info
from test_video import make_test_video


# --- check_target_fps -------------------------------------------------------

def test_target_fps_accepted():
    check_target_fps(5, 29.97)
    check_target_fps(30, 29.97)   # rounded source rate


@pytest.mark.parametrize("target", [0, -2, 31, 5.0, "5", True])
def test_target_fps_rejected(target):
    with pytest.raises(ValueError):
        check_target_fps(target, 29.97)


# --- select_frames ----------------------------------------------------------

def test_select_frames_regular_source():
    times = np.arange(20) / 10          # 10 fps, 0.0 … 1.9 s
    assert select_frames(times, 5) == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]


def test_select_frames_same_rate_keeps_every_frame():
    times = np.arange(20) / 10
    assert select_frames(times, 10) == list(range(20))


def test_select_frames_with_dropped_frame():
    # ~10 fps source where the frame at 0.4 s is missing
    times = np.array([0.0, 0.1, 0.2, 0.33, 0.5, 0.6, 0.7, 0.8])
    # targets 0.0, 0.2, 0.4, 0.6, 0.8 → for 0.4 the nearest frame is 0.33 (index 3)
    assert select_frames(times, 5) == [0, 2, 3, 5, 7]


def test_select_frames_long_gap_repeats_a_frame():
    times = np.array([0.0, 1.0])        # one-second gap, target 2 fps → targets 0.0, 0.5, 1.0
    assert select_frames(times, 2) == [0, 0, 1]


def test_select_frames_starts_at_first_timestamp():
    times = np.array([0.05, 0.15, 0.25, 0.35, 0.45])
    assert select_frames(times, 5) == [0, 2, 4]


# --- VideoWriter ------------------------------------------------------------

def test_video_writer_writes_h264(tmp_path):
    path = tmp_path / "out.mp4"
    with VideoWriter(path, 64, 48, fps=5, crf=18) as writer:
        for value in range(10):
            writer.write(np.full((48, 64, 3), value * 20, dtype=np.uint8))
    info = read_video_info(path)
    assert (info.width, info.height, info.frame_count) == (64, 48, 10)
    assert info.fps_nominal == pytest.approx(5)
    assert info.codec in ("avc1", "h264")


def test_video_writer_rejects_wrong_frame_size(tmp_path):
    writer = VideoWriter(tmp_path / "out.mp4", 64, 48, fps=5, crf=18)
    with pytest.raises(ValueError):
        writer.write(np.zeros((10, 10, 3), dtype=np.uint8))
    writer.cancel()
    assert not (tmp_path / "out.mp4").exists()


# --- process_video ----------------------------------------------------------

def test_process_video(tmp_path):
    source = make_test_video(tmp_path / "source.mp4", width=320, height=240, fps=10, seconds=2)
    output = tmp_path / "processed.mp4"
    frames = process_video(source, output, target_fps=5, crf=18, source_fps=10)

    assert [f.source_frame for f in frames] == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
    assert [f.processed_frame for f in frames] == list(range(10))
    assert frames[1].source_time_s == pytest.approx(0.2)

    info = read_video_info(output)
    assert (info.width, info.height) == (320, 240)      # resolution kept
    assert info.frame_count == 10
    assert info.fps_nominal == pytest.approx(5)
    assert info.is_vfr is False

    # Processed frame k shows the same image as source frame 2k (small difference from compression).
    source_images = {i: image for i, _, image in iter_frames(source)}
    for k, _, image in iter_frames(output):
        difference = np.abs(image.astype(int) - source_images[2 * k].astype(int)).mean()
        assert difference < 3


def test_process_video_rejects_too_high_fps(tmp_path):
    source = make_test_video(tmp_path / "source.mp4", fps=10, seconds=1)
    with pytest.raises(ValueError):
        process_video(source, tmp_path / "processed.mp4", target_fps=25, crf=18, source_fps=10)
    assert not (tmp_path / "processed.mp4").exists()


def test_video_writer_pads_odd_size(tmp_path):
    """H.264 needs even sizes: a 65x49 frame is written as 66x50, original pixels unchanged."""
    path = tmp_path / "odd.mp4"
    frame = np.full((49, 65, 3), 200, dtype=np.uint8)
    with VideoWriter(path, 65, 49, fps=5, crf=18) as writer:
        writer.write(frame)
    _, _, image = next(iter_frames(path))
    assert image.shape == (50, 66, 3)
    assert abs(int(image[10, 10, 0]) - 200) < 5


# --- R2: frame rate used for the FPS check ------------------------------------------------

def test_source_frame_rate():
    from ptrack.core.processing import source_frame_rate
    assert source_frame_rate(29.97, 29.9) == 29.97          # normal: header value
    assert source_frame_rate(29.97) == 29.97                # measured rate unknown (older projects)
    assert source_frame_rate(0, 30.0) == 30.0               # header missing → measured
    assert source_frame_rate(1000, 30.0) == 30.0            # header implausible → measured
    assert source_frame_rate(60, 30.0) == 60                # up to twice the measured rate is accepted


def test_video_info_has_measured_fps(tmp_path):
    info = read_video_info(make_test_video(tmp_path / "v.mp4", fps=10, seconds=1))
    assert info.fps_measured == pytest.approx(10, rel=0.01)


# --- B3: the first pass (timestamps) can be cancelled --------------------------------------

def test_processing_scan_reports_busy_progress(tmp_path):
    source = make_test_video(tmp_path / "source.mp4", fps=10, seconds=1)
    calls = []
    process_video(source, tmp_path / "out.mp4", 5, 18, 10, progress=lambda done, total: calls.append((done, total)))
    assert calls[0] == (0, 0)                               # scan: "busy", total unknown
    assert calls[-1] == (5, 5)                              # writing


def test_processing_cancelled_during_scan(tmp_path):
    source = make_test_video(tmp_path / "source.mp4", fps=10, seconds=1)

    def progress(done, total):
        if total == 0:
            raise KeyboardInterrupt                         # stands for the GUI's cancel exception

    with pytest.raises(KeyboardInterrupt):
        process_video(source, tmp_path / "out.mp4", 5, 18, 10, progress=progress)
    assert not (tmp_path / "out.mp4").exists()
