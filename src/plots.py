import math
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
from matplotlib.textpath import TextPath
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator
from matplotlib.transforms import ScaledTranslation, blended_transform_factory

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
NEUTRAL = "#8a8984"

VARIANT_ORDER = ["LLVM", "LLVM O1", "LLVM O2", "LLVM O3", "Cranelift", "TPDE", "TPDE inline", "TPDE inline,promote",
                 "TPDE MIR2", "TPDE inline MIR2", "TPDE inline,promote MIR2",
                 "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100", "TPDE inline 500",
                 "TPDE LLVM"]
VARIANT_COLORS = {
    "LLVM": "#e34948",
    "LLVM O1": "#2a78d6",
    "LLVM O2": "#1baf7a",
    "LLVM O3": "#eb6834",
    "TPDE": "#eda100",
    "TPDE inline": "#008300",
    # One green ramp from light (low cost factor, little inlining) to dark (high cost factor). 50 is the default of the
    # backend, so it has the color of "TPDE inline".
    "TPDE inline 10": "#53c44d",
    "TPDE inline 20": "#33a92f",
    "TPDE inline 50": "#008300",
    "TPDE inline 100": "#006e00",
    "TPDE inline 500": "#024f02",
    "TPDE inline,promote": "#1e528a",
    "TPDE MIR2": "#f5c95c",
    "TPDE inline MIR2": "#7ccf73",
    "TPDE inline,promote MIR2": "#6f9fd6",
    "TPDE LLVM": "#6250d6",
    "Cranelift": "#e87ba4",
}


def variant_color(name):
    return VARIANT_COLORS.get(name, NEUTRAL)


plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.size": 9,
    "text.color": TEXT,
    "axes.titlesize": 10,
    "axes.titleweight": "bold",
    "axes.labelcolor": TEXT_SECONDARY,
    "axes.edgecolor": GRID,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": TEXT_SECONDARY,
    "ytick.color": TEXT_SECONDARY,
    "xtick.major.size": 0,
    "legend.frameon": False,
})


def ordered(names):
    """The variants in the order of their colors, unknown ones last."""
    return sorted(names, key=lambda name: VARIANT_ORDER.index(name) if name in VARIANT_ORDER else len(VARIANT_ORDER))


