"""Tests for ptrack.core.analysis."""

import numpy as np
import pytest

from ptrack.core.analysis import box_pairs, box_quality, displacements, pair_strains, result_warnings


def test_box_pairs():
    assert box_pairs(2) == [(1, 2)]
    assert box_pairs(3) == [(1, 2), (1, 3), (2, 3)]
    assert len(box_pairs(10)) == 45


def test_displacements():
    centres = np.array([[[10, 20], [50, 60]],
                        [[12, 19], [50, 65]]], dtype=float)
    moves = displacements(centres)
    assert moves[0].tolist() == [[0, 0], [0, 0]]
    assert moves[1].tolist() == [[2, -1], [0, 5]]


def test_strain_vertical_pair():
    # Boxes 100 px apart vertically; box 2 moves 10 px further down → strain 0.10
    centres = np.array([[[50, 100], [50, 200]],
                        [[50, 100], [50, 210]]], dtype=float)
    pairs, strains = pair_strains(centres)
    assert pairs == [(1, 2)]
    assert strains[:, 0] == pytest.approx([0.0, 0.10])


def test_strain_does_not_depend_on_tilt():
    """The same 10 % stretch along a line tilted by 30° gives the same strain."""
    angle = np.radians(30)
    direction = np.array([np.sin(angle), np.cos(angle)])
    start = np.array([300.0, 100.0])
    centres = np.array([[start, start + 100 * direction],
                        [start, start + 110 * direction]])
    _, strains = pair_strains(centres)
    assert strains[1, 0] == pytest.approx(0.10)


def test_strain_three_boxes_all_pairs():
    centres = np.array([[[0, 0], [0, 100], [0, 300]],
                        [[0, 0], [0, 110], [0, 330]]], dtype=float)
    pairs, strains = pair_strains(centres)
    assert pairs == [(1, 2), (1, 3), (2, 3)]
    assert strains[1] == pytest.approx([0.10, 0.10, 0.10])


SCORES = np.array([[1.0, 1.0],
                   [0.9, 0.4],
                   [0.95, 0.3],
                   [0.97, 0.9]])


def test_box_quality():
    qualities = box_quality(SCORES, lost_threshold=0.5)
    assert (qualities[0].lost_frames, qualities[0].first_lost_frame) == (0, None)
    assert (qualities[1].lost_frames, qualities[1].first_lost_frame) == (2, 1)
    assert (qualities[1].lowest_score, qualities[1].lowest_frame) == (pytest.approx(0.3), 2)
    assert qualities[0].mean_score == pytest.approx((0.9 + 0.95 + 0.97) / 3)     # frame 0 (always 1) left out


def test_result_warnings():
    times = np.array([0.0, 0.2, 0.4, 0.4])
    warnings = result_warnings(np.array([0, 6, 12, 12]), times, SCORES, lost_threshold=0.5)
    assert len(warnings) == 2
    assert warnings[0].startswith("Box 2 is lost in 2 frame(s), first at frame 1 (0.20 s)")
    assert warnings[1].startswith("1 frame(s) are repeated")
    assert result_warnings(np.array([0, 6, 12, 18]), times, np.ones((4, 2)), 0.5) == []
