"""Quantities computed from the tracked box centres.

- displacement of each box from frame 0 (px);
- engineering strain between every pair of boxes (no unit);
- quality of each box from the ZNCC scores (lowest, mean, lost frames);
- warnings for the results page.

Arrays follow the `TrackingResult` layout: centres[frame, box, (x, y)], scores[frame, box].
"""

from dataclasses import dataclass

import numpy as np


def displacements(centres):
    """Return ux, uy of every box relative to frame 0: array (n_frames, n_boxes, 2), in px."""
    return centres - centres[0]


def box_pairs(n_boxes):
    """Return every pair (i, j) with i < j, using box numbers starting at 1: (1, 2), (1, 3), (2, 3), …"""
    pairs = []
    for i in range(1, n_boxes + 1):
        for j in range(i + 1, n_boxes + 1):
            pairs.append((i, j))
    return pairs


def pair_strains(centres):
    """Return (pairs, strains) for every pair of boxes.

    For a pair (i, j): L = distance between the centres of boxes i and j in each frame,
    L0 = that distance in frame 0, engineering strain = (L - L0) / L0.
    The distance is measured along the line joining the two centres, so the result does not
    depend on the camera being tilted or the specimen being vertical/horizontal.
    `strains` has shape (n_frames, n_pairs); column k belongs to pairs[k].
    """
    n_boxes = centres.shape[1]
    pairs = box_pairs(n_boxes)
    strains = np.zeros((centres.shape[0], len(pairs)))
    for k, (i, j) in enumerate(pairs):
        difference = centres[:, j - 1] - centres[:, i - 1]          # vector from box i to box j
        length = np.sqrt(difference[:, 0] ** 2 + difference[:, 1] ** 2)
        strains[:, k] = (length - length[0]) / length[0]
    return pairs, strains


@dataclass
class BoxQuality:
    """Tracking quality of one box, from its ZNCC scores."""
    box: int                        # box number, starting at 1
    lowest_score: float
    lowest_frame: int               # processed frame where the lowest score occurs
    mean_score: float               # mean over frames 1 … end (frame 0 is always exactly 1)
    lost_frames: int                # number of frames with score < lost_threshold
    first_lost_frame: int | None    # first such frame, None if never lost


def box_quality(scores, lost_threshold):
    """Return one `BoxQuality` per box."""
    qualities = []
    for i in range(scores.shape[1]):
        box_scores = scores[:, i]
        lost = np.flatnonzero(box_scores < lost_threshold)
        after_reference = box_scores[1:] if len(box_scores) > 1 else box_scores
        qualities.append(BoxQuality(
            box=i + 1,
            lowest_score=float(box_scores.min()),
            lowest_frame=int(box_scores.argmin()),
            mean_score=float(after_reference.mean()),
            lost_frames=len(lost),
            first_lost_frame=int(lost[0]) if len(lost) > 0 else None,
        ))
    return qualities


def result_warnings(source_frames, time_s, scores, lost_threshold):
    """Return a list of short warning texts (empty if nothing special happened)."""
    warnings = []
    for quality in box_quality(scores, lost_threshold):
        if quality.lost_frames > 0:
            first = quality.first_lost_frame
            warnings.append(f"Box {quality.box} is lost in {quality.lost_frames} frame(s), first at frame {first} "
                            f"({time_s[first]:.2f} s): its positions there are not reliable.")
    repeated = len(source_frames) - len(np.unique(source_frames))
    if repeated > 0:
        warnings.append(f"{repeated} frame(s) are repeated because the original video has gaps longer than one "
                        "target interval (same source_frame on two rows of results.csv).")
    return warnings
