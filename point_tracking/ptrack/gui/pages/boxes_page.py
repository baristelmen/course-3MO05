"""Step 3 page: define the boxes (ROIs) on the reference frame (frame 0 of the processed video).

Errors (box outside the frame, too small, fewer than 2 boxes) block saving. A box placed on a plain
area (too little texture to be tracked) only gets a warning.

Boxes are added with "Add box" (default size from settings.toml, centred in the frame) and edited
by typing x, y (top-left corner), width and height in video pixels. Deleting a box renumbers the
others. The boxes are stored in project.json only when "Save boxes" is pressed.
"""

import cv2
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ptrack.core import project
from ptrack.core.tracking import Box, box_texture
from ptrack.core.video import read_first_frame
from ptrack.gui.widgets.frame_view import FrameView


class BoxesPage(QWidget):
    """Box editor: list of boxes, x/y/w/h fields, frame view, validation, save."""

    step_done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.data = None
        self.settings = None
        self.boxes = []            # boxes being edited (not saved yet)
        self.frame_width = 0
        self.frame_height = 0
        self.gray = None           # reference frame in grey levels (for the texture check)

        title = QLabel("3. Define boxes")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        explanation = QLabel("Add at least 2 boxes on the marks to follow. Strain is computed between every "
                             "pair of boxes. Values are in video pixels; (x, y) is the top-left corner.")
        explanation.setWordWrap(True)

        self.box_list = QListWidget()
        self.box_list.currentRowChanged.connect(self.select_box)
        add_button = QPushButton("Add box")
        add_button.clicked.connect(self.add_box)
        self.delete_button = QPushButton("Delete box")
        self.delete_button.clicked.connect(self.delete_box)
        buttons = QHBoxLayout()
        buttons.addWidget(add_button)
        buttons.addWidget(self.delete_button)

        self.spins = {}
        form = QFormLayout()
        for key, label in (("x", "x (left)"), ("y", "y (top)"), ("w", "width"), ("h", "height")):
            spin = QSpinBox()
            spin.setSuffix(" px")
            spin.valueChanged.connect(self.field_changed)
            self.spins[key] = spin
            form.addRow(label + ":", spin)

        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)
        self.problems_label.setStyleSheet("color: #c0392b;")
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #d35400;")
        self.save_button = QPushButton("Save boxes")
        self.save_button.clicked.connect(self.save)
        fit_button = QPushButton("Fit image")

        side = QVBoxLayout()
        side.addWidget(title)
        side.addWidget(explanation)
        side.addWidget(self.box_list)
        side.addLayout(buttons)
        side.addLayout(form)
        side.addWidget(self.problems_label)
        side.addWidget(self.warnings_label)
        side.addStretch()
        side.addWidget(fit_button)
        side.addWidget(self.save_button)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(280)

        self.view = FrameView()
        fit_button.clicked.connect(self.view.fit)
        layout = QHBoxLayout(self)
        layout.addWidget(side_widget)
        layout.addWidget(self.view, stretch=1)

    def show_project(self, root, data, settings=None):
        """Load frame 0 of the processed video and the saved boxes."""
        self.root = root
        self.data = data
        self.settings = settings
        self.boxes = project.get_boxes(data)
        if not data["steps"]["processed"]:
            return
        frame = read_first_frame(root / data["processing"]["file"])
        self.gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.view.set_frame(frame)
        self.frame_width = data["source_video"]["width"]
        self.frame_height = data["source_video"]["height"]
        for key, spin in self.spins.items():
            spin.blockSignals(True)
            spin.setRange(0 if key in ("x", "y") else 1, self.frame_width if key in ("x", "w") else self.frame_height)
            spin.blockSignals(False)
        self.refresh(select=0 if self.boxes else None)

    def refresh(self, select=None):
        """Redraw the list and the boxes, check them. `select`: row to select (None = keep)."""
        row = self.box_list.currentRow() if select is None else select
        self.box_list.blockSignals(True)
        self.box_list.clear()
        for number, box in enumerate(self.boxes, start=1):
            self.box_list.addItem(f"Box {number}:  x={box.x}  y={box.y}  w={box.w}  h={box.h}")
        self.box_list.setCurrentRow(row if row is not None and row < len(self.boxes) else -1)
        self.box_list.blockSignals(False)
        self.select_box(self.box_list.currentRow())

    def select_box(self, row):
        """Show the values of the selected box in the fields."""
        has_box = 0 <= row < len(self.boxes)
        for key, spin in self.spins.items():
            spin.setEnabled(has_box)
            if has_box:
                spin.blockSignals(True)
                spin.setValue(getattr(self.boxes[row], key))
                spin.blockSignals(False)
        self.delete_button.setEnabled(has_box)
        self.view.set_boxes(self.boxes, selected=row if has_box else None)
        self.check()

    def field_changed(self):
        """A field was edited: update the selected box."""
        row = self.box_list.currentRow()
        if not 0 <= row < len(self.boxes):
            return
        box = self.boxes[row]
        box.x, box.y, box.w, box.h = (self.spins[key].value() for key in ("x", "y", "w", "h"))
        self.box_list.item(row).setText(f"Box {row + 1}:  x={box.x}  y={box.y}  w={box.w}  h={box.h}")
        self.view.set_boxes(self.boxes, selected=row)
        self.check()

    def add_box(self):
        """Add a box of the default size, centred in the frame."""
        w = self.settings["roi"]["default_width"]
        h = self.settings["roi"]["default_height"]
        self.boxes.append(Box((self.frame_width - w) // 2, (self.frame_height - h) // 2, w, h))
        self.refresh(select=len(self.boxes) - 1)

    def delete_box(self):
        """Delete the selected box; the others are renumbered."""
        row = self.box_list.currentRow()
        if 0 <= row < len(self.boxes):
            del self.boxes[row]
            self.refresh(select=min(row, len(self.boxes) - 1) if self.boxes else None)

    def check(self):
        """Show the problems (if any) and enable Save only when the boxes are valid; warn about plain boxes."""
        problems = project.check_boxes(self.boxes, self.frame_width, self.frame_height,
                                       self.settings["roi"]["min_size"] if self.settings else 1)
        self.problems_label.setText("\n".join(problems))
        self.save_button.setEnabled(not problems)

        warnings = []
        if self.gray is not None and self.settings is not None:
            for number, box in enumerate(self.boxes, start=1):
                inside = box.x >= 0 and box.y >= 0 and box.x + box.w <= self.frame_width \
                    and box.y + box.h <= self.frame_height
                if inside and box_texture(self.gray, box) < self.settings["roi"]["min_texture"]:
                    warnings.append(f"Box {number} is on a plain area (almost no texture): it will probably "
                                    "not be tracked. Place it on a mark.")
        self.warnings_label.setText("\n".join(warnings))
        return problems

    def save(self):
        """Store the boxes in project.json (results are deleted, after confirmation if they exist)."""
        if self.data["steps"]["tracked"]:
            answer = QMessageBox.question(self, "Save boxes",
                                          "Changing the boxes deletes the existing tracking results.\n\nContinue?")
            if answer != QMessageBox.Yes:
                return
        project.set_boxes(self.root, self.data, self.boxes, self.settings["roi"]["min_size"])
        self.step_done.emit()
