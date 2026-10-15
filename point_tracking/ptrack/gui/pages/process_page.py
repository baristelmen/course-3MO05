"""Step 2 page: choose the target FPS and write processed/processed.mp4."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ptrack.core import project
from ptrack.core.processing import check_target_fps, source_frame_rate
from ptrack.gui.progress import ProgressPanel, StepWorker


class ProcessPage(QWidget):
    """Target FPS input (whole number), validation against the source FPS, processing in the background."""

    step_done = Signal()
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.data = None
        self.settings = None
        self.worker = None

        title = QLabel("2. Process to target FPS")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        explanation = QLabel("The video is converted to a constant frame rate (same resolution). Fewer frames per "
                             "second make a smaller file and a faster tracking.")
        explanation.setWordWrap(True)

        self.source_label = QLabel()
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 1000)
        self.fps_spin.setSuffix(" FPS")
        self.fps_spin.valueChanged.connect(self.check_fps)
        self.fps_error_label = QLabel()
        self.fps_error_label.setStyleSheet("color: #c0392b;")
        self.process_button = QPushButton("Process")
        self.process_button.clicked.connect(self.start_processing)

        fps_row = QHBoxLayout()
        fps_row.addWidget(self.fps_spin)
        fps_row.addWidget(self.process_button)
        fps_row.addStretch()
        form = QFormLayout()
        form.addRow("Source video:", self.source_label)
        form.addRow("Target frame rate:", fps_row)
        form.addRow("", self.fps_error_label)

        self.result_box = QGroupBox("Processed video")
        result_form = QFormLayout(self.result_box)
        self.result_labels = {key: QLabel() for key in ("file", "fps", "frames", "size")}
        result_form.addRow("File:", self.result_labels["file"])
        result_form.addRow("Frame rate:", self.result_labels["fps"])
        result_form.addRow("Frames:", self.result_labels["frames"])
        result_form.addRow("File size:", self.result_labels["size"])

        self.progress_panel = ProgressPanel()
        self.progress_panel.cancel_button.clicked.connect(self.cancel_running)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addLayout(form)
        layout.addWidget(self.result_box)
        layout.addWidget(self.progress_panel)
        layout.addWidget(self.status_label)
        layout.addStretch()

    def show_project(self, root, data, settings=None):
        self.root = root
        self.data = data
        self.settings = settings
        self.status_label.clear()
        source = data["source_video"]
        if source is not None:
            self.source_label.setText(f"{source['fps_nominal']:.3f} FPS, {source['frame_count']} frames, "
                                      f"{source['duration_s']:.2f} s")
        processing = data["processing"]
        if processing is not None:
            self.fps_spin.setValue(processing["target_fps"])
        elif settings is not None:
            self.fps_spin.setValue(settings["processing"]["default_target_fps"])
        self.update_result()
        self.check_fps()

    def update_result(self):
        processing = self.data["processing"]
        self.result_box.setVisible(processing is not None)
        if processing is not None:
            size = (self.root / processing["file"]).stat().st_size if (self.root / processing["file"]).exists() else 0
            self.result_labels["file"].setText(processing["file"])
            self.result_labels["fps"].setText(f"{processing['target_fps']} FPS (H.264, CRF {processing['crf']})")
            self.result_labels["frames"].setText(str(processing["frame_count"]))
            self.result_labels["size"].setText(f"{size / 1e6:.1f} MB")

    def check_fps(self):
        """Show an error and disable Process when the target FPS is not allowed (GUI stays usable)."""
        source = self.data["source_video"] if self.data else None
        if source is None:
            self.process_button.setEnabled(False)
            return
        try:
            check_target_fps(self.fps_spin.value(),
                             source_frame_rate(source["fps_nominal"], source.get("fps_measured", 0.0)))
        except ValueError as error:
            self.fps_error_label.setText(str(error))
            self.process_button.setEnabled(False)
            return
        self.fps_error_label.clear()
        self.process_button.setEnabled(self.worker is None)

    def confirm_delete_results(self):
        """Processing again deletes the tracking results: ask first."""
        answer = QMessageBox.question(
            self, "Process again",
            "Processing the video again deletes the existing tracking results (the boxes are kept).\n\n"
            "Continue?")
        return answer == QMessageBox.Yes

    def start_processing(self):
        """Run project.process in a background thread."""
        if self.data["steps"]["tracked"] and not self.confirm_delete_results():
            return
        root, data = self.root, self.data
        fps = self.fps_spin.value()
        crf = self.settings["processing"]["crf"]
        self.worker = StepWorker(lambda report: project.process(root, data, fps, crf, report))
        self.worker.progress.connect(self.progress_panel.set_progress)
        self.worker.succeeded.connect(self.on_succeeded)
        self.worker.cancelled.connect(lambda: self.on_stopped("Processing cancelled. The project is unchanged."))
        self.worker.failed.connect(lambda message: self.on_stopped(f"Processing failed: {message}"))
        self.status_label.clear()
        self.process_button.setEnabled(False)
        self.fps_spin.setEnabled(False)
        self.progress_panel.start(f"Reading the video, then writing the processed video at {fps} FPS…")
        self.busy_changed.emit(True)
        self.worker.start()

    def on_succeeded(self):
        self.end_of_step()
        self.update_result()
        self.status_label.setText("Processing done.")
        self.step_done.emit()

    def on_stopped(self, message):
        self.end_of_step()
        self.status_label.setText(message)

    def end_of_step(self):
        self.worker.wait()
        self.worker = None
        self.progress_panel.stop()
        self.fps_spin.setEnabled(True)
        self.busy_changed.emit(False)
        self.check_fps()

    def is_busy(self):
        return self.worker is not None

    def cancel_running(self):
        """Stop the processing and wait for the thread to finish (the temporary file is removed)."""
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait()
