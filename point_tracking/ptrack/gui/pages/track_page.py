"""Step 5 page: track the boxes through the processed video, with a live preview.

Tracking starts automatically after the boxes are accepted and always runs until the last frame
(no Stop button). Then results/tracking.mp4 is written. Quitting the application during this step
asks for confirmation and discards the step.
"""

import cv2
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ptrack.core import project
from ptrack.core.results import draw_boxes
from ptrack.gui.progress import ProgressPanel, StepWorker
from ptrack.gui.widgets.frame_view import FrameView

PREVIEW_MAX_WIDTH = 960      # the preview image is reduced to this width (faster to display)


class TrackPage(QWidget):
    """Run project.track in the background and show every N-th frame with the tracked boxes."""

    step_done = Signal()
    busy_changed = Signal(bool)
    preview_ready = Signal(object, object)   # (image with boxes drawn, scores) — emitted from the worker thread
    stage_changed = Signal(str)              # emitted from the worker thread

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.data = None
        self.settings = None
        self.worker = None

        title = QLabel("5. Track")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        explanation = QLabel("Each box is searched in every frame of the processed video. Green = found, "
                             "red = possibly lost (low score). Tracking runs until the last frame.")
        explanation.setWordWrap(True)
        self.state_label = QLabel()
        self.run_button = QPushButton("Run tracking")
        self.run_button.clicked.connect(self.start_tracking)
        self.scores_label = QLabel()
        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_button.hide()          # no Stop button for tracking
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.view = FrameView()

        top = QHBoxLayout()
        top.addWidget(self.state_label, stretch=1)
        top.addWidget(self.run_button)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addLayout(top)
        layout.addWidget(self.view, stretch=1)
        layout.addWidget(self.scores_label)
        layout.addWidget(self.progress_panel)
        layout.addWidget(self.status_label)

        self.preview_ready.connect(self.show_preview)
        self.stage_changed.connect(self.show_stage)

    def show_project(self, root, data, settings=None):
        self.root = root
        self.data = data
        self.settings = settings
        if self.worker is None:
            self.status_label.clear()
        if data["steps"]["tracked"]:
            self.state_label.setText("Tracking done. Results are in results/. Run again to overwrite them.")
        else:
            self.state_label.setText("Not tracked yet.")
        self.run_button.setEnabled(data["steps"]["rois_verified"] and self.worker is None)

    def start_tracking(self):
        """Start tracking in the background (asks first if results already exist)."""
        if self.worker is not None or not self.data["steps"]["rois_verified"]:
            return
        if self.data["steps"]["tracked"]:
            answer = QMessageBox.question(self, "Run tracking",
                                          "Tracking again overwrites the existing results.\n\nContinue?")
            if answer != QMessageBox.Yes:
                return

        root, data, settings = self.root, self.data, self.settings
        total = data["processing"]["frame_count"]
        every_n = max(1, settings["preview"]["update_every_n_frames"])
        boxes = project.get_boxes(data)
        lost_threshold = settings["tracker"]["lost_threshold"]
        current_stage = {"name": None}

        def on_frame(index, frame, top_left, scores):
            """Worker thread: send every N-th frame (and the last one) to the preview."""
            if index % every_n == 0 or index == total - 1:
                image = frame.copy()
                draw_boxes(image, top_left, boxes, scores, lost_threshold)
                if image.shape[1] > PREVIEW_MAX_WIDTH:
                    factor = PREVIEW_MAX_WIDTH / image.shape[1]
                    image = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
                self.preview_ready.emit(image, scores.copy())

        def run(report):
            def progress(stage, done):
                if stage != current_stage["name"]:
                    current_stage["name"] = stage
                    self.stage_changed.emit(stage)
                if stage == "scan":
                    report(0, 0)            # "busy" bar: the number of source frames is not the total here
                else:
                    report(done, total)
            project.track(root, data, settings, progress=progress, on_frame=on_frame)

        self.worker = StepWorker(run)
        self.worker.progress.connect(self.progress_panel.set_progress)
        self.worker.succeeded.connect(self.on_succeeded)
        self.worker.cancelled.connect(lambda: self.on_stopped("Tracking cancelled. The project is unchanged."))
        self.worker.failed.connect(lambda message: self.on_stopped(f"Tracking failed: {message}"))
        self.status_label.clear()
        self.state_label.setText("Tracking in progress…")
        self.run_button.setEnabled(False)
        self.progress_panel.start("Tracking…")
        self.busy_changed.emit(True)
        self.worker.start()

    def show_stage(self, stage):
        texts = {"scan": "Reading the timestamps of the source video…", "tracking": "Tracking the boxes…",
                 "video": "Writing results/tracking.mp4…"}
        self.progress_panel.label.setText(texts.get(stage, stage))

    def show_preview(self, image, scores):
        """GUI thread: display a preview frame and the current scores."""
        self.view.update_frame(image)
        self.scores_label.setText("Scores:  " + "   ".join(f"box {i + 1}: {s:.3f}" for i, s in enumerate(scores)))

    def on_succeeded(self):
        self.end_of_step()
        self.status_label.setText("Tracking done.")
        self.step_done.emit()

    def on_stopped(self, message):
        self.end_of_step()
        self.status_label.setText(message)

    def end_of_step(self):
        self.worker.wait()
        self.worker = None
        self.progress_panel.stop()
        self.busy_changed.emit(False)
        self.show_project(self.root, self.data, self.settings)

    def is_busy(self):
        return self.worker is not None

    def cancel_running(self):
        """Used only when the application is closed during tracking: stop and wait."""
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait()

