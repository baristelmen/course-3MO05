"""Tests for ptrack.core.tracking with synthetic videos of a moving speckle pattern."""

import numpy as np
import pytest

from ptrack.core.tracking import Box, search_window, track_boxes
from ptrack.core.video import VideoWriter


def speckle_image(width, height, seed=0):
    """Random grey speckle pattern (smoothed noise), like the paint on a specimen. BGR uint8."""
    import cv2
    rng = np.random.default_rng(seed)
    noise = rng.random((height, width)).astype(np.float32)
    smooth = cv2.GaussianBlur(noise, (0, 0), 2)
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min()) * 255
    return cv2.cvtColor(smooth.astype(np.uint8), cv2.COLOR_GRAY2BGR)


def write_shifted_video(path, shifts, width=320, height=240):
    """Video whose frame k is a crop of a large speckle image, moved by shifts[k] = (dx, dy) whole pixels.

    A point at (x, y) on frame 0 is at (x + dx, y + dy) on frame k.
    """
    pad = 40
    big = speckle_image(width + 2 * pad, height + 2 * pad)
    with VideoWriter(path, width, height, fps=5, crf=18) as writer:
        for dx, dy in shifts:
            writer.write(np.ascontiguousarray(big[pad - dy:pad - dy + height, pad - dx:pad - dx + width]))


def test_search_window_is_clipped_to_image():
    assert search_window(100, 100, 20, 10, 1.0, 320, 240) == (80, 90, 140, 120)
    assert search_window(5, 5, 20, 10, 1.0, 320, 240) == (0, 0, 45, 25)
    assert search_window(300, 230, 20, 10, 1.0, 320, 240) == (280, 220, 320, 240)


def test_tracking_recovers_known_shifts(tmp_path):
    shifts = [(0, 0), (1, 0), (2, 1), (4, 3), (6, 6), (8, 10)]
    video = tmp_path / "shifted.mp4"
    write_shifted_video(video, shifts)
    boxes = [Box(100, 80, 40, 40), Box(200, 150, 30, 50)]

    result = track_boxes(video, boxes, search_margin=1.0)

    assert result.top_left.shape == (len(shifts), 2, 2)
    for k, (dx, dy) in enumerate(shifts):
        for i, box in enumerate(boxes):
            assert tuple(result.top_left[k, i]) == (box.x + dx, box.y + dy)
            assert tuple(result.centres[k, i]) == (box.x + dx + box.w / 2, box.y + dy + box.h / 2)
    assert result.scores.min() > 0.95


def test_tracking_with_template_refresh(tmp_path):
    shifts = [(k, 2 * k) for k in range(8)]
    video = tmp_path / "shifted.mp4"
    write_shifted_video(video, shifts)
    result = track_boxes(video, [Box(100, 60, 40, 40)], search_margin=1.0, refresh_every=3)
    assert [tuple(p) for p in result.top_left[:, 0]] == [(100 + dx, 60 + dy) for dx, dy in shifts]


def test_box_near_the_edge(tmp_path):
    """A box touching the image border is tracked without error (search window clipped)."""
    shifts = [(0, 0), (1, 1), (2, 2)]
    video = tmp_path / "shifted.mp4"
    write_shifted_video(video, shifts)
    result = track_boxes(video, [Box(0, 0, 30, 30)], search_margin=1.0)
    assert [tuple(p) for p in result.top_left[:, 0]] == [(0, 0), (1, 1), (2, 2)]


def test_box_outside_frame_is_rejected(tmp_path):
    video = tmp_path / "shifted.mp4"
    write_shifted_video(video, [(0, 0), (1, 1)])
    with pytest.raises(ValueError):
        track_boxes(video, [Box(300, 200, 50, 50)], search_margin=1.0)


def test_motion_larger_than_search_window_gives_low_score(tmp_path):
    """If a box moves further than the search window allows, the match is poor (score drops)."""
    video = tmp_path / "jump.mp4"
    write_shifted_video(video, [(0, 0), (30, 0)])        # 30 px jump, window allows only 10 px
    result = track_boxes(video, [Box(100, 100, 20, 20)], search_margin=0.5)
    assert result.scores[1, 0] < 0.8


# --- sub-pixel accuracy (Phase 10) ------------------------------------------------------

def write_subpixel_video(path, shifts, width=320, height=240, crf=18):
    """Video whose frame k is a speckle image moved by shifts[k] = (dx, dy), fractions of a pixel allowed.

    The shift is applied with bicubic interpolation on a large image, then the centre is cropped.
    The video is compressed with H.264 (CRF 18, as in the application), so the test includes compression noise.
    """
    import cv2
    pad = 40
    big = speckle_image(width + 2 * pad, height + 2 * pad, seed=1)
    with VideoWriter(path, width, height, fps=5, crf=crf) as writer:
        for dx, dy in shifts:
            matrix = np.float32([[1, 0, dx], [0, 1, dy]])
            moved = cv2.warpAffine(big, matrix, (big.shape[1], big.shape[0]), flags=cv2.INTER_CUBIC)
            writer.write(np.ascontiguousarray(moved[pad:pad + height, pad:pad + width]))


