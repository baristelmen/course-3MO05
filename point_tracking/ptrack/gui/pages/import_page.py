"""Step 1 page: choose the source video, copy it into the project, show its information."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QFormLayout, QGroupBox, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ptrack.core import project
from ptrack.gui.progress import ProgressPanel, StepWorker

VIDEO_FILTER = ("Videos (*.mp4 *.MP4 *.mov *.MOV *.m4v *.avi *.AVI *.mkv *.mts *.MTS *.3gp *.wmv *.webm);;"
                "All files (*)")

# (key in project.json "source_video", label shown)
INFO_FIELDS = [
    ("original_filename", "Original file"),
    ("file", "Copied to"),
    ("container", "Container"),
    ("codec", "Codec"),
    ("resolution", "Resolution"),
    ("rotation", "Rotation"),
    ("fps_nominal", "Frame rate (FPS)"),
    ("is_vfr", "Variable frame rate"),
    ("frame_count", "Frames"),
    ("duration_s", "Duration"),
    ("size_bytes", "File size"),
]


def format_info(video, key):
    """Text shown for one field of the video information."""
    if key == "resolution":
        return f"{video['width']} × {video['height']} px"
    if key == "rotation":
        return f"{video['rotation']}°"
    if key == "fps_nominal":
        measured = video.get("fps_measured")
        return f"{video['fps_nominal']:.3f}" + (f"  (measured from the timestamps: {measured:.3f})" if measured else "")
    if key == "is_vfr":
        return "yes (irregular frame timing, handled by the processing)" if video["is_vfr"] else "no"
    if key == "duration_s":
        return f"{video['duration_s']:.2f} s"
    if key == "size_bytes":
        return f"{video['size_bytes'] / 1e6:.1f} MB"
    return str(video[key])


class ImportPage(QWidget):
    """Choose a video file; it is copied to raw/input.<ext> and scanned in a background thread.

    Known limitation (plan.md §14, L1): Cancel cannot interrupt the file copy itself; it takes
    effect when the copy is finished and the video is being read.
    """

    step_done = Signal()
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.data = None
        self.worker = None

        title = QLabel("1. Import video")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        explanation = QLabel("Choose the video of the test (any camera or phone). It is copied into the "
                             "project folder, so the project keeps working if the original file is moved.")
        explanation.setWordWrap(True)
        self.choose_button = QPushButton("Choose video…")
        self.choose_button.clicked.connect(self.choose_video)

        self.info_labels = {}
        info_box = QGroupBox("Video information")
        form = QFormLayout(info_box)
        for key, label in INFO_FIELDS:
            self.info_labels[key] = QLabel()
            form.addRow(label + ":", self.info_labels[key])
        self.no_video_label = QLabel("No video imported yet.")

        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_button.clicked.connect(self.cancel_running)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.no_video_label)
        layout.addWidget(info_box)
        layout.addWidget(self.progress_panel)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.info_box = info_box

    def show_project(self, root, data, settings=None):
        self.root = root
        self.data = data
        self.status_label.clear()
        self.update_info()

    def update_info(self):
        video = self.data["source_video"]
        self.no_video_label.setVisible(video is None)
        self.info_box.setVisible(video is not None)
        if video is not None:
            for key, _ in INFO_FIELDS:
                self.info_labels[key].setText(format_info(video, key))
        self.choose_button.setText("Replace video…" if video is not None else "Choose video…")

    def choose_video(self):
        """Ask for a video file (and confirmation if a video is already imported), then import it."""
        path, _ = QFileDialog.getOpenFileName(self, "Choose the test video", "", VIDEO_FILTER)
        if not path:
            return
        if self.data["source_video"] is not None and not self.confirm_replace():
            return
        self.start_import(path)

    def confirm_replace(self):
        """Ask before replacing the video: everything after step 1 is lost."""
        answer = QMessageBox.question(
            self, "Replace video",
            "Replacing the video resets the project: the processed video, the boxes and the results "
            "will be deleted.\n\nReplace the video?")
        return answer == QMessageBox.Yes

    def start_import(self, path):
        """Run project.import_video in a background thread."""
        root, data = self.root, self.data
        self.worker = StepWorker(lambda report: project.import_video(root, data, path, report))
        self.worker.progress.connect(self.progress_panel.set_progress)
        self.worker.succeeded.connect(self.on_succeeded)
        self.worker.cancelled.connect(lambda: self.on_stopped("Import cancelled. The project is unchanged."))
        self.worker.failed.connect(lambda message: self.on_stopped(f"Import failed: {message}"))
        self.status_label.clear()
        self.choose_button.setEnabled(False)
        self.progress_panel.start("Copying and reading the video…")
        self.busy_changed.emit(True)
        self.worker.start()

    def on_succeeded(self):
        self.end_of_step()
        self.update_info()
        self.status_label.setText("Video imported.")
        self.step_done.emit()

    def on_stopped(self, message):
        self.end_of_step()
        self.status_label.setText(message)

    def end_of_step(self):
        self.worker.wait()
        self.worker = None
        self.progress_panel.stop()
        self.choose_button.setEnabled(True)
        self.busy_changed.emit(False)

    def is_busy(self):
        return self.worker is not None

    def cancel_running(self):
        """Stop the import and wait for the thread to finish (temporary files are removed)."""
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait()
