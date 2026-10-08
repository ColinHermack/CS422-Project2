"""Goodput summary table and goodput-over-time plot for one results directory.

This is the analysis half of Part 1(c). run_experiments.py saves every
TCP_INFO sample to <results dir>/samples.csv and then calls
generate_report(), which:

    1. Loads the goodput samples from samples.csv.
    2. Computes min / median / mean / 95th-percentile goodput for each
       (destination, congestion control algorithm) pair, pooling all
       repetitions, and writes them to goodput_summary.csv and stdout.
    3. Plots goodput over time, one panel per destination, to
       goodput_over_time.pdf.

Everything is read back from the CSV rather than passed in memory, so the
table and plot can be regenerated after a long campaign without rerunning
it (run_experiments.py --report-only <results dir>).
"""

import csv
import logging
import math
import os
import statistics

import matplotlib

# "Agg" renders to files only, with no window. It must be selected before
# pyplot is imported, and it works on headless machines and in Docker.
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 (must come after matplotlib.use)
from matplotlib.lines import Line2D  # noqa: E402


logger = logging.getLogger(__name__)

# File names inside a results directory.
SAMPLES_FILE = "samples.csv"
SUMMARY_FILE = "goodput_summary.csv"
GOODPUT_PLOT_FILE = "goodput_over_time.pdf"

# Goodput is stored in bits/second; tables and plots use megabits/second
# (decimal mega, as networking rates are: 1 Mbit/s = 1,000,000 bits/s).
BITS_PER_MEGABIT = 1_000_000

# Columns of goodput_summary.csv, in order.
SUMMARY_COLUMNS = [
    "host", "port", "algorithm", "samples",
    "min_mbps", "median_mbps", "mean_mbps", "p95_mbps",
]

# Digits after the decimal point when writing Mbit/s values.
SUMMARY_DECIMALS = 3

# Plot layout: panels per row and the size of each panel, inches.
PLOT_COLUMNS = 2
PANEL_WIDTH_INCHES = 6
PANEL_HEIGHT_INCHES = 3


