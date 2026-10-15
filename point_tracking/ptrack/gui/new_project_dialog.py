"""Dialog to create a new project: name, location, description."""

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from ptrack.core import project


class NewProjectDialog(QDialog):
    """Ask for the project name, the parent folder and a description, then create the project.

    The dialog stays open and shows the reason when the project cannot be created
    (invalid name, folder already exists, …). After `exec()` returns accepted,
    `self.root` is the folder of the new project.
    """

    def __init__(self, parent=None, default_location=""):
        super().__init__(parent)
        self.setWindowTitle("New project")
        self.setMinimumWidth(520)
        self.root = None

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Steel group 3")
        self.location_edit = QLineEdit(default_location)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.choose_location)
        location_row = QHBoxLayout()
        location_row.addWidget(self.location_edit)
        location_row.addWidget(browse_button)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Optional: students, group, material, specimen…")
        self.description_edit.setFixedHeight(80)

        self.folder_label = QLabel()     # shows the folder that will be created
        self.folder_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c0392b;")

        form = QFormLayout()
        form.addRow("Project name:", self.name_edit)
        form.addRow("Location:", location_row)
        form.addRow("Description:", self.description_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Create")
        self.buttons.accepted.connect(self.create)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.folder_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)

        self.name_edit.textChanged.connect(self.update_preview)
        self.location_edit.textChanged.connect(self.update_preview)
        self.update_preview()

    def choose_location(self):
        """Open a folder chooser for the parent location."""
        folder = QFileDialog.getExistingDirectory(self, "Choose where to create the project", self.location_edit.text())
        if folder:
            self.location_edit.setText(folder)

    def update_preview(self):
        """Show the folder that will be created, or why the name is not valid. Enable Create only when valid."""
        self.error_label.clear()
        valid = False
        name = self.name_edit.text()
        location = self.location_edit.text().strip()
        if not name.strip():
            self.folder_label.setText("Enter a project name.")
        elif not location:
            self.folder_label.setText("Choose a location.")
        else:
            try:
                folder_name = project.clean_project_name(name)
                self.folder_label.setText(f"Project folder: {Path(location) / folder_name}")
                valid = True
            except ValueError as error:
                self.folder_label.setText("")
                self.error_label.setText(str(error))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(valid)

    def create(self):
        """Create the project; on error show the message and keep the dialog open."""
        try:
            self.root, _ = project.create_project(self.location_edit.text().strip(), self.name_edit.text(),
                                                  self.description_edit.toPlainText())
        except (ValueError, OSError) as error:
            self.error_label.setText(str(error))
            return
        self.accept()
