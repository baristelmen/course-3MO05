"""Command-line entry used to try the core functions before the GUI exists.

Run from the point_tracking folder:
    python -m ptrack.cli info <video>
    python -m ptrack.cli process <video> --fps 5 --out processed.mp4
    python -m ptrack.cli track <processed video> --box 540,160,40,40 --box 540,480,40,40
    python -m ptrack.cli run <video> --fps 5 --box 540,160,40,40 --box 540,480,40,40 --out-dir <folder>

Project commands (one per wizard step):
    python -m ptrack.cli project-new <parent folder> "<name>" [--description "..."]
    python -m ptrack.cli project-import <project> <video>
    python -m ptrack.cli project-process <project> [--fps 5]
    python -m ptrack.cli project-boxes <project> --box x,y,w,h --box x,y,w,h   (sets and verifies the boxes)
    python -m ptrack.cli project-track <project>
    python -m ptrack.cli project-status <project>
    python -m ptrack.cli project-run <project>       (redo processing + tracking from project.json alone)
"""

import argparse
import time
from pathlib import Path

from ptrack.core import project
from ptrack.core.analysis import box_quality, pair_strains
from ptrack.core.processing import process_video, source_frame_rate
from ptrack.core.results import write_results_csv, write_tracking_video
from ptrack.core.settings import load_settings
from ptrack.core.tracking import Box, track_boxes
from ptrack.core.video import read_video_info


def command_info(args):
    """Print the metadata of a video."""
    info = read_video_info(args.video)
    print(f"File          : {info.file_name}")
    print(f"Container     : {info.container}")
    print(f"Codec         : {info.codec}")
    print(f"Resolution    : {info.width} x {info.height} px")
    print(f"Rotation      : {info.rotation} deg")
    print(f"Nominal FPS   : {info.fps_nominal:.3f}")
    print(f"Measured FPS  : {info.fps_measured:.3f}")
    print(f"Variable FPS  : {'yes' if info.is_vfr else 'no'}")
    print(f"Frames        : {info.frame_count}")
    print(f"Duration      : {info.duration_s:.3f} s")
    print(f"File size     : {info.size_bytes / 1e6:.1f} MB")


def command_process(args):
    """Convert a video to the target FPS and print where each processed frame comes from."""
    settings = load_settings()
    crf = settings["processing"]["crf"]
    fps = args.fps if args.fps is not None else settings["processing"]["default_target_fps"]
    source = read_video_info(args.video)

    def show_progress(done, total):
        print(f"\rWriting frame {done}/{total}", end="", flush=True)

    start = time.perf_counter()
    frames = process_video(args.video, args.out, fps, crf, source_frame_rate(source.fps_nominal, source.fps_measured),
                           progress=show_progress)
    elapsed = time.perf_counter() - start
    print()

    print(f"Source        : {source.frame_count} frames, {source.fps_nominal:.3f} FPS, {source.width} x {source.height} px")
    print(f"Processed     : {len(frames)} frames at {fps} FPS (CRF {crf}) -> {args.out}")
    print(f"File size     : {Path(args.out).stat().st_size / 1e6:.1f} MB (source {source.size_bytes / 1e6:.1f} MB)")
    print(f"Time          : {elapsed:.1f} s")
    print("First frames  : processed_frame, source_frame, source_time_s")
    for frame in frames[:5]:
        print(f"                {frame.processed_frame:>5d}, {frame.source_frame:>5d}, {frame.source_time_s:.4f}")


def parse_box(text):
    """Convert "x,y,w,h" to a Box (used by argparse)."""
    try:
        x, y, w, h = (int(value) for value in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"box must be x,y,w,h with whole numbers, got {text!r}")
    return Box(x, y, w, h)


def command_track(args):
    """Track the boxes through the video and print a summary per box."""
    settings = load_settings()
    tracker = settings["tracker"]
    margin = tracker["search_margin"]

    def show_progress(done):
        print(f"\rTracking frame {done}", end="", flush=True)

    start = time.perf_counter()
    mode = f"sub-pixel {tracker['subpixel']}, refresh when score < {tracker['refresh_threshold']}"
    result = track_boxes(args.video, args.box, margin, subpixel=tracker["subpixel"],
                         refresh_threshold=tracker["refresh_threshold"],
                         lost_threshold=tracker["lost_threshold"], progress=show_progress)
    elapsed = time.perf_counter() - start
    print()

    n_frames = result.centres.shape[0]
    print(f"Frames tracked: {n_frames} in {elapsed:.1f} s (search margin {margin}, {mode}, "
          f"{int(result.refreshed.sum())} template refreshes)")
    print("Box | start centre (px)  | end centre (px)    | displacement (px) | lowest score (frame)")
    for i in range(len(args.box)):
        cx0, cy0 = result.centres[0, i]
        cx1, cy1 = result.centres[-1, i]
        worst = int(result.scores[:, i].argmin())
        print(f"{i + 1:>3} | {cx0:8.2f} {cy0:8.2f}  | {cx1:8.2f} {cy1:8.2f}  | "
              f"{cx1 - cx0:7.2f} {cy1 - cy0:7.2f}   | {result.scores[worst, i]:.3f} ({worst})")


