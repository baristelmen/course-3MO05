"""Output files of a tracking run.

- `write_results_csv`: results.csv, one row per processed frame (frame numbers, time, and per box:
  centre, displacement, score; then the strain of every pair).
- `write_tracking_video`: tracking.mp4, the processed video with the tracked boxes drawn on it.
- `read_results_csv`: read results.csv back (for the results page of a reopened project).
"""

import csv

import cv2
import numpy as np

from ptrack.core.analysis import box_pairs, displacements, pair_strains
from ptrack.core.video import VideoWriter, iter_frames

BOX_COLOUR = (0, 200, 0)      # green (OpenCV colours are B, G, R)
LOST_COLOUR = (0, 0, 255)     # red


def results_header(n_boxes):
    """Column names of results.csv for `n_boxes` boxes."""
    header = ["processed_frame", "source_frame", "time_s"]
    for n in range(1, n_boxes + 1):
        header += [f"roi{n}_cx", f"roi{n}_cy", f"roi{n}_ux", f"roi{n}_uy", f"roi{n}_score"]
    header += [f"strain_{i}_{j}" for i, j in box_pairs(n_boxes)]
    return header


def write_results_csv(path, processed_frames, result):
    """Write results.csv.

    `processed_frames`: list of `ProcessedFrame` (from processing) — gives source frame and time.
    `result`: `TrackingResult` for the same processed video.
    `time_s` is the source-video timestamp shifted so that frame 0 is at 0 s.
    Positions/displacements in px with 3 decimals, scores with 4, strains with 6.
    """
    n_frames, n_boxes, _ = result.centres.shape
    if len(processed_frames) != n_frames:
        raise ValueError(f"{len(processed_frames)} processed frames but {n_frames} tracked frames.")

    moves = displacements(result.centres)
    _, strains = pair_strains(result.centres)
    time_zero = processed_frames[0].source_time_s

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(results_header(n_boxes))
        for k, frame in enumerate(processed_frames):
            row = [frame.processed_frame, frame.source_frame, f"{frame.source_time_s - time_zero:.4f}"]
            for i in range(n_boxes):
                row += [f"{result.centres[k, i, 0]:.3f}", f"{result.centres[k, i, 1]:.3f}",
                        f"{moves[k, i, 0]:.3f}", f"{moves[k, i, 1]:.3f}",
                        f"{result.scores[k, i]:.4f}"]
            row += [f"{value:.6f}" for value in strains[k]]
            writer.writerow(row)


def draw_boxes(frame, top_left, boxes, scores, lost_threshold):
    """Draw every box with its number on `frame` (modified in place).

    Boxes whose score is below `lost_threshold` are drawn in red, the others in green.
    Line width and text size grow with the image size so they stay visible on 4K videos.
    """
    height, width = frame.shape[:2]
    thickness = max(1, round(width / 640))
    font_scale = 0.5 * thickness
    for i, box in enumerate(boxes):
        colour = LOST_COLOUR if scores[i] < lost_threshold else BOX_COLOUR
        x, y = int(round(top_left[i, 0])), int(round(top_left[i, 1]))
        cv2.rectangle(frame, (x, y), (x + box.w, y + box.h), colour, thickness)
        label_y = y - 4 * thickness if y > 20 * thickness else y + box.h + 15 * thickness
        cv2.putText(frame, str(i + 1), (x, label_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, colour, thickness)


def write_tracking_video(video_path, output_path, boxes, result, lost_threshold, fps, crf, progress=None):
    """Write the processed video again with the tracked boxes drawn on every frame.

    `progress`, if given, is called as progress(frames_done).
    """
    writer = None
    try:
        for k, _, frame in iter_frames(video_path):
            if writer is None:
                height, width = frame.shape[:2]
                writer = VideoWriter(output_path, width, height, fps, crf)
            draw_boxes(frame, result.top_left[k], boxes, result.scores[k], lost_threshold)
            writer.write(frame)
            if progress is not None:
                progress(k + 1)
    except BaseException:
        if writer is not None:
            writer.cancel()
        raise
    if writer is not None:
        writer.close()


def read_results_csv(path):
    """Read results.csv and return a dict of numpy arrays.

    Keys: "processed_frame", "source_frame", "time_s" (n_frames,), "centres" (n_frames, n_boxes, 2),
    "scores" (n_frames, n_boxes), "strains" (n_frames, n_pairs), "pairs" (list of (i, j)).
    """
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = np.array([[float(value) for value in row] for row in reader])
    column = {name: k for k, name in enumerate(header)}
    n_boxes = sum(1 for name in header if name.endswith("_score"))
    pairs = [tuple(int(n) for n in name.split("_")[1:]) for name in header if name.startswith("strain_")]
    centres = np.stack([rows[:, [column[f"roi{n}_cx"], column[f"roi{n}_cy"]]] for n in range(1, n_boxes + 1)], axis=1)
    return {
        "processed_frame": rows[:, column["processed_frame"]].astype(int),
        "source_frame": rows[:, column["source_frame"]].astype(int),
        "time_s": rows[:, column["time_s"]],
        "centres": centres,
        "scores": np.stack([rows[:, column[f"roi{n}_score"]] for n in range(1, n_boxes + 1)], axis=1),
        "strains": np.stack([rows[:, column[f"strain_{i}_{j}"]] for i, j in pairs], axis=1),
        "pairs": pairs,
    }
