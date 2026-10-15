"""Tracking of rectangular boxes with ZNCC template matching (OpenCV `matchTemplate`).

For every box drawn on frame 0:
- the image inside the box is the *template*;
- in each next frame, the template is searched in a *search window* = the box at its last
  position, enlarged by `search_margin × box size` on each side and clipped to the image;
- the best match (highest ZNCC score, 1 = identical) gives the new position of the box.

ZNCC (zero-normalised cross-correlation, `cv2.TM_CCOEFF_NORMED`) is insensitive to uniform
changes of brightness and contrast.

Sub-pixel (`subpixel=True`): the best match is a whole pixel; a parabola is fitted through the
score of that pixel and its two neighbours, separately in x and in y. The top of each parabola
gives the position to a fraction of a pixel (typically better than 0.1 px).

Template refresh (see plan.md §8.3.1): the template can be replaced by the image of the box in
the current frame, cut at its (sub-pixel) tracked position:
- `refresh_threshold`: when the score of a box drops below this value (but stays above
  `lost_threshold`, otherwise the image is probably not the mark any more);
- `refresh_every`: every N frames (behaviour of the original code, kept for legacy/compare.py).

Plain template: if the image inside a box has no variation at all (completely uniform or
overexposed), ZNCC is undefined (OpenCV then returns 1 everywhere and the box would slide to the
corner of its window). Such a box keeps its previous position and gets the score 0 (lost).
"""

from dataclasses import dataclass

import cv2
import numpy as np

from ptrack.core.video import iter_frames


@dataclass
class Box:
    """A rectangle in pixels: (x, y) = top-left corner, w = width, h = height."""
    x: int
    y: int
    w: int
    h: int


@dataclass
class TrackingResult:
    """Output of `track_boxes`. Index order: [frame, box, ...]."""
    top_left: np.ndarray   # shape (n_frames, n_boxes, 2): x, y of each box's top-left corner (px)
    centres: np.ndarray    # shape (n_frames, n_boxes, 2): cx, cy = top-left + (w/2, h/2) (px)
    scores: np.ndarray     # shape (n_frames, n_boxes): ZNCC score of the match (1.0 on frame 0)
    refreshed: np.ndarray = None  # shape (n_frames, n_boxes): True where the template was refreshed after that frame


def box_texture(gray, box):
    """Standard deviation of the grey levels inside the box (0 = completely plain area).

    A box needs a visible pattern (a dot, speckle…) to be tracked: on a plain or overexposed
    area every position looks the same and the box cannot be found.
    """
    return float(gray[box.y:box.y + box.h, box.x:box.x + box.w].std())


def search_window(x, y, w, h, margin, image_width, image_height):
    """Return (x0, y0, x1, y1) of the search window around a box, clipped to the image.

    The window is the box enlarged by int(margin × w) left/right and int(margin × h) up/down.
    """
    dx = int(margin * w)
    dy = int(margin * h)
    x0 = max(x - dx, 0)
    y0 = max(y - dy, 0)
    x1 = min(x + w + dx, image_width)
    y1 = min(y + h + dy, image_height)
    return x0, y0, x1, y1


def parabola_top(left, centre, right):
    """Position (between -0.5 and 0.5) of the top of the parabola through (-1, left), (0, centre), (1, right).

    offset = (left - right) / (2 × (left - 2 × centre + right)). Returns 0 if the three values do not
    form a peak (curvature not negative).
    """
    denominator = left - 2 * centre + right
    if denominator >= 0:
        return 0.0
    return float(np.clip((left - right) / (2 * denominator), -0.5, 0.5))


def subpixel_offset(result, location):
    """Return (dx, dy), the sub-pixel correction of the peak at `location` = (x, y) in the score map.

    A parabola is fitted separately in x and in y; at the border of the map (no neighbour) the correction is 0.
    """
    x, y = location
    height, width = result.shape
    dx = parabola_top(result[y, x - 1], result[y, x], result[y, x + 1]) if 0 < x < width - 1 else 0.0
    dy = parabola_top(result[y - 1, x], result[y, x], result[y + 1, x]) if 0 < y < height - 1 else 0.0
    return dx, dy


