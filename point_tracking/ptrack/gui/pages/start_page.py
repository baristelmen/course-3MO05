"""Start page: create a new project, open one, or reopen a recent one."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class StartPage(QWidget):
    """Buttons for New / Open project and the list of recent projects.

    The page only emits signals; the main window does the work.
    """

    new_requested = Signal()
    open_requested = Signal()
    recent_selected = Signal(str)      # path of the chosen recent project

    def __init__(self, parent=None):
        super().__init__(parent)
        title = QLabel("Point tracking")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        subtitle = QLabel("Create a project for each tested specimen, or open an existing one.")

        new_button = QPushButton("New project…")
        open_button = QPushButton("Open project…")
        for button in (new_button, open_button):
            button.setMinimumHeight(36)
        new_button.clicked.connect(self.new_requested)
        open_button.clicked.connect(self.open_requested)

        self.recent_list = QListWidget()
        self.recent_list.itemActivated.connect(lambda item: self.recent_selected.emit(item.data(Qt.UserRole)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(new_button)
        layout.addWidget(open_button)
        layout.addSpacing(10)
        layout.addWidget(QLabel("Recent projects (double-click to open):"))
        layout.addWidget(self.recent_list)

    def set_recent(self, paths):
        """Show the recent project folders (most recent first)."""
        self.recent_list.clear()
        for path in paths:
            item = QListWidgetItem(path)
            item.setData(Qt.UserRole, path)
            self.recent_list.addItem(item)
