"""Step 4 page: show the saved boxes with their numbers; Accept, or go back to edit them."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ptrack.core import project
from ptrack.core.video import read_first_frame
from ptrack.gui.widgets.frame_view import FrameView


class VerifyPage(QWidget):
    """Reference frame with every box and its number. Accept → step done; Back → box editor."""

    step_done = Signal()
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.data = None

        title = QLabel("4. Verify boxes")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        explanation = QLabel("Check that every box is on a mark and that the numbering is the one you want. "
                             "Tracking starts after you accept.")
        explanation.setWordWrap(True)
        self.summary_label = QLabel()
        back_button = QPushButton("Back: edit boxes")
        back_button.clicked.connect(self.back_requested)
        self.accept_button = QPushButton("Accept boxes")
        self.accept_button.clicked.connect(self.accept)
        fit_button = QPushButton("Fit image")

        self.view = FrameView()
        fit_button.clicked.connect(self.view.fit)

        top = QVBoxLayout()
        top.addWidget(title)
        top.addWidget(explanation)
        top.addWidget(self.summary_label)
        buttons = QHBoxLayout()
        buttons.addWidget(fit_button)
        buttons.addStretch()
        buttons.addWidget(back_button)
        buttons.addWidget(self.accept_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.view, stretch=1)
        layout.addLayout(buttons)

    def show_project(self, root, data, settings=None):
        self.root = root
        self.data = data
        boxes = project.get_boxes(data)
        if not data["steps"]["processed"] or len(boxes) < 2:
            return
        self.view.set_frame(read_first_frame(root / data["processing"]["file"]))
        self.view.set_boxes(boxes)
        n_pairs = len(boxes) * (len(boxes) - 1) // 2
        state = "accepted" if data["steps"]["rois_verified"] else "not accepted yet"
        self.summary_label.setText(f"{len(boxes)} boxes → {n_pairs} strain pairs ({state}).")

    def accept(self):
        project.verify_boxes(self.root, self.data)
        self.step_done.emit()