def command_run(args):
    """Whole pipeline without a project: process → track → results.csv + tracking.mp4 in --out-dir."""
    settings = load_settings()
    crf = settings["processing"]["crf"]
    fps = args.fps if args.fps is not None else settings["processing"]["default_target_fps"]
    margin = settings["tracker"]["search_margin"]
    lost_threshold = settings["tracker"]["lost_threshold"]
    if len(args.box) < 2:
        raise ValueError("At least 2 boxes are needed (strain is measured between pairs of boxes).")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    processed_path = out_dir / "processed.mp4"
    csv_path = out_dir / "results.csv"
    video_path = out_dir / "tracking.mp4"
    source = read_video_info(args.video)

    def show(step):
        """Return a progress function that prints "<step>: frame N[/total]" on one line."""
        def progress(done, total=None):
            text = f"{step}: frame {done}" if total is None else f"{step}: frame {done}/{total}"
            print("\r" + text, end="", flush=True)
        return progress

    start = time.perf_counter()
    frames = process_video(args.video, processed_path, fps, crf,
                           source_frame_rate(source.fps_nominal, source.fps_measured), progress=show("Processing"))
    print()
    tracker = settings["tracker"]
    result = track_boxes(processed_path, args.box, margin, subpixel=tracker["subpixel"],
                         refresh_threshold=tracker["refresh_threshold"], lost_threshold=lost_threshold,
                         progress=show("Tracking"))
    print()
    write_results_csv(csv_path, frames, result)
    write_tracking_video(processed_path, video_path, args.box, result, lost_threshold, fps, crf,
                         progress=show("Tracking video"))
    print()
    elapsed = time.perf_counter() - start

    print(f"Done in {elapsed:.1f} s: {len(frames)} frames at {fps} FPS")
    print(f"  {processed_path}\n  {csv_path}\n  {video_path}")
    print_summary(result, lost_threshold)


def print_summary(result, lost_threshold):
    """Print the lost-box report and the final strain of every pair."""
    print("Box | lowest score (frame) | mean score | frames lost | first lost frame")
    for quality in box_quality(result.scores, lost_threshold):
        first = "-" if quality.first_lost_frame is None else str(quality.first_lost_frame)
        print(f"{quality.box:>3} | {quality.lowest_score:6.3f} ({quality.lowest_frame:>5d})       | "
              f"{quality.mean_score:10.3f} | {quality.lost_frames:11d} | {first}")
    pairs, strains = pair_strains(result.centres)
    print("Pair | final strain")
    for k, (i, j) in enumerate(pairs):
        print(f"{i}-{j}  | {strains[-1, k]: .5f}")


def print_project_progress(stage, done, total=None):
    """Progress function for the project commands."""
    text = f"{stage}: frame {done}" if total is None else f"{stage}: frame {done}/{total}"
    print("\r" + text, end="", flush=True)


def command_project_new(args):
    root, _ = project.create_project(args.parent, args.name, args.description)
    print(f"Project created: {root}")


def command_project_import(args):
    root, data = project.open_project(args.project)
    project.import_video(root, data, args.video,
                         progress=lambda done, total: print_project_progress("Reading", done, total))
    print()
    video = data["source_video"]
    print(f"Imported {video['original_filename']} -> {video['file']} "
          f"({video['width']} x {video['height']} px, {video['frame_count']} frames, {video['fps_nominal']:.3f} FPS)")


def command_project_process(args):
    root, data = project.open_project(args.project)
    settings = load_settings()
    fps = args.fps if args.fps is not None else settings["processing"]["default_target_fps"]
    project.process(root, data, fps, settings["processing"]["crf"],
                    progress=lambda done, total: print_project_progress("Processing", done, total))
    print()
    print(f"Processed: {data['processing']['frame_count']} frames at {fps} FPS -> {data['processing']['file']}")


def command_project_boxes(args):
    root, data = project.open_project(args.project)
    settings = load_settings()
    project.set_boxes(root, data, args.box, settings["roi"]["min_size"])
    project.verify_boxes(root, data)
    for roi in data["rois"]:
        print(f"Box {roi['id']}: x={roi['x']} y={roi['y']} w={roi['w']} h={roi['h']}")


