"""Project page: list of steps on the left, the page of the selected step on the right.

Step pages are plain widgets that provide:
    show_project(root, data, settings)   fill the page from the project
    signal step_done                     emitted when the step has finished and project.json is saved
    signal busy_changed(bool)            emitted when a long step starts / ends
    is_busy(), cancel_running()          (only pages that run long steps)
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QStackedWidget, QWidget

from ptrack.gui.pages.boxes_page import BoxesPage
from ptrack.gui.pages.import_page import ImportPage
from ptrack.gui.pages.overview_page import OverviewPage
from ptrack.gui.pages.process_page import ProcessPage
from ptrack.gui.pages.results_page import ResultsPage
from ptrack.gui.pages.track_page import TrackPage
from ptrack.gui.pages.verify_page import VerifyPage

# (key, title shown in the list)
STEP_LIST = [
    ("overview", "Project"),
    ("import", "1. Import video"),
    ("process", "2. Process"),
    ("boxes", "3. Define boxes"),
    ("verify", "4. Verify boxes"),
    ("track", "5. Track"),
    ("results", "6. Results"),
]
# Page to show after a step has finished
NEXT_PAGE = {"import": "process", "process": "boxes", "boxes": "verify", "verify": "track", "track": "results"}


def page_available(key, data):
    """True if the page `key` can be opened, given the steps already done."""
    steps = data["steps"]
    if key in ("overview", "import"):
        return True
    if key == "process":
        return steps["imported"]
    if key == "boxes":
        return steps["processed"]
    if key == "verify":
        return steps["processed"] and len(data["rois"]) >= 2
    if key == "track":
        return steps["rois_verified"]
    if key == "results":
        return steps["tracked"]
    return False


def first_page_to_show(data):
    """Page to open when a project is loaded: the first step that is not done."""
    steps = data["steps"]
    if not steps["imported"]:
        return "import"
    if not steps["processed"]:
        return "process"
    if not steps["rois_verified"]:
        return "boxes"
    if not steps["tracked"]:
        return "track"
    return "results"


class ProjectPage(QWidget):
    """Wizard for one open project."""

    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.root = None
        self.data = None

        self.pages = {
            "overview": OverviewPage(),
            "import": ImportPage(),
            "process": ProcessPage(),
            "boxes": BoxesPage(),
            "verify": VerifyPage(),
            "track": TrackPage(),
            "results": ResultsPage(),
        }
        self.step_list = QListWidget()
        self.step_list.setFixedWidth(190)
        self.stack = QStackedWidget()
        for key, title in STEP_LIST:
            self.step_list.addItem(title)
            self.stack.addWidget(self.pages[key])
        self.step_list.currentRowChanged.connect(self.stack.setCurrentIndex)

        for key, page in self.pages.items():
            if hasattr(page, "step_done"):
                page.step_done.connect(lambda key=key: self.on_step_done(key))
            if hasattr(page, "busy_changed"):
                page.busy_changed.connect(self.on_busy_changed)

        self.pages["verify"].back_requested.connect(lambda: self.go_to("boxes"))

        layout = QHBoxLayout(self)
        layout.addWidget(self.step_list)
        layout.addWidget(self.stack, stretch=1)

    def show_project(self, root, data):
        """Display a newly opened project, on the first step that is not done."""
        self.root = root
        self.data = data
        self.refresh_pages()
        self.go_to(first_page_to_show(data))

    def refresh_pages(self):
        """Refill every page from the project and enable the steps that can be opened."""
        for key, page in self.pages.items():
            page.show_project(self.root, self.data, self.settings)
        for row, (key, _) in enumerate(STEP_LIST):
            item = self.step_list.item(row)
            if page_available(key, self.data):
                item.setFlags(item.flags() | Qt.ItemIsEnabled)
            else:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)

    def go_to(self, key):
        """Select the page `key` in the list (shows it)."""
        row = [k for k, _ in STEP_LIST].index(key)
        self.step_list.setCurrentRow(row)

    def current_key(self):
        return STEP_LIST[self.step_list.currentRow()][0]

    def on_step_done(self, key):
        """A step finished: update all pages and move on to the next step."""
        self.refresh_pages()
        if key in NEXT_PAGE and page_available(NEXT_PAGE[key], self.data):
            self.go_to(NEXT_PAGE[key])
        if key == "verify":
            self.pages["track"].start_tracking()       # tracking starts automatically after Accept

    def on_busy_changed(self, busy):
        """While a step runs, the user cannot switch pages."""
        self.step_list.setEnabled(not busy)
        self.busy_changed.emit(busy)

    def is_busy(self):
        return any(hasattr(page, "is_busy") and page.is_busy() for page in self.pages.values())

    def cancel_running(self):
        """Cancel the running step (if any) and wait until it has stopped."""
        for page in self.pages.values():
            if hasattr(page, "is_busy") and page.is_busy():
                page.cancel_running()
