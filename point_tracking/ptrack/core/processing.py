"""Convert a video to a target frame rate (same resolution) → processed video.

Method: target times t_k = t_0 + k / target_fps (t_0 = time of the first source frame),
k = 0, 1, … while t_k ≤ time of the last source frame. For each t_k the source frame with
the nearest real timestamp is written. The processed video therefore has an exact,
constant frame rate even when the source has irregular timing (dropped frames, VFR).
"""

from dataclasses import dataclass

import numpy as np

from ptrack.core.video import VideoWriter, iter_frames, read_frame_times


@dataclass
class ProcessedFrame:
    """Where a frame of the processed video comes from."""
    processed_frame: int   # index in the processed video (0 = reference frame)
    source_frame: int      # index of the same image in the source video
    source_time_s: float   # timestamp of that image in the source video


def source_frame_rate(fps_nominal, fps_measured=0.0):
    """Frame rate of the source used to check the target FPS.

    Normally the rate announced in the file header (`fps_nominal`). If that value is missing or
    implausible (0, or more than twice the rate measured from the real timestamps), the measured
    rate (`fps_measured`, 0 = unknown) is used instead.
    """
    if fps_measured > 0 and (fps_nominal <= 0 or fps_nominal > 2 * fps_measured):
        return fps_measured
    return fps_nominal


def check_target_fps(target_fps, source_fps):
    """Raise ValueError with a readable message if `target_fps` is not allowed.

    Rules: whole number, at least 1, not higher than the source frame rate.
    The source rate is rounded first, so a "30 fps" phone video (29.97 in the file) accepts 30.
    """
    if isinstance(target_fps, bool) or not isinstance(target_fps, int):
        raise ValueError(f"The target FPS must be a whole number (got {target_fps!r}).")
    if target_fps < 1:
        raise ValueError(f"The target FPS must be at least 1 (got {target_fps}).")
    if target_fps > round(source_fps):
        raise ValueError(f"The target FPS ({target_fps}) is higher than the video's FPS ({source_fps:.2f}).")


def select_frames(source_times, target_fps):
    """Return the source frame index to use for each processed frame.

    `source_times`: timestamps of all source frames (seconds, increasing).
    The result is a list; element k is the index of the source frame nearest to t_k.
    If the source has a gap longer than 1 / target_fps, the same source frame can appear twice.
    """
    source_times = np.asarray(source_times, dtype=float)
    t0 = source_times[0]
    count = int(np.floor((source_times[-1] - t0) * target_fps + 1e-9)) + 1
    selected = []
    for k in range(count):
        target_time = t0 + k / target_fps
        # first source frame at or after target_time, then keep whichever neighbour is closer
        after = int(np.searchsorted(source_times, target_time))
        after = min(after, len(source_times) - 1)
        before = max(after - 1, 0)
        if abs(source_times[before] - target_time) <= abs(source_times[after] - target_time):
            selected.append(before)
        else:
            selected.append(after)
    return selected


def process_video(source_path, output_path, target_fps, crf, source_fps, progress=None):
    """Write the processed video and return the list of `ProcessedFrame`.

    `source_fps` is the frame rate announced by the source (used only to check `target_fps`).
    `progress`, if given, is called as progress(frames_done, frames_total) during writing, and as
    progress(0, 0) ("busy", total unknown) while the timestamps are read, so a cancel request is
    also noticed during that first pass.
    Two passes over the source: one to read all timestamps, one to write the selected frames.
    """
    check_target_fps(target_fps, source_fps)

    def scan_progress(done, expected):
        if progress is not None:
            progress(0, 0)

    source_times, width, height = read_frame_times(source_path, scan_progress)
    selected = select_frames(source_times, target_fps)

    processed_frames = []
    next_k = 0  # next processed frame to write
    with VideoWriter(output_path, width, height, target_fps, crf) as writer:
        for source_index, _, frame in iter_frames(source_path):
            # write this source frame for every processed frame that selected it (usually 0 or 1 times)
            while next_k < len(selected) and selected[next_k] == source_index:
                writer.write(frame)
                processed_frames.append(ProcessedFrame(next_k, source_index, float(source_times[source_index])))
                next_k += 1
                if progress is not None:
                    progress(next_k, len(selected))
            if next_k == len(selected):
                break

    if next_k != len(selected):
        raise RuntimeError(f"Only {next_k} of {len(selected)} frames could be written "
                           "(the video was read differently in the two passes).")
    return processed_frames
