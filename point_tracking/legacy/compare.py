"""Compare the original tracking function with the new ptrack tracker on the same video and boxes.

Run from the point_tracking folder:
    python legacy/compare.py [video] [--box x,y,w,h ...]

Defaults: examples/tracking/output.mp4 (video processed by the original code) and three 40x40 boxes
placed at the top-left corners found in the first row of legacy/output.mp4_tracking.csv.
Both trackers use search margin 1 and a template refresh every 50 frames, as in the original code.

The original functions open OpenCV windows and import matplotlib; these are replaced by
do-nothing stand-ins so the original tracking loop can run unchanged in the headless environment.
"""

import argparse
import sys
import types
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # to import ptrack
sys.path.insert(0, str(HERE))                 # to import the legacy module

from ptrack.core.tracking import Box, track_boxes  # noqa: E402

# Stand-ins for what the legacy module needs but is not used by tracking_ROIs.
cv2.imshow = lambda *args, **kwargs: None
cv2.waitKey = lambda *args, **kwargs: -1
cv2.destroyAllWindows = lambda *args, **kwargs: None
matplotlib_stub = types.ModuleType("matplotlib")
matplotlib_stub.pyplot = types.ModuleType("matplotlib.pyplot")
sys.modules.setdefault("matplotlib", matplotlib_stub)
sys.modules.setdefault("matplotlib.pyplot", matplotlib_stub.pyplot)

import function_Tracking_video as legacy  # noqa: E402

DEFAULT_VIDEO = HERE.parent.parent / "examples" / "tracking" / "output.mp4"
DEFAULT_BOXES = ["547,164,40,40", "546,326,40,40", "541,485,40,40"]
REFRESH_EVERY = 50
SEARCH_MARGIN = 1.0


def run_legacy(video_path, boxes):
    """Run the original `tracking_ROIs` and return the top-left corners, shape (n_frames, n_boxes, 2)."""
    video = cv2.VideoCapture(str(video_path))
    frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    _, first = video.read()
    gray_ref = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    positions_ref = np.array([[b.x, b.y, b.w, b.h] for b in boxes], dtype=int)
    new_position, _ = legacy.tracking_ROIs(video, gray_ref, positions_ref, np.arange(frame_count),
                                           SEARCH_MARGIN, REFRESH_EVERY, show_each_index=10**9)
    video.release()
    columns = [[4 * i, 4 * i + 1] for i in range(len(boxes))]
    return np.stack([new_position[:, c] for c in columns], axis=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", nargs="?", default=str(DEFAULT_VIDEO))
    parser.add_argument("--box", action="append", help="x,y,w,h (repeat); default: three 40x40 boxes")
    args = parser.parse_args()
    boxes = [Box(*(int(v) for v in text.split(","))) for text in (args.box or DEFAULT_BOXES)]

    print("Running the original code ...", flush=True)
    old = run_legacy(args.video, boxes)
    print("\nRunning ptrack ...")
    new = track_boxes(args.video, boxes, SEARCH_MARGIN, refresh_every=REFRESH_EVERY).top_left

    print(f"\nFrames: original {old.shape[0]}, ptrack {new.shape[0]}")
    n = min(old.shape[0], new.shape[0])
    difference = np.abs(old[:n] - new[:n])
    print("Box | max |dx| | max |dy| | frames that differ")
    for i in range(len(boxes)):
        differing = int(np.any(difference[:, i] > 0, axis=1).sum())
        print(f"{i + 1:>3} | {difference[:, i, 0].max():8.0f} | {difference[:, i, 1].max():8.0f} | {differing}")
    print("Result:", "IDENTICAL" if difference.max() == 0 else f"max difference {difference.max():.0f} px")


if __name__ == "__main__":
    main()