SUBPIXEL_SHIFTS = [(0, 0), (0.25, 0.1), (0.5, 0.75), (1.3, 1.6), (2.45, 3.2), (3.9, 4.05), (5.6, 6.35)]


def test_parabola_top():
    from ptrack.core.tracking import parabola_top
    assert parabola_top(0.5, 1.0, 0.5) == 0.0                 # symmetric peak
    assert parabola_top(0.9, 1.0, 0.5) < 0                    # left neighbour higher → peak to the left
    assert parabola_top(0.5, 1.0, 0.9) > 0
    assert parabola_top(1.0, 0.5, 1.0) == 0.0                 # not a peak → no correction


def test_subpixel_accuracy(tmp_path):
    """Known sub-pixel shifts, H.264 CRF 18: RMS error < 0.06 px, largest error < 0.15 px.

    Measured while developing (40 random shifts, 4 boxes): RMS 0.030 px without compression (CRF 0),
    0.039 px at CRF 18, 0.048 px at CRF 23; whole-pixel tracking gives 0.30 px RMS.
    """
    video = tmp_path / "subpixel.mp4"
    write_subpixel_video(video, SUBPIXEL_SHIFTS)
    boxes = [Box(60, 50, 40, 40), Box(200, 140, 40, 40), Box(140, 90, 30, 50)]
    result = track_boxes(video, boxes, search_margin=1.0, subpixel=True)
    measured = result.top_left - result.top_left[0]                       # (frames, boxes, 2)
    errors = measured - np.array(SUBPIXEL_SHIFTS)[:, None, :]
    assert np.sqrt((errors ** 2).mean()) < 0.06
    assert np.abs(errors).max() < 0.15


def test_whole_pixel_mode_is_less_accurate(tmp_path):
    """Without sub-pixel the error can reach 0.5 px — the reason for the sub-pixel step."""
    video = tmp_path / "subpixel.mp4"
    write_subpixel_video(video, SUBPIXEL_SHIFTS)
    result = track_boxes(video, [Box(60, 50, 40, 40)], search_margin=1.0, subpixel=False)
    errors = [np.abs(result.top_left[k, 0] - result.top_left[0, 0] - np.array(shift)).max()
              for k, shift in enumerate(SUBPIXEL_SHIFTS)]
    assert max(errors) > 0.3


def test_refresh_only_between_lost_and_refresh_thresholds(tmp_path):
    """Score-based refresh: no refresh while the score stays high."""
    video = tmp_path / "subpixel.mp4"
    write_subpixel_video(video, SUBPIXEL_SHIFTS)
    result = track_boxes(video, [Box(60, 50, 40, 40)], 1.0, subpixel=True, refresh_threshold=0.8, lost_threshold=0.5)
    assert not result.refreshed.any()
    # with an impossible threshold every frame (after the first) is refreshed
    result = track_boxes(video, [Box(60, 50, 40, 40)], 1.0, subpixel=True, refresh_threshold=1.01, lost_threshold=0.5)
    assert result.refreshed[1:].all()
    # a box whose score is below lost_threshold is not refreshed
    result = track_boxes(video, [Box(60, 50, 40, 40)], 1.0, subpixel=True, refresh_threshold=1.01, lost_threshold=1.0)
    assert not result.refreshed.any()


def test_subpixel_with_refresh_stays_accurate(tmp_path):
    """Templates refreshed at every frame, cut at sub-pixel positions: the drift stays small."""
    video = tmp_path / "subpixel.mp4"
    write_subpixel_video(video, SUBPIXEL_SHIFTS)
    result = track_boxes(video, [Box(60, 50, 40, 40)], 1.0, subpixel=True, refresh_threshold=1.01, lost_threshold=0.0)
    final = result.top_left[-1, 0] - result.top_left[0, 0]
    assert np.abs(final - np.array(SUBPIXEL_SHIFTS[-1])).max() < 0.3


# --- B4: texture of a box -------------------------------------------------------------------

def test_box_texture():
    from ptrack.core.tracking import box_texture
    import cv2
    gray = cv2.cvtColor(speckle_image(200, 100), cv2.COLOR_BGR2GRAY)
    gray[:, 100:] = 128                                     # right half: plain area
    assert box_texture(gray, Box(10, 10, 40, 40)) > 20       # speckle
    assert box_texture(gray, Box(120, 10, 40, 40)) == 0      # plain


def test_plain_box_cannot_be_tracked(tmp_path):
    """A completely plain box cannot be matched: it keeps its position and is reported lost (score 0)."""
    video = tmp_path / "plain.mp4"
    with VideoWriter(video, 160, 120, fps=5, crf=18) as writer:
        for _ in range(3):
            writer.write(np.full((120, 160, 3), 128, dtype=np.uint8))
    result = track_boxes(video, [Box(60, 40, 30, 30)], 1.0, subpixel=True, lost_threshold=0.5)
    assert (result.scores[1:] == 0).all()
    assert (result.top_left[:, 0] == [60, 40]).all()          # does not slide away
