"""Result plots: strain vs time for every pair of boxes, score vs frame for every box.

The `draw_*` functions draw on a matplotlib Axes; they are used both by the GUI (interactive
plots) and by `save_plots` (PNG files in images/). Only matplotlib's object interface is used
(no pyplot), so plots can be made safely in the background tracking thread.
"""

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

STRAIN_PLOT_FILE = "strain_vs_time.png"
SCORE_PLOT_FILE = "score_vs_frame.png"


def draw_strain(ax, time_s, strains, pairs, visible=None):
    """Strain of every pair (or only the pairs whose `visible[k]` is True) against time."""
    ax.clear()
    drawn = 0
    for k, (i, j) in enumerate(pairs):
        if visible is None or visible[k]:
            ax.plot(time_s, strains[:, k], label=f"{i}–{j}", linewidth=1.2)
            drawn += 1
    ax.axhline(0, color="grey", linewidth=0.6)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Engineering strain (–)")
    ax.set_title("Strain between boxes")
    ax.grid(True, alpha=0.3)
    if drawn > 0:
        ax.legend(title="Pair", fontsize="small", ncol=2 if len(pairs) > 6 else 1)


def draw_scores(ax, frames, scores, refresh_threshold, lost_threshold):
    """ZNCC score of every box against the frame number, with the refresh and lost thresholds."""
    ax.clear()
    for n in range(scores.shape[1]):
        ax.plot(frames, scores[:, n], label=f"Box {n + 1}", linewidth=1.2)
    ax.axhline(refresh_threshold, color="orange", linestyle="--", linewidth=1, label=f"refresh ({refresh_threshold})")
    ax.axhline(lost_threshold, color="red", linestyle="--", linewidth=1, label=f"lost ({lost_threshold})")
    ax.set_ylim(min(0.0, scores.min() - 0.05), 1.02)
    ax.set_xlabel("Processed frame")
    ax.set_ylabel("ZNCC score (–)")
    ax.set_title("Tracking score of each box")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize="small", loc="lower left")


def save_plots(images_dir, results, refresh_threshold, lost_threshold, suffix=""):
    """Write the two plots as PNG files in `images_dir` and return their paths.

    `results` is the dict returned by `results.read_results_csv` (or built the same way).
    `suffix` is added before ".png" (used for temporary files).
    """
    strain_path = images_dir / STRAIN_PLOT_FILE.replace(".png", suffix + ".png")
    figure, ax = new_figure()
    draw_strain(ax, results["time_s"], results["strains"], results["pairs"])
    figure.savefig(strain_path)

    score_path = images_dir / SCORE_PLOT_FILE.replace(".png", suffix + ".png")
    figure, ax = new_figure()
    draw_scores(ax, results["processed_frame"], results["scores"], refresh_threshold, lost_threshold)
    figure.savefig(score_path)
    return [strain_path, score_path]


def new_figure():
    """A matplotlib figure for a PNG file (8 × 5 inches at 150 dpi) and its axes."""
    figure = Figure(figsize=(8, 5), dpi=150, layout="constrained")
    FigureCanvasAgg(figure)
    return figure, figure.add_subplot()
