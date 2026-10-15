"""Reading videos with OpenCV, writing videos with ffmpeg.

- `read_video_info` scans a video once and returns its metadata (`VideoInfo`).
- `read_frame_times` returns the timestamp of every frame.
- `iter_frames` yields every frame with its real timestamp; `read_first_frame` / `read_frame` return one frame.
- `VideoWriter` writes frames to an H.264 .mp4 file through the ffmpeg program shipped with imageio-ffmpeg.

OpenCV applies the rotation stored in the file (e.g. portrait iPhone videos), so frames
and sizes are always upright. Timestamps come from the file itself (`CAP_PROP_POS_MSEC`),
not from `index / fps`, so videos with irregular frame timing are handled correctly.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    """Metadata of a video file. Sizes are after rotation (as the frames are displayed)."""
    file_name: str
    container: str        # file extension, e.g. "mp4", "mov"
    codec: str            # FourCC code, e.g. "avc1", "hvc1"
    width: int            # px
    height: int           # px
    rotation: int         # degrees stored in the file (already applied to the frames)
    fps_nominal: float    # frame rate announced in the file header
    fps_measured: float   # 1 / typical time between two frames (from the real timestamps)
    frame_count: int      # frames actually decoded
    duration_s: float     # from first frame to the end of the last frame
    is_vfr: bool          # True if the time between frames is not constant (variable frame rate / dropped frames)
    size_bytes: int


def open_video(path):
    """Open a video with OpenCV and return the `cv2.VideoCapture`. Raises ValueError if it cannot be read."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open the video file: {path}")
    return capture


def read_frame_times(path, progress=None):
    """Go through the whole video and return (times_s, width, height).

    `times_s` is a numpy array with the timestamp (seconds) of every frame, in order.
    `width`, `height` are the real (rotated) frame size, taken from the first frame.
    `progress`, if given, is called as progress(frames_done, frames_expected).
    """
    capture = open_video(path)
    try:
        frames_expected = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, first_frame = capture.read()
        if not ok:
            raise ValueError(f"The video contains no readable frame: {path}")
        height, width = first_frame.shape[:2]
        times_ms = [capture.get(cv2.CAP_PROP_POS_MSEC)]

        # grab() moves to the next frame without converting it to an image: faster than read().
        while capture.grab():
            times_ms.append(capture.get(cv2.CAP_PROP_POS_MSEC))
            if progress is not None:
                progress(len(times_ms), frames_expected)
    finally:
        capture.release()
    return np.array(times_ms) / 1000.0, width, height


def read_video_info(path, progress=None):
    """Scan the whole video once and return its `VideoInfo`.

    The frame count and timing are measured by going through every frame, because the
    values written in the file header are often approximate for phone videos.
    `progress`, if given, is called as progress(frames_done, frames_expected).
    """
    path = Path(path)
    capture = open_video(path)
    fps_nominal = capture.get(cv2.CAP_PROP_FPS)
    rotation = int(capture.get(cv2.CAP_PROP_ORIENTATION_META))
    codec = _fourcc_to_text(capture.get(cv2.CAP_PROP_FOURCC))
    capture.release()

    times_s, width, height = read_frame_times(path, progress)
    intervals = np.diff(times_s)
    if len(intervals) > 0:
        typical_interval = float(np.median(intervals))
        # More than 10 % away from the typical interval anywhere → not a constant frame rate.
        is_vfr = bool(np.any(np.abs(intervals - typical_interval) > 0.1 * typical_interval))
    else:
        typical_interval = 1.0 / fps_nominal if fps_nominal > 0 else 0.0
        is_vfr = False

    return VideoInfo(
        file_name=path.name,
        container=path.suffix.lstrip(".").lower(),
        codec=codec,
        width=width,
        height=height,
        rotation=rotation,
        fps_nominal=fps_nominal,
        fps_measured=1.0 / typical_interval if typical_interval > 0 else 0.0,
        frame_count=len(times_s),
        duration_s=float(times_s[-1] - times_s[0] + typical_interval),
        is_vfr=is_vfr,
        size_bytes=path.stat().st_size,
    )


def iter_frames(path):
    """Yield (index, time_s, frame) for every frame of the video, in order.

    `time_s` is the timestamp stored in the file, in seconds.
    `frame` is an upright BGR image (numpy array, shape height × width × 3, uint8).
    """
    capture = open_video(path)
    try:
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield index, capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0, frame
            index += 1
    finally:
        capture.release()


def read_frame(path, index):
    """Return frame number `index` of a video (upright BGR image). Raises ValueError if it cannot be read.

    Uses OpenCV seeking, which is exact for the videos written by this application.
    """
    capture = open_video(path)
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise ValueError(f"Frame {index} cannot be read from {path}")
    return frame


def read_first_frame(path):
    """Return the first frame of a video (upright BGR image). Raises ValueError if there is none."""
    capture = open_video(path)
    try:
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise ValueError(f"The video contains no readable frame: {path}")
    return frame


class VideoWriter:
    """Write BGR frames to an H.264 .mp4 file at a constant frame rate.

    Frames are sent as raw pixels to an ffmpeg process (ffmpeg from imageio-ffmpeg, encoder libx264).
    Usage:
        with VideoWriter("out.mp4", width, height, fps=5, crf=18) as writer:
            writer.write(frame)

    H.264 (yuv420p) needs an even width and height. If the size is odd, ffmpeg adds one
    black pixel column/row on the right/bottom; the existing pixels keep their coordinates.
    """

    def __init__(self, path, width, height, fps, crf):
        self.path = Path(path)
        self.width = width
        self.height = height
        if width % 2 or height % 2:
            logger.warning("Odd frame size %dx%d: one black pixel row/column is added.", width, height)
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error",
            # input: raw BGR frames from this program (stdin)
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            # output: H.264, constant frame rate, standard pixel format playable everywhere
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(self.path),
        ]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, frame):
        """Add one frame (BGR uint8 array of shape height × width × 3)."""
        if frame.shape != (self.height, self.width, 3):
            raise ValueError(f"Frame shape {frame.shape} does not match {self.height}x{self.width}x3.")
        try:
            self.process.stdin.write(frame.tobytes())
        except BrokenPipeError:
            self.close()  # raises with ffmpeg's error message

    def close(self):
        """Finish the file. Raises RuntimeError if ffmpeg reported an error."""
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        error_output = self.process.stderr.read().decode(errors="replace")
        self.process.stderr.close()
        if self.process.wait() != 0:
            raise RuntimeError(f"ffmpeg could not write {self.path}: {error_output.strip()}")

    def cancel(self):
        """Stop ffmpeg and delete the unfinished file."""
        self.process.kill()
        self.process.wait()
        self.path.unlink(missing_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.close()
        else:
            self.cancel()


def _fourcc_to_text(value):
    """Convert OpenCV's numeric FourCC (e.g. 828601953.0) to text (e.g. "avc1")."""
    code = int(value)
    characters = [chr((code >> (8 * i)) & 0xFF) for i in range(4)]
    return "".join(c for c in characters if c.isprintable()).strip()