def command_project_track(args):
    root, data = project.open_project(args.project)
    settings = load_settings()
    result = project.track(root, data, settings, progress=print_project_progress)
    print()
    print(f"Results: {data['results']['file']}, {data['results']['tracking_video']}")
    print_summary(result, settings["tracker"]["lost_threshold"])


def command_project_status(args):
    root, data = project.open_project(args.project)
    print(f"Project     : {data['project']['name']}  ({root})")
    print(f"Description : {data['project']['description']}")
    for step in project.STEPS:
        print(f"  [{'x' if data['steps'][step] else ' '}] {step}")
    print(f"Next step   : {project.next_step(data) or 'all done'}")


def command_project_run(args):
    """Redo processing and tracking using only what is stored in project.json."""
    root, data = project.open_project(args.project)
    settings = load_settings()
    boxes = project.get_boxes(data)
    fps = data["processing"]["target_fps"]
    project.process(root, data, fps, settings["processing"]["crf"],
                    progress=lambda done, total: print_project_progress("Processing", done, total))
    print()
    project.set_boxes(root, data, boxes, settings["roi"]["min_size"])
    project.verify_boxes(root, data)
    result = project.track(root, data, settings, progress=print_project_progress)
    print()
    print_summary(result, settings["tracker"]["lost_threshold"])


def main():
    parser = argparse.ArgumentParser(prog="ptrack", description="Point tracking (command line).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser("info", help="show the metadata of a video")
    info_parser.add_argument("video", help="path to the video file")
    info_parser.set_defaults(function=command_info)

    process_parser = subparsers.add_parser("process", help="convert a video to a target FPS")
    process_parser.add_argument("video", help="path to the source video")
    process_parser.add_argument("--fps", type=int, help="target FPS (default: from settings.toml)")
    process_parser.add_argument("--out", required=True, help="path of the processed .mp4 to write")
    process_parser.set_defaults(function=command_process)

    track_parser = subparsers.add_parser("track", help="track boxes through a (processed) video")
    track_parser.add_argument("video", help="path to the video")
    track_parser.add_argument("--box", type=parse_box, action="append", required=True,
                              help="box on frame 0 as x,y,w,h (top-left corner, width, height); repeat for each box")
    track_parser.set_defaults(function=command_track)

    run_parser = subparsers.add_parser("run", help="process + track + write results (no project)")
    run_parser.add_argument("video", help="path to the source video")
    run_parser.add_argument("--fps", type=int, help="target FPS (default: from settings.toml)")
    run_parser.add_argument("--box", type=parse_box, action="append", required=True,
                            help="box on frame 0 as x,y,w,h; repeat for each box (at least 2)")
    run_parser.add_argument("--out-dir", required=True, help="folder for processed.mp4, results.csv, tracking.mp4")
    run_parser.set_defaults(function=command_run)

    new_parser = subparsers.add_parser("project-new", help="create a project")
    new_parser.add_argument("parent", help="folder in which the project folder is created")
    new_parser.add_argument("name", help="project name (spaces become _)")
    new_parser.add_argument("--description", default="", help="free text")
    new_parser.set_defaults(function=command_project_new)

    import_parser = subparsers.add_parser("project-import", help="step 1: copy a video into the project")
    import_parser.add_argument("project", help="project folder")
    import_parser.add_argument("video", help="source video")
    import_parser.set_defaults(function=command_project_import)

    pprocess_parser = subparsers.add_parser("project-process", help="step 2: convert to the target FPS")
    pprocess_parser.add_argument("project", help="project folder")
    pprocess_parser.add_argument("--fps", type=int, help="target FPS (default: from settings.toml)")
    pprocess_parser.set_defaults(function=command_project_process)

    boxes_parser = subparsers.add_parser("project-boxes", help="steps 3-4: set and verify the boxes")
    boxes_parser.add_argument("project", help="project folder")
    boxes_parser.add_argument("--box", type=parse_box, action="append", required=True, help="x,y,w,h (repeat)")
    boxes_parser.set_defaults(function=command_project_boxes)

    ptrack_parser = subparsers.add_parser("project-track", help="step 5: track and write the results")
    ptrack_parser.add_argument("project", help="project folder")
    ptrack_parser.set_defaults(function=command_project_track)

    status_parser = subparsers.add_parser("project-status", help="show the steps done")
    status_parser.add_argument("project", help="project folder")
    status_parser.set_defaults(function=command_project_status)

    prun_parser = subparsers.add_parser("project-run", help="redo processing + tracking from project.json")
    prun_parser.add_argument("project", help="project folder")
    prun_parser.set_defaults(function=command_project_run)

    args = parser.parse_args()
    try:
        args.function(args)
    except ValueError as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
