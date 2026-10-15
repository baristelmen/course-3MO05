"""Entry point of the point tracking application.

    python app.py
"""

import sys

import ptrack  # noqa: F401  first: stops with a clear message if the Python version is too old
from PySide6.QtWidgets import QApplication

from ptrack.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Point tracking")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
