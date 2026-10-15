"""Tests for ptrack.core.results (results.csv and tracking.mp4)."""

import csv

import numpy as np
import pytest

from ptrack.core.processing import ProcessedFrame
from ptrack.core.results import read_results_csv, results_header, write_results_csv, write_tracking_video
from ptrack.core.tracking import Box, TrackingResult
from ptrack.core.video import VideoWriter, iter_frames


def make_result(top_left, boxes, scores):
    top_left = np.array(top_left, dtype=float)
    half = np.array([[b.w / 2, b.h / 2] for b in boxes])
    return TrackingResult(top_left=top_left, centres=top_left + half, scores=np.array(scores, dtype=float))


def test_results_header():
    assert results_header(2) == [
        "processed_frame", "source_frame", "time_s",
        "roi1_cx", "roi1_cy", "roi1_ux", "roi1_uy", "roi1_score",
        "roi2_cx", "roi2_cy", "roi2_ux", "roi2_uy", "roi2_score",
        "strain_1_2",
    ]


def test_write_results_csv(tmp_path):
    boxes = [Box(40, 90, 20, 20), Box(40, 190, 20, 20)]          # centres (50, 100) and (50, 200)
    result = make_result([[[40, 90], [40, 190]],
                          [[40, 90], [40, 200]]], boxes, [[1, 1], [0.9, 0.8]])
    frames = [ProcessedFrame(0, 3, 0.1), ProcessedFrame(1, 9, 0.3)]
    path = tmp_path / "results.csv"
    write_results_csv(path, frames, result)

    rows = list(csv.DictReader(open(path, newline="")))
    assert len(rows) == 2
    assert rows[1]["processed_frame"] == "1"
    assert rows[1]["source_frame"] == "9"
    assert float(rows[0]["time_s"]) == 0.0                       # time starts at 0 on frame 0
    assert float(rows[1]["time_s"]) == pytest.approx(0.2)
    assert float(rows[1]["roi2_cy"]) == 210.0
    assert float(rows[1]["roi2_uy"]) == 10.0
    assert float(rows[1]["roi2_score"]) == pytest.approx(0.8)
    assert float(rows[1]["strain_1_2"]) == pytest.approx(0.10)


def test_write_results_csv_checks_frame_count(tmp_path):
    boxes = [Box(0, 0, 10, 10), Box(20, 20, 10, 10)]
    result = make_result([[[0, 0], [20, 20]]], boxes, [[1, 1]])
    with pytest.raises(ValueError):
        write_results_csv(tmp_path / "r.csv", [ProcessedFrame(0, 0, 0), ProcessedFrame(1, 1, 0.2)], result)


def test_tracking_video_draws_green_and_red_boxes(tmp_path):
    processed = tmp_path / "processed.mp4"
    with VideoWriter(processed, 160, 120, fps=5, crf=18) as writer:
        for _ in range(2):
            writer.write(np.zeros((120, 160, 3), dtype=np.uint8))       # black frames
    boxes = [Box(20, 30, 40, 40), Box(100, 30, 40, 40)]
    # frame 1: box 2 has a low score → red
    result = make_result([[[20, 30], [100, 30]], [[20, 30], [100, 30]]], boxes, [[1, 1], [1, 0.2]])
    output = tmp_path / "tracking.mp4"
    write_tracking_video(processed, output, boxes, result, lost_threshold=0.5, fps=5, crf=18)

    frames = [image for _, _, image in iter_frames(output)]
    assert len(frames) == 2
    left_edge_box2 = frames[1][50, 100]                # a pixel on box 2's left side (B, G, R)
    left_edge_box1 = frames[1][50, 20]
    assert left_edge_box2[2] > 150 and left_edge_box2[1] < 80     # red
    assert left_edge_box1[1] > 150 and left_edge_box1[2] < 80     # green


def test_read_results_csv_round_trip(tmp_path):
    boxes = [Box(40, 90, 20, 20), Box(40, 190, 20, 20), Box(100, 90, 20, 20)]
    result = make_result([[[40, 90], [40, 190], [100, 90]],
                          [[40, 90], [40, 200], [101, 90]]], boxes, [[1, 1, 1], [0.9, 0.8, 0.7]])
    frames = [ProcessedFrame(0, 3, 0.1), ProcessedFrame(1, 9, 0.3)]
    path = tmp_path / "results.csv"
    write_results_csv(path, frames, result)
    read = read_results_csv(path)
    assert read["processed_frame"].tolist() == [0, 1]
    assert read["source_frame"].tolist() == [3, 9]
    assert read["centres"] == pytest.approx(result.centres)
    assert read["scores"] == pytest.approx(result.scores)
    assert read["pairs"] == [(1, 2), (1, 3), (2, 3)]
    assert read["strains"][1, 0] == pytest.approx(0.10)
