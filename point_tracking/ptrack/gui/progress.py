"""Running a long step (import, process, track) in a background thread, with progress and cancel.

- `StepWorker` runs `function(report_progress)` in its own thread, so the window stays responsive.
  The core functions already accept a `progress(done, total)` callback: the worker gives them
  `report_progress`, which forwards the numbers to the GUI and, when the user pressed Cancel,
  raises `StepCancelled`. The core functions then delete their temporary files and leave the
  project unchanged.
- `ProgressPanel` is the progress bar + Cancel button shown on the pages.
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget


class StepCancelled(Exception):
    """Raised inside the worker thread to stop a step the user cancelled."""


class StepWorker(QThread):
    """Run `function(report_progress)` in a background thread.

    Signals (received in the GUI thread):
        progress(done, total)   total = 0 when unknown
        succeeded()
        cancelled()
        failed(message)
    """

    progress = Signal(int, int)
    succeeded = Signal()
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function
        self.cancel_requested = False

    def report_progress(self, done, total=0):
        """Called by the core function (in the worker thread) after each frame."""
        if self.cancel_requested:
            raise StepCancelled()
        self.progress.emit(done, total or 0)

    def cancel(self):
        """Ask the step to stop at the next frame."""
        self.cancel_requested = True

    def run(self):
        try:
            self.function(self.report_progress)
        except StepCancelled:
            self.cancelled.emit()
            return
        except Exception as error:              # shown to the user, the project is unchanged
            self.failed.emit(str(error))
            return
        self.succeeded.emit()


class ProgressPanel(QWidget):
    """A text, a progress bar and a Cancel button. Hidden when no step is running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel()
        self.bar = QProgressBar()
        self.cancel_button = QPushButton("Cancel")
        row = QHBoxLayout()
        row.addWidget(self.bar)
        row.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addLayout(row)
        self.hide()

    def start(self, text):
        self.label.setText(text)
        self.bar.setRange(0, 0)          # "busy" animation until the first progress value
        self.cancel_button.setEnabled(True)
        self.show()

    def set_progress(self, done, total):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(min(done, total))
            self.bar.setFormat(f"frame {done} / {total}")
        else:
            self.bar.setRange(0, 0)

    def stop(self):
        self.hide()