def save(fig, name):
    RESULTS_DIR.mkdir(exist_ok=True)
    fig.savefig(RESULTS_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Graph: {RESULTS_DIR / name}.png")


def median_of_series(series):
    return {key: statistics.median(values) * 1000 for (key, values) in series.items()}


def medians_of_backend(config):
    return {key: median_of_series(config) for (key, config) in config.items()}


class Wrapper:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def short_name(self):
        return self._name

DIVERGING = LinearSegmentedColormap.from_list("diverging", ["#2a78d6", "#f0efec", "#e34948"])
SEQUENTIAL = LinearSegmentedColormap.from_list("sequential", ["#f0efec", "#2a78d6", "#0d2f5c"])

BOOTSTRAP_SAMPLES = 10000

# Heatmap geometry in inches: the cells fit a sign and three digits (or a share like 100%)
HEATMAP_CELL_PADDING = 0.08
HEATMAP_ROW_HEIGHT = 0.2
HEATMAP_EXTRA_GAP = 0.08
HEATMAP_CBAR_GAP = 0.12
HEATMAP_CBAR_WIDTH = 0.12


def text_width(text, fontsize):
    """Width of the text in inches with the default font."""
    return TextPath((0, 0), text, size=fontsize).get_extents().width / 72


def benchmark_frame(results, runs, relative="LLVM"):
    """The median of every benchmark in ms as a long frame with the columns Run, Backend, Benchmark and Time (ms). With
    relative, the baseline is left out and Baseline (ms) and Ratio (time / baseline) are added, only for the benchmarks
    that both have results. Times of 0 (a phase the backend doesn't have) are left out, they don't fit a log scale."""
    if relative and not any(relative in result for result in results):
        available = ", ".join(ordered({backend for result in results for backend in result}))
        raise ValueError(f"Baseline {relative!r} is in none of the results (available: {available}), pass relative=")
    rows = []
    for run, result in zip(runs, results):
        medians = medians_of_backend(result)
        baseline = medians.get(relative) if relative else None
        for backend, series in medians.items():
            if backend == relative:
                continue
            for benchmark, ms in series.items():
                if ms <= 0:
                    continue
                row = {"Run": run.short_name(), "Backend": backend, "Benchmark": benchmark, "Time (ms)": ms}
                if relative:
                    if baseline is None or baseline.get(benchmark, 0) <= 0:
                        continue
                    row["Baseline (ms)"] = baseline[benchmark]
                    row["Ratio"] = ms / baseline[benchmark]
                rows.append(row)
    return pd.DataFrame(rows)


def self_perf_results(results, phase):
    """The time of one phase of self-profile results as a single run ({backend: {benchmark: samples}}), so that the
    benchmarks are the data points instead of the iterations."""
    merged = defaultdict(dict)
    for benchmark, data in results.items():
        for backend, phases in data["phases"].items():
            merged[backend][benchmark] = phases[phase]
    return [dict(merged)]


def percent(ratio):
    """The ratio as change in %, with one decimal for small changes that aren't whole."""
    change = (ratio - 1) * 100
    if abs(change) < 0.05:
        return "0%"
    if abs(change) < 10 and abs(change - round(change)) >= 0.05:
        return f"{change:+.1f}%"
    return f"{change:+.0f}%"


# Ticks of ratio axes that span more than a factor of WIDE_RANGE, evenly spread on the log scale
WIDE_RANGE = 2.5
WIDE_TICKS = [0.01, 0.02, 0.05, 0.1, 0.2, 1 / 3, 0.5, 2 / 3, 1, 1.5, 2, 3, 5, 10, 20]


def ratio_ticks(lo, hi):
    if hi / lo > WIDE_RANGE:
        return [tick for tick in WIDE_TICKS if lo <= tick <= hi]
    changes = MaxNLocator(nbins=7, steps=[1, 2, 2.5, 5, 10]).tick_values((lo - 1) * 100, (hi - 1) * 100)
    return [1 + change / 100 for change in changes if change > -100 and lo <= 1 + change / 100 <= hi]


def ratio_axis(ax, axis="y"):
    """Puts ratios on a log scale with the ticks labeled as relative change in %. Call after plotting."""
    if axis == "y":
        ax.set_yscale("log")
        lo, hi = ax.get_ylim()
        target = ax.yaxis
    else:
        ax.set_xscale("log")
        lo, hi = ax.get_xlim()
        target = ax.xaxis
    target.set_major_locator(FixedLocator(ratio_ticks(lo, hi)))
    target.set_major_formatter(FuncFormatter(lambda ratio, _: percent(ratio)))
    target.set_minor_locator(NullLocator())


def geomean_ci(values):
    """Geometric mean and its 95% confidence interval, bootstrapped over the benchmarks."""
    logs = np.log(np.asarray(values, dtype=float))
    rng = np.random.default_rng(0)
    means = logs[rng.integers(0, len(logs), (BOOTSTRAP_SAMPLES, len(logs)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return math.exp(logs.mean()), math.exp(low), math.exp(high)


def panels(count, width=3.6, height=2.8, sharex=True, sharey=True):
    """A grid of up to three panels per row, the unused ones removed. A single panel is larger."""
    cols = min(count, 3)
    rows = math.ceil(count / cols)
    size = (6.4, 4) if count == 1 else (width * cols, height * rows)
    fig, axes = plt.subplots(rows, cols, figsize=size, sharex=sharex, sharey=sharey, squeeze=False,
                             layout="constrained")
    axes = axes.flatten()
    for ax in axes[count:]:
        ax.remove()
    return fig, axes[:count]


def baseline_line(ax, relative, axis="y"):
    line = ax.axhline if axis == "y" else ax.axvline
    line(1, color=TEXT_SECONDARY, linestyle="--", linewidth=1, zorder=1, label=f"{relative} (baseline)")


def spread_labels(positions, gap):
    """Moves the label positions (sorted ascending) apart until neighbors are at least gap away, keeping their mean."""
    positions = list(positions)
    for _ in range(50):
        moved = False
        for i in range(1, len(positions)):
            overlap = gap - (positions[i] - positions[i - 1])
            if overlap > 1e-9:
                positions[i - 1] -= overlap / 2
                positions[i] += overlap / 2
                moved = True
        if not moved:
            break
    return positions


def generate_distribution_plot(plot_name, title, results, runs, relative="LLVM"):
    """Per run, the results of all benchmarks of each backend sorted from best to worst, so that the share of benchmarks
    with a given change can be read off. The dotted lines are the geometric means over all benchmarks, labeled on the
    right. Also prints the geometric means with their bootstrapped 95% confidence interval."""
    df = benchmark_frame(results, runs, relative)
    value = "Ratio" if relative else "Time (ms)"
    backends = ordered(set(df["Backend"]))
    run_names = [run.short_name() for run in runs]

    fig, axes = panels(len(run_names))
    means = {}
    print(f"Geometric mean ({'relative to ' + relative if relative else 'ms'}, 95% CI):")
    for ax, run in zip(axes, run_names):
        means[run] = []
        for backend in backends:
            values = np.sort(df[(df["Run"] == run) & (df["Backend"] == backend)][value].to_numpy())
            if len(values) == 0:
                continue
            share = (np.arange(len(values)) + 0.5) / len(values) * 100
            ax.plot(share, values, color=variant_color(backend), linewidth=2, label=backend, zorder=3)

            mean, low, high = geomean_ci(values)
            ax.axhline(mean, color=variant_color(backend), linestyle=":", linewidth=1.2, zorder=2)
            means[run].append(mean)
            interval = (f"{percent(mean)} [{percent(low)}, {percent(high)}]" if relative
                        else f"{mean:.1f} [{low:.1f}, {high:.1f}] ms")
            print(f"  {run or backend:>22} {backend:>16}: {interval} (n={len(values)})")
        if relative:
            baseline_line(ax, relative)
        else:
            ax.set_yscale("log")
        if len(run_names) > 1:
            ax.set_title(run, fontweight="normal")
        ax.grid(axis="x")
        ax.set_xlim(0, 100)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda share, _: f"{share:.0f}%"))

    if relative:
        ratio_axis(axes[0])
    for ax in axes:
        if ax.get_subplotspec().is_first_col():
            ax.set_ylabel(f"Relative to {relative}" if relative else "Time (ms)")
        if ax.get_subplotspec().is_last_row() or len(run_names) == 1:
            ax.set_xlabel("Benchmarks (sorted)")
    # The geomean lines are identified by their color, the label only carries the value
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(plt.Line2D([], [], color=NEUTRAL, linestyle=":", linewidth=1.2))
    labels.append("Geometric mean")
    fig.legend(handles, labels, title="Backend", loc="outside right upper")
    fig.suptitle(title, fontweight="bold", fontsize=10)

    # Label the geomeans right of each panel, spread apart where they would overlap
    fig.canvas.draw()
    for ax, run in zip(axes, run_names):
        to_axes = ax.transScale + ax.transLimits
        order = sorted(means[run])
        fractions = [to_axes.transform((1, mean))[1] for mean in order]
        gap = 7 / (ax.get_window_extent().height * 72 / fig.dpi)
        for mean, fraction in zip(order, spread_labels(fractions, gap)):
            ax.annotate(percent(mean) if relative else f"{mean:.0f}", xy=(1, fraction), xycoords="axes fraction",
                        xytext=(3, 0), textcoords="offset points", fontsize=6, color=TEXT_SECONDARY, va="center",
                        annotation_clip=False)
    save(fig, plot_name)


def generate_distribution_plot_self_perf(plot_name, title, results, runs, phase, relative="LLVM"):
    """generate_distribution_plot of one phase of self-profile results, with the benchmarks as data points."""
    generate_distribution_plot(plot_name, title, self_perf_results(results, phase), [Wrapper(phase)], relative)


def generate_heatmap(plot_name, title, results, runs, relative="LLVM", limits=None, extra=None, extra_title=None,
                     row_groups=None, shared_runs=()):
    """Every benchmark (rows) with every run and backend (columns), sorted by the mean change over all columns. Missing
    cells are benchmarks a backend failed on, backends without any result in a run get no column. limits is the
    (low, high) ratio of the color scale, beyond which the colors saturate, by default symmetric around the baseline at
    the 98th percentile of the changes.

    extra are additional columns {label: {benchmark: share}} with shares between 0 and 1, shown in % at the end of each
    row with their own color scale, under extra_title.

    row_groups {row: group} keeps the rows of a group together and names the group left of them: the groups are sorted
    by the mean change of their rows, the rows within a group by their own. The runs named in shared_runs have the same
    value in every row of a group, which is drawn as one cell spanning the rows of the group."""
    df = benchmark_frame(results, runs, relative)
    if df.empty:
        print(f"Heatmap {plot_name}: no results, skipped")
        return
    backends = ordered(set(df["Backend"]))
    run_names = [run.short_name() for run in runs]
    multi = len(run_names) > 1

    df["Column"] = [f"{run}\n{backend}" if multi else backend for run, backend in zip(df["Run"], df["Backend"])]
    present = set(df["Column"])
    # The backends with results per run, runs without any are left out
    run_backends = [(run, [backend for backend in backends if (f"{run}\n{backend}" if multi else backend) in present])
                    for run in run_names]
    run_backends = [(run, names) for run, names in run_backends if names]
    columns = [f"{run}\n{backend}" if multi else backend for run, names in run_backends for backend in names]
    if relative:
        df["Value"] = np.log(df["Ratio"])
    else:
        df["Value"] = np.log10(df["Time (ms)"])
    table = df.pivot_table(index="Benchmark", columns="Column", values="Value").reindex(columns=columns)
    means = table.mean(axis=1).fillna(math.inf)
    if row_groups:
        group_of = {row: row_groups.get(row, row) for row in table.index}
        group_means = means.groupby(group_of).mean()
        table = table.loc[sorted(table.index, key=lambda row: (group_means[group_of[row]], group_of[row], means[row]))]
    else:
        table = table.loc[means.sort_values().index]

    if relative:
        def cell(v):
            if np.isnan(v):
                return ""
            change = round((math.exp(v) - 1) * 100)
            return "0" if change == 0 else f"{change:+d}"

        annot = table.map(cell)
        if limits:
            low, high = math.log(limits[0]), math.log(limits[1])
        else:
            high = np.nanpercentile(np.abs(table.to_numpy()), 98)
            low = -high
        ticks = [math.log(tick) for tick in ratio_ticks(math.exp(low), math.exp(high))]
        style = {"cmap": DIVERGING, "center": 0, "vmin": low, "vmax": high,
                 "cbar_kws": {"format": FuncFormatter(lambda v, _: percent(math.exp(v))), "ticks": ticks,
                              "shrink": 0.5 if len(table) > 15 else 1, "label": f"Relative to {relative}"}}
    else:
        annot = table.map(lambda v: "" if np.isnan(v) else f"{10 ** v:.0f}")
        style = {"cmap": SEQUENTIAL,
                 "cbar_kws": {"format": FuncFormatter(lambda v, _: f"{10 ** v:.0f}"),
                              "shrink": 0.5 if len(table) > 15 else 1,
                              "label": "Time (ms)"}}
    # The rows of each group as (group, first row index, number of rows), in the order of the table
    group_spans = []
    if row_groups:
        for index, row in enumerate(table.index):
            group = row_groups.get(row, row)
            if group_spans and group_spans[-1][0] == group:
                group_spans[-1][2] += 1
            else:
                group_spans.append([group, index, 1])
    # The shared runs are drawn as one cell spanning all rows of a group, see below
    shared = [column for column in columns
              if (column.split("\n")[0] if multi else run_names[0]) in shared_runs] if row_groups else []
    merged = [(column, start, count, annot[column].iloc[start:start + count].replace("", np.nan).dropna(),
               table[column].iloc[start:start + count].dropna())
              for column in shared for _, start, count in group_spans if count > 1]
    for column, start, count, _, _ in merged:
        annot.iloc[start:start + count, columns.index(column)] = ""

    # Fixed cell sizes, the labels around the cells extend the figure when it is saved (bbox_inches="tight")
    cell = max(text_width("+888", 6), text_width("100%", 6)) + HEATMAP_CELL_PADDING
    heat_width, height = cell * len(columns), HEATMAP_ROW_HEIGHT * len(table)
    extra_width = cell * len(extra) + HEATMAP_EXTRA_GAP if extra else 0
    width = heat_width + extra_width + HEATMAP_CBAR_GAP + HEATMAP_CBAR_WIDTH
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_axes((0, 0, heat_width / width, 1))
    if extra:
        extra_ax = fig.add_axes(((heat_width + HEATMAP_EXTRA_GAP) / width, 0, (extra_width - HEATMAP_EXTRA_GAP) / width, 1))
    cbar_height = 0.5 if len(table) > 15 and not extra else 1
    style["cbar_ax"] = fig.add_axes((1 - HEATMAP_CBAR_WIDTH / width, (1 - cbar_height) / 2, HEATMAP_CBAR_WIDTH / width,
                                     cbar_height))
    del style["cbar_kws"]["shrink"]
    sns.heatmap(table, annot=annot, fmt="", annot_kws={"fontsize": 6}, linewidths=0.5, linecolor=SURFACE, ax=ax,
                **style)
    style["cbar_ax"].tick_params(labelsize=7)
    style["cbar_ax"].yaxis.label.set_fontsize(8)
    ax.set_ylabel("")
    ax.set_xlabel("")
    ax.tick_params(axis="y", labelsize=7)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(False)
    # One cell per group for the shared runs, over the cells of its rows, with the color of the value
    mesh = ax.collections[0]
    for column, start, count, labels, values in merged:
        if values.empty:
            continue
        color = mesh.cmap(mesh.norm(values.iloc[0]))
        x = columns.index(column)
        ax.add_patch(Rectangle((x, start), 1, count, facecolor=color, edgecolor=SURFACE, linewidth=0.5))
        if not labels.empty:
            text = ".15" if sns.utils.relative_luminance(color) > 0.408 else "w"
            ax.text(x + 0.5, start + count / 2, labels.iloc[0], ha="center", va="center", fontsize=6, color=text)
    # The name of each group left of the row labels, with a bracket over its rows. A group with a single row of the
    # same name needs none.
    if row_groups:
        renderer = fig.canvas.get_renderer()
        label_width = max(label.get_window_extent(renderer).width for label in ax.get_yticklabels()) * 72 / fig.dpi
        offset = label_width + 10
        to_left = blended_transform_factory(ax.transAxes, ax.transData) + ScaledTranslation(-offset / 72, 0,
                                                                                            fig.dpi_scale_trans)
        for group, start, count in group_spans:
            if count == 1 and table.index[start] == group:
                continue
            ax.plot([0, 0], [start + 0.2, start + count - 0.2], color=TEXT_SECONDARY, linewidth=0.8,
                    transform=to_left, clip_on=False)
            ax.annotate(group, xy=(0, start + count / 2), xycoords=to_left, xytext=(-4, 0), textcoords="offset points",
                        ha="right", va="center", fontsize=8, color=TEXT, annotation_clip=False)
    # Separate the runs and name them above their group of columns, the columns only name the backend
    if multi:
        position = 0
        labels = []
        # If a run name is wider than its columns, all are wrapped to fit above them
        wrapped = any(text_width(run, 8) > cell * len(names) - 0.15 and ", " in run for run, names in run_backends)
        for index, (run, names) in enumerate(run_backends):
            if index:
                ax.axvline(position, color=SURFACE, linewidth=4)
            name = run.replace(", ", "\n") if wrapped else run
            ax.annotate(name, xy=(position + len(names) / 2, 1), xycoords=("data", "axes fraction"),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8,
                        color=TEXT, annotation_clip=False)
            position += len(names)
            labels += names
        ax.set_xticklabels(labels, rotation=30, ha="right", rotation_mode="anchor")
        ax.set_title(title + (" (change in %)" if relative else " (ms)"), pad=26 if wrapped else 16)
    else:
        ax.set_title(title + (" (change in %)" if relative else " (ms)"))

    if extra:
        shares = pd.DataFrame({label: pd.Series(values, dtype=float) for label, values in extra.items()})
        shares = shares.reindex(index=table.index, columns=list(extra))
        sns.heatmap(shares, annot=shares.map(lambda v: "" if np.isnan(v) else f"{v * 100:.0f}%"), fmt="",
                    annot_kws={"fontsize": 6}, linewidths=0.5, linecolor=SURFACE, cmap=SEQUENTIAL, vmin=0, vmax=1,
                    cbar=False, ax=extra_ax)
        extra_ax.set_ylabel("")
        extra_ax.set_xlabel("")
        extra_ax.set_yticks([])
        extra_ax.tick_params(axis="x", labelsize=7)
        extra_ax.set_xticklabels(list(extra), rotation=30, ha="right", rotation_mode="anchor")
        extra_ax.grid(False)
        if extra_title:
            extra_ax.set_title(extra_title, fontsize=8, pad=(26 if wrapped else 16) if multi else None)
    save(fig, plot_name)


def backend_shares(compiletimes, backendtimes, variant):
    """{benchmark: share} of the backend in the compile time of variant: backend time / compile time of the medians."""
    total = median_of_series(compiletimes[variant])
    backend = median_of_series(backendtimes[variant])
    return {benchmark: backend[benchmark] / time for benchmark, time in total.items() if benchmark in backend}


def generate_heatmap_self_perf(plot_name, title, results, phases, relative="LLVM", limits=None):
    """generate_heatmap of several phases of self-profile results, one group of backend columns per phase."""
    generate_heatmap(plot_name, title, [self_perf_results(results, phase)[0] for phase in phases],
                     [Wrapper(phase) for phase in phases], relative, limits)


def runtime_per_group(results, groups):
    """Runtime results {variant: {benchmark: samples}} as {variant: {group: [geometric mean of the benchmark medians]}},
    with groups {group: [benchmark]}. A group is left out for a variant that lacks any of its benchmarks, its mean
    wouldn't be comparable to the one of the baseline."""
    per_group = {}
    for variant, series in results.items():
        for group, benchmarks in groups.items():
            if benchmarks and all(benchmark in series for benchmark in benchmarks):
                mean = statistics.geometric_mean(statistics.median(series[benchmark]) for benchmark in benchmarks)
                per_group.setdefault(variant, {})[group] = [mean]
    return per_group


def compile_runtime_runs(compiletimes, runtimes, settings, groups, prefix=""):
    """The compile time and runtime of the runtime benchmarks as (results, runs, row_groups, shared_runs) for
    generate_heatmap, a compile time and a runtime run for each of the settings (names of the runs). compiletimes are
    the results of the copies of the groups, named prefix + group, runtimes the results of their benchmarks, groups
    maps each group to its benchmarks.

    Every runtime benchmark is a row, named after the benchmark (the names are unique among all groups), row_groups
    names its group. The compile time is of the whole group, so it is the same in all rows of the group
    (shared_runs)."""
    rows = {(group, benchmark): benchmark for group, benchmarks in groups.items() for benchmark in benchmarks}
    if len(set(rows.values())) < len(rows):
        raise ValueError("Runtime benchmark names are not unique among the groups")
    row_groups = {row: group for (group, _), row in rows.items()}
    results, runs, shared_runs = [], [], []
    for setting, compiletime, runtime in zip(settings, compiletimes, runtimes):
        compiletime = strip_prefix(compiletime, prefix)
        results.append({variant: {row: series[group] for (group, _), row in rows.items() if group in series}
                        for variant, series in compiletime.items()})
        runs.append(Wrapper(f"Compile time, {setting}" if setting else "Compile time"))
        shared_runs.append(runs[-1].short_name())
        results.append({variant: {row: series[benchmark] for (_, benchmark), row in rows.items() if benchmark in series}
                        for variant, series in runtime.items()})
        runs.append(Wrapper(f"Runtime, {setting}" if setting else "Runtime"))
    return results, runs, row_groups, shared_runs


def strip_prefix(results, prefix):
    """{variant: {benchmark: samples}} with the prefix removed from the benchmark names."""
    return {variant: {benchmark.removeprefix(prefix): samples for benchmark, samples in series.items()}
            for variant, series in results.items()}


def generate_compile_runtime_heatmap(plot_name, title, compiletimes, runtimes, settings, groups, relative="LLVM",
                                     prefix=""):
    """generate_heatmap with the compile time of the runtime benchmark groups next to the runtime of each of their
    benchmarks (rows), see compile_runtime_runs."""
    results, runs, row_groups, shared_runs = compile_runtime_runs(compiletimes, runtimes, settings, groups, prefix)
    generate_heatmap(plot_name, title, results, runs, relative, row_groups=row_groups, shared_runs=shared_runs)