def load_samples(path):
    """Read the goodput samples from a samples.csv file.

    The first sample of every run is a baseline taken at t = 0. It has no
    previous sample to measure an interval from, so its goodput_bps cell
    is empty and the row is skipped here.

    Args:
        path: path to samples.csv written by run_experiments.py.

    Returns:
        List of dicts, in file order (which is time order within a run),
        with keys:
            "run_id", "repetition": ints,
            "host": str, "port": int,
            "algorithm": congestion control the kernel actually used,
            "t": seconds since the run started sending,
            "goodput_mbps": goodput over the interval ending at t, Mbit/s.
    """
    samples = []
    with open(path, newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            if row["goodput_bps"] == "":
                continue  # baseline sample at t = 0, no interval before it

            samples.append({
                "run_id": int(row["run_id"]),
                "repetition": int(row["repetition"]),
                "host": row["host"],
                "port": int(row["port"]),
                "algorithm": row["algorithm_used"],
                "t": float(row["t"]),
                "goodput_mbps": float(row["goodput_bps"]) / BITS_PER_MEGABIT,
            })
    return samples


def percentile_95(values):
    """Return the 95th percentile of a list of numbers.

    statistics.quantiles(values, n=100) returns the 99 cut points that split
    the data into 100 equal groups; cut point k (1-based) is the k-th
    percentile, so the 95th is at index 94. Values between data points are
    linearly interpolated.

    method="inclusive" treats the samples as the whole population, so the
    result always lies between min and max. The default "exclusive" method
    assumes the samples come from a larger population and can extrapolate
    beyond the largest sample, which would be confusing in a summary table.

    Args:
        values: list of numbers (at least one).

    Returns:
        The 95th percentile, same unit as the values.
    """
    if len(values) == 1:
        # quantiles() needs at least two points; one value is every percentile.
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def summarize_goodput(samples):
    """Compute goodput statistics per (destination, algorithm).

    All repetitions of the same destination and algorithm are pooled into
    one group, as the spec asks for one row per destination and algorithm.

    Args:
        samples: list of sample dicts from load_samples.

    Returns:
        List of dicts with the keys in SUMMARY_COLUMNS, sorted by host,
        port, then algorithm. Goodput values are in Mbit/s.
    """
    # Group goodput values by (host, port, algorithm).
    groups = {}
    for sample in samples:
        key = (sample["host"], sample["port"], sample["algorithm"])
        if key not in groups:
            groups[key] = []
        groups[key].append(sample["goodput_mbps"])

    rows = []
    for key in sorted(groups):
        host, port, algorithm = key
        values = groups[key]
        rows.append({
            "host": host,
            "port": port,
            "algorithm": algorithm,
            "samples": len(values),
            "min_mbps": min(values),
            "median_mbps": statistics.median(values),
            "mean_mbps": statistics.mean(values),
            "p95_mbps": percentile_95(values),
        })
    return rows


def write_summary(rows, path):
    """Write summary rows to a CSV file, rounding Mbit/s values.

    Args:
        rows: list of dicts from summarize_goodput.
        path: CSV file to create (overwritten if it exists).
    """
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for row in rows:
            rounded_row = dict(row)
            for column in ["min_mbps", "median_mbps", "mean_mbps", "p95_mbps"]:
                rounded_row[column] = round(row[column], SUMMARY_DECIMALS)
            writer.writerow(rounded_row)


def format_summary_table(rows):
    """Format summary rows as an aligned text table for the terminal.

    Args:
        rows: list of dicts from summarize_goodput.

    Returns:
        The table as one multi-line string.
    """
    # Width of the destination column: the longest "host:port", at least
    # as wide as its header.
    destination_width = len("destination")
    for row in rows:
        destination = f"{row['host']}:{row['port']}"
        destination_width = max(destination_width, len(destination))

    header = (
        f"{'destination':<{destination_width}}  {'algorithm':<9}  {'samples':>7}  "
        f"{'min':>8}  {'median':>8}  {'mean':>8}  {'p95':>8}   (Mbit/s)"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        destination = f"{row['host']}:{row['port']}"
        lines.append(
            f"{destination:<{destination_width}}  {row['algorithm']:<9}  {row['samples']:>7}  "
            f"{row['min_mbps']:>8.2f}  {row['median_mbps']:>8.2f}  "
            f"{row['mean_mbps']:>8.2f}  {row['p95_mbps']:>8.2f}"
        )
    return "\n".join(lines)


def plot_goodput_over_time(samples, path):
    """Plot goodput over time, one panel per destination, to a PDF.

    Each run (one destination, algorithm, and repetition) is one line.
    Lines are colored by algorithm, so repetitions of the same algorithm
    share a color. All panels share the same x and y axes so destinations
    can be compared at a glance. Each point is the average goodput over
    the sampling interval that ends at its x value.

    Args:
        samples: list of sample dicts from load_samples (must not be empty).
        path: PDF file to create (overwritten if it exists).
    """
    # Split samples into runs, and list destinations and algorithms in the
    # order they first appear (which is the order the tests were run).
    runs = {}
    destination_order = []
    algorithm_order = []
    for sample in samples:
        if sample["run_id"] not in runs:
            runs[sample["run_id"]] = []
        runs[sample["run_id"]].append(sample)

        destination = (sample["host"], sample["port"])
        if destination not in destination_order:
            destination_order.append(destination)
        if sample["algorithm"] not in algorithm_order:
            algorithm_order.append(sample["algorithm"])

    # One color per algorithm from matplotlib's default cycle ("C0", "C1", ...).
    algorithm_colors = {}
    for index, algorithm in enumerate(algorithm_order):
        algorithm_colors[algorithm] = f"C{index}"

    # Grid of panels. squeeze=False keeps `axes` a 2-D array even for a
    # single row or column, so indexing below works for any count.
    row_count = math.ceil(len(destination_order) / PLOT_COLUMNS)
    figure, axes = plt.subplots(
        row_count, PLOT_COLUMNS,
        sharex=True, sharey=True, squeeze=False,
        figsize=(PANEL_WIDTH_INCHES * PLOT_COLUMNS, PANEL_HEIGHT_INCHES * row_count),
    )

    # Panel position for destination number i: row i // columns, column i % columns.
    panels = {}
    for index, destination in enumerate(destination_order):
        panel = axes[index // PLOT_COLUMNS][index % PLOT_COLUMNS]
        host, port = destination
        panel.set_title(f"{host}:{port}", fontsize=9)
        panel.grid(True, alpha=0.3)
        panels[destination] = panel

    # Hide leftover panels when the destination count is odd.
    for index in range(len(destination_order), row_count * PLOT_COLUMNS):
        axes[index // PLOT_COLUMNS][index % PLOT_COLUMNS].set_visible(False)

    for run_samples in runs.values():
        first = run_samples[0]
        panel = panels[(first["host"], first["port"])]
        times = []
        goodputs = []
        for sample in run_samples:
            times.append(sample["t"])
            goodputs.append(sample["goodput_mbps"])
        panel.plot(times, goodputs, color=algorithm_colors[first["algorithm"]],
                   linewidth=1, alpha=0.8)

    # Goodput cannot be negative; anchoring at 0 avoids exaggerating small
    # differences when every panel shares the y axis.
    axes[0][0].set_ylim(bottom=0)

    # One legend for the whole figure, one entry per algorithm.
    legend_handles = []
    for algorithm in algorithm_order:
        legend_handles.append(Line2D([], [], color=algorithm_colors[algorithm], label=algorithm))
    figure.legend(handles=legend_handles, loc="upper right")

    figure.suptitle("Goodput over time (acknowledged bytes per interval)")
    figure.supxlabel("time since start of sending (s)")
    figure.supylabel("goodput (Mbit/s)")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)  # free memory; pyplot keeps figures open otherwise


def generate_report(results_dir):
    """Build the goodput summary table and plot for one results directory.

    Args:
        results_dir: directory containing samples.csv. Outputs are written
            next to it (goodput_summary.csv, goodput_over_time.pdf).

    Returns:
        The summary rows (see summarize_goodput); empty if there were no
        goodput samples, e.g. because every run failed.
    """
    samples = load_samples(os.path.join(results_dir, SAMPLES_FILE))
    if not samples:
        # Every run failed (or the campaign was interrupted before the
        # first run finished): nothing to summarize or plot.
        logger.warning("no goodput samples in %s, skipping report", results_dir)
        return []

    rows = summarize_goodput(samples)

    summary_path = os.path.join(results_dir, SUMMARY_FILE)
    write_summary(rows, summary_path)
    print(format_summary_table(rows))
    logger.info("wrote %s", summary_path)

    plot_path = os.path.join(results_dir, GOODPUT_PLOT_FILE)
    plot_goodput_over_time(samples, plot_path)
    logger.info("wrote %s", plot_path)
    return rows


# ---------------------------------------------------------------------------
# Self-check (runs on any OS; no network)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    # Inclusive percentile of 1..5: position 0.95 * (5 - 1) = 3.8 between
    # the sorted values, i.e. 4 + 0.8 * (5 - 4) = 4.8.
    assert abs(percentile_95([1, 2, 3, 4, 5]) - 4.8) < 1e-9
    assert percentile_95([7]) == 7

    # Fake samples.csv: two destinations, two algorithms, one baseline row
    # (empty goodput) at the start of each run.
    header = ["run_id", "repetition", "host", "port", "algorithm_used", "t", "goodput_bps"]
    fake_runs = [
        # (run_id, host, algorithm, goodput values in Mbit/s)
        (1, "a.example", "cubic", [1, 2, 3, 4, 5]),
        (2, "a.example", "reno", [10, 10, 10]),
        (3, "b.example", "cubic", [20, 30]),
    ]
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(os.path.join(temp_dir, SAMPLES_FILE), "w", newline="") as fake_file:
            fake_writer = csv.writer(fake_file)
            fake_writer.writerow(header)
            for run_id, host, algorithm, values in fake_runs:
                fake_writer.writerow([run_id, 1, host, 5201, algorithm, 0.0, ""])
                for index, value in enumerate(values):
                    fake_writer.writerow([run_id, 1, host, 5201, algorithm,
                                          float(index + 1), value * BITS_PER_MEGABIT])

        summary = generate_report(temp_dir)

        # Baselines skipped, groups sorted by host then algorithm.
        assert len(summary) == 3
        first_row = summary[0]
        assert (first_row["host"], first_row["algorithm"]) == ("a.example", "cubic")
        assert first_row["samples"] == 5
        assert first_row["min_mbps"] == 1
        assert first_row["median_mbps"] == 3
        assert first_row["mean_mbps"] == 3
        assert abs(first_row["p95_mbps"] - 4.8) < 1e-9
        assert summary[1]["algorithm"] == "reno"
        assert summary[2]["mean_mbps"] == 25

        assert os.path.getsize(os.path.join(temp_dir, SUMMARY_FILE)) > 0
        assert os.path.getsize(os.path.join(temp_dir, GOODPUT_PLOT_FILE)) > 0

    print("self-check passed")
