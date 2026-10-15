"""Overview page: project name, folder, description and the state of each step."""

from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ptrack.core import project

STEP_NAMES = {
    "imported": "1. Import video",
    "processed": "2. Process to target FPS",
    "rois_verified": "3–4. Define and verify boxes",
    "tracked": "5. Track",
}


class OverviewPage(QWidget):
    """First page of an open project. `show_project(root, data, settings)` fills the page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.data = None

        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setFixedHeight(80)
        self.save_description_button = QPushButton("Save description")
        self.save_description_button.clicked.connect(self.save_description)
        description_box = QGroupBox("Description")
        description_layout = QVBoxLayout(description_box)
        description_layout.addWidget(self.description_edit)
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self.save_description_button)
        description_layout.addLayout(save_row)

        self.steps_label = QLabel()
        steps_box = QGroupBox("Steps")
        QVBoxLayout(steps_box).addWidget(self.steps_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.addWidget(self.name_label)
        layout.addWidget(self.folder_label)
        layout.addWidget(description_box)
        layout.addWidget(steps_box)
        layout.addStretch()

    def show_project(self, root, data, settings=None):
        """Display a project."""
        self.root = root
        self.data = data
        self.name_label.setText(data["project"]["name"])
        self.folder_label.setText(f"Folder: {root}")
        self.description_edit.setPlainText(data["project"]["description"])
        self.update_steps()

    def update_steps(self):
        """Show a tick for each completed step and the next step to do."""
        lines = []
        for step in project.STEPS:
            mark = "✔" if self.data["steps"][step] else "○"
            lines.append(f"{mark}  {STEP_NAMES[step]}")
        next_step = project.next_step(self.data)
        lines.append("")
        lines.append("Next step: " + (STEP_NAMES[next_step] if next_step else "all steps done"))
        self.steps_label.setText("\n".join(lines))

    def save_description(self):
        """Save the description text into project.json."""
        try:
            project.set_description(self.root, self.data, self.description_edit.toPlainText())
        except OSError as error:
            QMessageBox.warning(self, "Save description", f"Could not save the description:\n{error}")
