"""Main window: File menu, start page and project page."""

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget

from ptrack import __version__
from ptrack.core import project
from ptrack.core.settings import load_settings
from ptrack.gui.new_project_dialog import NewProjectDialog
from ptrack.gui.pages.project_page import ProjectPage
from ptrack.gui.pages.start_page import StartPage

MAX_RECENT = 10


class MainWindow(QMainWindow):
    """The application window.

    `qsettings` is where the list of recent projects is kept (a QSettings object; the default
    is the user's application settings, tests pass a temporary file).
    The tuning parameters come from settings.toml (`load_settings`).
    """

    def __init__(self, qsettings=None):
        super().__init__()
        self.qsettings = qsettings if qsettings is not None else QSettings("MO105", "ptrack")
        self.app_settings = load_settings()
        self.root = None      # folder of the open project
        self.data = None      # content of its project.json

        self.start_page = StartPage()
        self.project_page = ProjectPage(self.app_settings)
        self.project_page.busy_changed.connect(self.on_busy_changed)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.start_page)
        self.stack.addWidget(self.project_page)
        self.setCentralWidget(self.stack)

        self.start_page.new_requested.connect(self.new_project)
        self.start_page.open_requested.connect(self.choose_and_open_project)
        self.start_page.recent_selected.connect(self.open_project)

        self.create_menu()
        self.show_start_page()
        self.resize(900, 650)

    def create_menu(self):
        """File menu: New, Open, Recent, Close project, Quit."""
        file_menu = self.menuBar().addMenu("&File")
        self.file_menu = file_menu
        actions = [
            ("&New project…", QKeySequence.New, self.new_project),
            ("&Open project…", QKeySequence.Open, self.choose_and_open_project),
        ]
        for text, shortcut, slot in actions:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        self.recent_menu = file_menu.addMenu("Open &recent")
        file_menu.addSeparator()
        self.close_action = QAction("&Close project", self)
        self.close_action.triggered.connect(self.close_project)
        file_menu.addAction(self.close_action)
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # --- pages ----------------------------------------------------------------------------

    def show_start_page(self):
        self.root = None
        self.data = None
        self.start_page.set_recent(self.recent_projects())
        self.update_recent_menu()
        self.close_action.setEnabled(False)
        self.stack.setCurrentWidget(self.start_page)
        self.setWindowTitle(f"Point tracking {__version__}")

    def new_project(self):
        """Ask for name/location/description, create the project and open it."""
        dialog = NewProjectDialog(self, default_location=self.last_location())
        if dialog.exec():
            self.qsettings.setValue("last_location", str(dialog.root.parent))
            self.open_project(dialog.root)

    def choose_and_open_project(self):
        """Let the user pick a project folder, then open it."""
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", self.last_location())
        if folder:
            self.open_project(folder)

    def open_project(self, path):
        """Open the project in `path` (folder or project.json) and show it.

        Steps whose files were deleted or moved by hand are undone first (the user is told which).
        """
        try:
            root, data = project.open_project(path)
            messages = project.repair_missing_files(root, data)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Open project", f"This project cannot be opened:\n{error}")
            self.remove_recent(str(path))
            return
        if messages:
            QMessageBox.information(self, "Open project", "Some files of this project are missing:\n\n• "
                                    + "\n• ".join(messages))
        try:
            self.project_page.show_project(root, data)
        except (ValueError, OSError, KeyError) as error:
            QMessageBox.warning(self, "Open project", f"This project cannot be displayed:\n{error}")
            self.show_start_page()
            return
        self.root = root
        self.data = data
        self.add_recent(str(root))
        self.close_action.setEnabled(True)
        self.stack.setCurrentWidget(self.project_page)
        self.setWindowTitle(f"{data['project']['name']} — Point tracking {__version__}")

    def close_project(self):
        self.show_start_page()

    def on_busy_changed(self, busy):
        """While a step runs, the File menu is disabled (no new/open/close)."""
        self.file_menu.setEnabled(not busy)

    def closeEvent(self, event):
        """Closing while a step runs: ask, then cancel the step (nothing of it is recorded)."""
        if self.project_page.is_busy():
            answer = QMessageBox.question(
                self, "Quit", "A step is still running. Quit and discard this step?\n\n"
                "The project stays as it was before the step started.")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.project_page.cancel_running()
        event.accept()

    # --- recent projects (kept in the user's application settings, not in the project) ---

    def recent_projects(self):
        """Return the recent project folders that still exist, most recent first."""
        paths = self.qsettings.value("recent_projects", [])
        if isinstance(paths, str):          # QSettings returns a plain string for a one-item list
            paths = [paths]
        return [p for p in paths if (Path(p) / project.PROJECT_FILE).is_file()]

    def add_recent(self, path):
        paths = [p for p in self.recent_projects() if p != path]
        self.qsettings.setValue("recent_projects", [path] + paths[:MAX_RECENT - 1])
        self.update_recent_menu()

    def remove_recent(self, path):
        self.qsettings.setValue("recent_projects", [p for p in self.recent_projects() if p != path])
        self.update_recent_menu()

    def update_recent_menu(self):
        self.recent_menu.clear()
        paths = self.recent_projects()
        for path in paths:
            action = self.recent_menu.addAction(path)
            action.triggered.connect(lambda checked=False, p=path: self.open_project(p))
        self.recent_menu.setEnabled(bool(paths))

    def last_location(self):
        """Folder proposed in the New/Open dialogs: the last one used, or the home folder."""
        return self.qsettings.value("last_location", str(Path.home()))
