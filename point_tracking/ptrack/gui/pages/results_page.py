"""Step 6 page: the tracking results, in three tabs.

- Summary: analysis info, warnings, tracking quality of each box, final strain of each pair.
- Plots:   strain vs time (pairs can be hidden) and score vs frame, side by side.
- Frames:  browse results/tracking.mp4 frame by frame (boxes drawn, red = lost).

Everything is read back from the project folder (results/results.csv, results/tracking.mp4,
project.json), so the page also works for a project that is reopened later.
"""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ptrack.core import project
from ptrack.core.analysis import box_quality, result_warnings
from ptrack.core.plots import draw_scores, draw_strain
from ptrack.core.results import read_results_csv
from ptrack.core.video import read_frame
from ptrack.gui.widgets.frame_view import FrameView

STRAIN_COLUMNS = 3      # strain labels per row in the Summary tab


def link(path, text):
    """HTML link that opens a local file or folder with the system application."""
    return f'<a href="{QUrl.fromLocalFile(str(path)).toString()}">{text}</a>'


def clear_layout(layout):
    """Remove every widget from a layout (used when the page is refilled)."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()


class ResultsPage(QWidget):
    """Results of the tracking: Summary, Plots and Frames tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = None
        self.results = None

        title = QLabel("6. Results")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_summary_tab(), "Summary")
        self.tabs.addTab(self.build_plots_tab(), "Plots")
        self.tabs.addTab(self.build_frames_tab(), "Frames")

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.tabs)

    # --- building the tabs (once) -----------------------------------------------------------

    def build_summary_tab(self):
        self.info_labels = {}
        info_box = QGroupBox("Analysis info")
        info_form = QFormLayout(info_box)
        for key, text in (("project", "Project"), ("description", "Description"), ("source", "Source video"),
                          ("fps", "Target frame rate"), ("frames", "Frames tracked"), ("date", "Tracked on"),
                          ("files", "Files")):
            label = QLabel()
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            label.setOpenExternalLinks(True)          # links open the files/folders
            self.info_labels[key] = label
            info_form.addRow(text + ":", label)

        self.warnings_box = QGroupBox("Warnings")
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet("color: #c0392b;")
        QVBoxLayout(self.warnings_box).addWidget(self.warnings_label)

        self.quality_box = QGroupBox("Tracking quality of each box")
        self.quality_grid = QGridLayout(self.quality_box)

        self.strain_box = QGroupBox("Final strain between boxes (last frame)")
        self.strain_grid = QGridLayout(self.strain_box)

        content = QWidget()
        layout = QVBoxLayout(content)
        for widget in (info_box, self.warnings_box, self.quality_box, self.strain_box):
            layout.addWidget(widget)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def build_plots_tab(self):
        self.strain_figure = Figure(layout="constrained")
        self.strain_canvas = FigureCanvasQTAgg(self.strain_figure)
        self.strain_ax = self.strain_figure.add_subplot()
        self.score_figure = Figure(layout="constrained")
        self.score_canvas = FigureCanvasQTAgg(self.score_figure)
        self.score_ax = self.score_figure.add_subplot()

        self.pair_checks_layout = QGridLayout()
        self.pair_checks = []
        pair_checks_widget = QWidget()
        pair_checks_widget.setLayout(self.pair_checks_layout)
        pairs_scroll = QScrollArea()
        pairs_scroll.setWidgetResizable(True)
        pairs_scroll.setWidget(pair_checks_widget)
        pairs_scroll.setMaximumHeight(80)

        left = QVBoxLayout()
        left.addWidget(QLabel("Pairs shown:"))
        left.addWidget(pairs_scroll)
        left.addWidget(NavigationToolbar2QT(self.strain_canvas, self))
        left.addWidget(self.strain_canvas, stretch=1)
        right = QVBoxLayout()
        right.addWidget(QLabel("The saved PNG files are in images/."))
        right.addWidget(NavigationToolbar2QT(self.score_canvas, self))
        right.addWidget(self.score_canvas, stretch=1)

        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.addLayout(left, stretch=1)
        layout.addLayout(right, stretch=1)
        return tab

    def build_frames_tab(self):
        self.frame_view = FrameView()
        self.frame_slider = QSlider(Qt.Horizontal)
        # The frame is loaded when the slider is released (loading at every step of a drag is slow on
        # long 4K videos); while dragging, only the frame number and time are updated.
        self.frame_slider.setTracking(False)
        self.frame_slider.sliderMoved.connect(self.show_frame_number)
        self.frame_spin = QSpinBox()
        self.frame_label = QLabel()
        self.frame_slider.valueChanged.connect(self.frame_spin.setValue)
        self.frame_spin.valueChanged.connect(self.frame_slider.setValue)
        self.frame_spin.valueChanged.connect(self.show_frame)
        first_button = QPushButton("First")
        first_button.clicked.connect(lambda: self.frame_spin.setValue(0))
        last_button = QPushButton("Last")
        last_button.clicked.connect(lambda: self.frame_spin.setValue(self.frame_spin.maximum()))
        fit_button = QPushButton("Fit image")
        fit_button.clicked.connect(self.frame_view.fit)

        controls = QHBoxLayout()
        controls.addWidget(first_button)
        controls.addWidget(self.frame_slider, stretch=1)
        controls.addWidget(last_button)
        controls.addWidget(QLabel("Frame:"))
        controls.addWidget(self.frame_spin)
        controls.addWidget(fit_button)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Frames of results/tracking.mp4: green = box found, red = box lost."))
        layout.addWidget(self.frame_view, stretch=1)
        layout.addWidget(self.frame_label)
        layout.addLayout(controls)
        return tab

    # --- filling the page ---------------------------------------------------------------------

    def show_project(self, root, data, settings=None):
        self.root = root
        self.data = data
        if not data["steps"]["tracked"]:
            self.results = None
            return
        self.results = read_results_csv(root / project.RESULTS_FILE)
        self.fill_summary()
        self.fill_plots()
        self.fill_frames()

    def fill_summary(self):
        data, results, root = self.data, self.results, self.root
        tracker = data["settings_used"]["tracker"]
        source = data["source_video"]
        n_frames = len(results["time_s"])

        self.info_labels["project"].setText(data["project"]["name"])
        self.info_labels["description"].setText(data["project"]["description"] or "—")
        self.info_labels["source"].setText(f"{source['original_filename']} — {source['width']} × {source['height']} px, "
                                           f"{source['fps_nominal']:.2f} FPS, {source['duration_s']:.2f} s")
        self.info_labels["fps"].setText(f"{data['processing']['target_fps']} FPS")
        self.info_labels["frames"].setText(f"{n_frames} frames, {results['time_s'][-1]:.2f} s")
        self.info_labels["date"].setText(data["results"].get("tracked_at", "—").replace("T", " "))
        self.info_labels["files"].setText(
            f"{link(root, 'Project folder')} · {link(root / project.RESULTS_FILE, 'results.csv')} · "
            f"{link(root / project.TRACKING_VIDEO_FILE, 'tracking.mp4')} (open with your video player) · "
            f"{link(root / 'images', 'images/')}<br>{root}")

        warnings = result_warnings(results["source_frame"], results["time_s"], results["scores"],
                                   tracker["lost_threshold"])
        self.warnings_box.setVisible(bool(warnings))
        self.warnings_label.setText("\n".join("• " + w for w in warnings))

        clear_layout(self.quality_grid)
        refreshes = data["results"].get("refreshes_per_box")
        headers = ["Box", "Lowest score", "at frame", "Mean score", "Frames lost", "Template refreshes"]
        for column, text in enumerate(headers):
            header = QLabel(f"<b>{text}</b>")
            self.quality_grid.addWidget(header, 0, column)
        for row, quality in enumerate(box_quality(results["scores"], tracker["lost_threshold"]), start=1):
            frame = quality.lowest_frame
            values = [str(quality.box), f"{quality.lowest_score:.3f}",
                      f"{frame} ({results['time_s'][frame]:.2f} s)", f"{quality.mean_score:.3f}",
                      str(quality.lost_frames), str(refreshes[row - 1]) if refreshes else "—"]
            for column, value in enumerate(values):
                label = QLabel(value)
                if column == 4 and quality.lost_frames > 0:
                    label.setStyleSheet("color: #c0392b; font-weight: bold;")
                self.quality_grid.addWidget(label, row, column)
        note = QLabel(f"Score: 1 = perfect match. Below {tracker['lost_threshold']} a box counts as lost; below "
                      f"{tracker['refresh_threshold']} its template is refreshed. Frame 0 (always 1) is left out "
                      "of the mean.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        self.quality_grid.addWidget(note, len(results["scores"][0]) + 1, 0, 1, len(headers))

        clear_layout(self.strain_grid)
        centres = results["centres"]
        for k, (i, j) in enumerate(results["pairs"]):
            initial_distance = float(np.linalg.norm(centres[0, j - 1] - centres[0, i - 1]))
            label = QLabel(f"<b>{i}–{j}</b>: {results['strains'][-1, k]:+.5f}  "
                           f"<span style='color:gray'>(L0 = {initial_distance:.1f} px)</span>")
            self.strain_grid.addWidget(label, k // STRAIN_COLUMNS, k % STRAIN_COLUMNS)

    def fill_plots(self):
        clear_layout(self.pair_checks_layout)
        self.pair_checks = []
        for k, (i, j) in enumerate(self.results["pairs"]):
            check = QCheckBox(f"{i}–{j}")
            check.setChecked(True)
            check.toggled.connect(self.redraw_strain)
            self.pair_checks.append(check)
            self.pair_checks_layout.addWidget(check, k // 8, k % 8)
        self.redraw_strain()
        tracker = self.data["settings_used"]["tracker"]
        draw_scores(self.score_ax, self.results["processed_frame"], self.results["scores"],
                    tracker["refresh_threshold"], tracker["lost_threshold"])
        self.score_canvas.draw_idle()

    def redraw_strain(self):
        visible = [check.isChecked() for check in self.pair_checks]
        draw_strain(self.strain_ax, self.results["time_s"], self.results["strains"], self.results["pairs"], visible)
        self.strain_canvas.draw_idle()

    def fill_frames(self):
        last = len(self.results["time_s"]) - 1
        for widget in (self.frame_slider, self.frame_spin):
            widget.blockSignals(True)
            widget.setRange(0, last)
            widget.setValue(last)
            widget.blockSignals(False)
        self.show_frame(last, fit=True)

    def show_frame_number(self, index):
        """While the slider is dragged: show which frame will be loaded."""
        if self.results is not None:
            self.frame_label.setText(f"Frame {index}  ·  {self.results['time_s'][index]:.2f} s  ·  "
                                     "(release the slider to load it)")

    def show_frame(self, index, fit=False):
        """Show frame `index` of tracking.mp4 with its time and the scores of the boxes.

        `fit=True` fits the image to the view; otherwise the current zoom is kept while browsing.
        """
        if self.results is None:
            return
        frame = read_frame(self.root / project.TRACKING_VIDEO_FILE, index)
        if fit:
            self.frame_view.set_frame(frame)
        else:
            self.frame_view.update_frame(frame)
        scores = "   ".join(f"box {n + 1}: {s:.3f}" for n, s in enumerate(self.results["scores"][index]))
        self.frame_label.setText(f"Frame {index}  ·  {self.results['time_s'][index]:.2f} s  ·  "
                                 f"source frame {self.results['source_frame'][index]}  ·  scores: {scores}")