def cut_template(gray, x, y, w, h):
    """Return the w × h image whose top-left corner is at (x, y); x, y may be fractions of a pixel.

    Whole-pixel positions are cut directly; fractional positions are interpolated (bilinear)
    with OpenCV `getRectSubPix`, whose centre is given in pixel coordinates.
    """
    if float(x).is_integer() and float(y).is_integer():
        x, y = int(x), int(y)
        return gray[y:y + h, x:x + w].copy()
    centre = (x + (w - 1) / 2, y + (h - 1) / 2)
    return cv2.getRectSubPix(gray, (w, h), centre)


def track_boxes(video_path, boxes, search_margin, subpixel=False, refresh_threshold=None, lost_threshold=0.0,
                refresh_every=None, progress=None, on_frame=None):
    """Track `boxes` (list of `Box`, defined on frame 0) through every frame of the video.

    `search_margin`: search window size, see `search_window`.
    `subpixel`: refine every match to a fraction of a pixel (see `subpixel_offset`).
    `refresh_threshold`, `lost_threshold`: refresh a box's template when
        lost_threshold <= score < refresh_threshold (None = never refresh on score).
    `refresh_every`: if given, refresh all templates every this many frames (original code; None = never).
    `progress`, if given, is called as progress(frames_done) after each frame.
    `on_frame`, if given, is called as on_frame(frame_index, frame, top_left, scores) after each
    frame (used for the live preview); `top_left` is (n_boxes, 2), `scores` is (n_boxes,).
    Returns a `TrackingResult`.
    """
    top_left = []      # one (n_boxes, 2) array per frame
    scores = []        # one (n_boxes,) array per frame
    refreshed = []     # one (n_boxes,) bool array per frame: template refreshed after this frame
    templates = []

    for frame_index, _, frame in iter_frames(video_path):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        image_height, image_width = gray.shape

        if frame_index == 0:
            # Reference frame: templates are cut from the boxes as drawn.
            for box in boxes:
                if box.x < 0 or box.y < 0 or box.x + box.w > image_width or box.y + box.h > image_height:
                    raise ValueError(f"Box {box} is not entirely inside the {image_width}x{image_height} frame.")
                templates.append(gray[box.y:box.y + box.h, box.x:box.x + box.w].copy())
            top_left.append(np.array([[box.x, box.y] for box in boxes], dtype=float))
            scores.append(np.ones(len(boxes)))
            refreshed.append(np.zeros(len(boxes), dtype=bool))
        else:
            previous = top_left[-1]
            frame_positions = np.zeros((len(boxes), 2))
            frame_scores = np.zeros(len(boxes))
            frame_refreshed = np.zeros(len(boxes), dtype=bool)
            for i, box in enumerate(boxes):
                if templates[i].std() == 0:
                    # plain template: no possible match (see module docstring)
                    frame_positions[i] = previous[i]
                    frame_scores[i] = 0.0
                    continue
                # the search window is placed around the last position, rounded to whole pixels
                x, y = int(round(previous[i, 0])), int(round(previous[i, 1]))
                x0, y0, x1, y1 = search_window(x, y, box.w, box.h, search_margin, image_width, image_height)
                result = cv2.matchTemplate(gray[y0:y1, x0:x1], templates[i], cv2.TM_CCOEFF_NORMED)
                _, best_score, _, best_location = cv2.minMaxLoc(result)
                dx, dy = subpixel_offset(result, best_location) if subpixel else (0.0, 0.0)
                frame_positions[i] = (x0 + best_location[0] + dx, y0 + best_location[1] + dy)
                frame_scores[i] = best_score

                refresh = False
                if refresh_threshold is not None and lost_threshold <= best_score < refresh_threshold:
                    refresh = True
                if refresh_every is not None and frame_index % refresh_every == 0:
                    refresh = True
                if refresh:
                    templates[i] = cut_template(gray, frame_positions[i, 0], frame_positions[i, 1], box.w, box.h)
                    frame_refreshed[i] = True
            top_left.append(frame_positions)
            scores.append(frame_scores)
            refreshed.append(frame_refreshed)

        if on_frame is not None:
            on_frame(frame_index, frame, top_left[-1], scores[-1])
        if progress is not None:
            progress(frame_index + 1)

    if not top_left:
        raise ValueError(f"The video contains no readable frame: {video_path}")

    top_left = np.array(top_left)
    half_sizes = np.array([[box.w / 2, box.h / 2] for box in boxes])
    return TrackingResult(top_left=top_left, centres=top_left + half_sizes, scores=np.array(scores),
                          refreshed=np.array(refreshed))
