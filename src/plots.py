import math
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

from src.runs import CompileTime, Runtime

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator, NullLocator

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


def merge_dicts(a, b):
    return {k: (a.get(k), b.get(k)) for k in a.keys() | b.keys()}


def generate_box_plot(plot_name, title, results, runs, VARIANTS, relative="LLVM", single_test=False):
    # Reduce everything to median
    if not single_test:
        results = [medians_of_backend(config) for config in results]
    else:
        results = [
            {
                backend: {
                    str(i): value * 1000
                    for (i, value) in enumerate(values)
                }
                for (backend, values) in config.items()
            }
            for config in results
        ]

    fig, ax = plt.subplots()
    plot_data = []

    # Compute data and print
    for run, result in zip(runs, results):
        print(f"{run.name()}:")

        if relative:
            llvm = result[relative]
            print(f"LLVM: {statistics.geometric_mean(llvm.values())}")

            for name, series in result.items():
                if name == relative:
                    continue

                print(f"{name}")

                merge = merge_dicts(llvm, series)
                existing = {key: (a, b) for (key, (a, b)) in merge.items() if a is not None and b is not None}

                missing = sum(1 for a, b in merge.values() if b is None)
                if missing > 0:
                    print(f"  missing: {missing}")

                ratio = [b / a * 100 for a, b in existing.values()]
                min_val = min(ratio) - 100
                max_val = max(ratio) - 100
                mean = statistics.geometric_mean(ratio) - 100
                geomstdev = math.exp(statistics.stdev([math.log(r) for r in ratio]))
                print(
                    f"  relative: mean: {mean:.2f}%, geom-stdev: {geomstdev:.2f}, min: {min_val:.2f}%, max: {max_val:.2f}%")

                for r in ratio:
                    plot_data.append({
                        "Run": run.short_name(),
                        "Backend": name,
                        "Relative Change (%)": r - 100
                    })
        else:
            for name, series in result.items():
                print(f"{name}")

                # absolute values
                mean = statistics.geometric_mean(series.values())
                print(
                    f"  absolute: mean: {mean:.2f}ms")

                for v in series.values():
                    plot_data.append({
                        "Run": run.short_name(),
                        "Backend": name,
                        "Time (ms)": v
                    })

    df = pd.DataFrame(plot_data)
    backends = ordered(set(df["Backend"]))
    by_run = len(runs) > 1
    sns.boxplot(
        data=df,
        x="Run" if by_run else "Backend",
        order=[run.short_name() for run in runs] if by_run else backends,
        y="Relative Change (%)" if relative else "Time (ms)",
        palette={v: variant_color(v) for v in VARIANTS if not relative or v != "LLVM"},
        hue="Backend",
        hue_order=backends,
        ax=ax,
        gap=0.1,
        saturation=1,
        linewidth=0.8,
        boxprops={"edgecolor": TEXT_SECONDARY},
        medianprops={"color": TEXT_SECONDARY},
        whiskerprops={"color": TEXT_SECONDARY},
        capprops={"color": TEXT_SECONDARY},
        flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "none", "markeredgecolor": NEUTRAL},
        showmeans=True,
        meanprops={"marker": "D", "markersize": 4, "markerfacecolor": SURFACE, "markeredgecolor": TEXT},
    )

    ax.tick_params(axis="x", labelrotation=20)
    ax.xaxis.label.set_visible(False)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
        label.set_rotation_mode("anchor")

    if relative:
        ax.set_ylabel(f"Relative to {relative} run")
    elif isinstance(runs[0], Runtime):
        ax.set_ylabel("Compiletime (ms)")
    else:
        ax.set_ylabel("Compiletime (ms)")

    ax.axhline(0, color=TEXT_SECONDARY, linestyle='--', linewidth=1, zorder=1, label='LLVM O0 Baseline')
    plt.title(title)
    save(fig, plot_name)

class Wrapper:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name

    def short_name(self):
        return self._name

def generate_box_plot_self_perf(plot_name, title, results, runs, VARIANTS, phase, relative="LLVM"):
    new_results = []
    for test, data in results.items():
        new_data = defaultdict()
        for backend, values in data['phases'].items():
            new_data[backend] = values[phase]
        new_results.append(dict(new_data))

    generate_box_plot(plot_name, title, new_results, [Wrapper(name) for name in results.keys()], VARIANTS,
                      relative=relative,
                      single_test=True)

DIVERGING = LinearSegmentedColormap.from_list("diverging", ["#2a78d6", "#f0efec", "#e34948"])
SEQUENTIAL = LinearSegmentedColormap.from_list("sequential", ["#f0efec", "#2a78d6", "#0d2f5c"])

BOOTSTRAP_SAMPLES = 10000


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


def generate_heatmap(plot_name, title, results, runs, relative="LLVM", limits=None):
    """Every benchmark (rows) with every run and backend (columns), sorted by the mean change over all columns. Missing
    cells are benchmarks a backend failed on. limits is the (low, high) ratio of the color scale, beyond which the
    colors saturate, by default symmetric around the baseline at the 98th percentile of the changes."""
    df = benchmark_frame(results, runs, relative)
    backends = ordered(set(df["Backend"]))
    run_names = [run.short_name() for run in runs]
    multi = len(run_names) > 1

    df["Column"] = [f"{run}\n{backend}" if multi else backend for run, backend in zip(df["Run"], df["Backend"])]
    columns = [f"{run}\n{backend}" if multi else backend for run in run_names for backend in backends]
    if relative:
        df["Value"] = np.log(df["Ratio"])
    else:
        df["Value"] = np.log10(df["Time (ms)"])
    table = df.pivot_table(index="Benchmark", columns="Column", values="Value").reindex(columns=columns)
    table = table.loc[table.mean(axis=1).sort_values().index]

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

    fig, ax = plt.subplots(figsize=(1.6 + 0.62 * len(columns), 1.2 + 0.19 * len(table)))
    sns.heatmap(table, annot=annot, fmt="", annot_kws={"fontsize": 6}, linewidths=0.5, linecolor=SURFACE, ax=ax,
                **style)
    ax.set_ylabel("")
    ax.set_xlabel("")
    ax.tick_params(axis="y", labelsize=7)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(False)
    # Separate the runs and name them above their group of columns, the columns only name the backend
    if multi:
        for r in range(1, len(run_names)):
            ax.axvline(r * len(backends), color=SURFACE, linewidth=4)
        ax.set_xticklabels(backends * len(run_names), rotation=30, ha="right", rotation_mode="anchor")
        for r, run in enumerate(run_names):
            ax.annotate(run, xy=((r + 0.5) * len(backends), 1), xycoords=("data", "axes fraction"),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8,
                        color=TEXT, annotation_clip=False)
        ax.set_title(title + (" (change in %)" if relative else " (ms)"), pad=16)
    else:
        ax.set_title(title + (" (change in %)" if relative else " (ms)"))
    save(fig, plot_name)


# Backend speedups of the reference curves in the scatter plot, math.inf is a backend taking no time at all
REFERENCE_SPEEDUPS = [2, 5, math.inf]


def codegen_shares(results, checks, relative):
    """{benchmark: share} of codegen in the compile time with the baseline: 1 - check / debug of the medians."""
    baseline = median_of_series(results[relative])
    check = median_of_series(checks)
    return {benchmark: 1 - check[benchmark] / ms for benchmark, ms in baseline.items() if benchmark in check}


def generate_scatter_plot(plot_name, title, results, runs, checks, relative="LLVM", labeled=3):
    """The change of every benchmark over the share of codegen in its compile time with the baseline, per run. checks
    are the results of the CheckTime runs with the same settings as runs, giving the time without codegen.

    The gray curves are a model: if codegen is a share s of the compile time and the backend makes it k times faster,
    the compile time changes to 1 - s * (1 - 1 / k). Codegen here is everything the check profile skips, including
    linking, which all backends share, so even an infinitely fast backend stays above its curve. The labeled benchmarks
    with the largest change are named."""
    df = benchmark_frame(results, runs, relative)
    shares = {run.short_name(): codegen_shares(result, check, relative)
              for run, result, check in zip(runs, results, checks)}
    df["Codegen share"] = [shares[run].get(benchmark) for run, benchmark in zip(df["Run"], df["Benchmark"])]
    missing = df["Codegen share"].isna().sum()
    if missing:
        print(f"Scatter {plot_name}: {missing} points without check results left out")
    df = df.dropna(subset=["Codegen share"])
    if df.empty:
        print(f"Scatter {plot_name}: no check results, skipped")
        return
    backends = ordered(set(df["Backend"]))
    run_names = [run.short_name() for run in runs]

    fig, axes = panels(len(run_names))
    share = np.linspace(0, 1, 101)
    for ax, run in zip(axes, run_names):
        for speedup in REFERENCE_SPEEDUPS:
            ax.plot(share * 100, 1 - share * (1 - 1 / speedup), color=GRID, linewidth=1, zorder=1)

        data = df[df["Run"] == run]
        for backend in backends:
            points = data[data["Backend"] == backend]
            ax.scatter(points["Codegen share"] * 100, points["Ratio"], s=14, color=variant_color(backend),
                       label=backend, edgecolors=SURFACE, linewidths=0.5, alpha=0.85, zorder=3)
        # Name the outliers of the first backend, the others are mostly the same benchmarks. A point close to an
        # already named one is skipped, the labels would overlap (e.g. ripgrep and ripgrep-nll).
        if labeled and backends:
            first = data[data["Backend"] == backends[0]]
            names = []
            for _, row in first.loc[np.abs(np.log(first["Ratio"])).sort_values(ascending=False).index].iterrows():
                if len(names) == labeled:
                    break
                x, y = row["Codegen share"], math.log(row["Ratio"])
                if any(abs(x - nx) < 0.15 and abs(y - ny) < 0.03 for nx, ny in names):
                    continue
                names.append((x, y))
                ax.annotate(row["Benchmark"], (row["Codegen share"] * 100, row["Ratio"]), xytext=(4, 0),
                            textcoords="offset points", fontsize=6, color=TEXT_SECONDARY, va="center")
        baseline_line(ax, relative)
        ax.grid(axis="x")
        ax.set_xlim(0, 100)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
        if len(run_names) > 1:
            ax.set_title(run, fontweight="normal")

    # The reference curves reach far below the data, only show the range of the data
    low, high = df["Ratio"].min() / 1.05, df["Ratio"].max() * 1.05
    axes[0].set_ylim(low, high)
    ratio_axis(axes[0])
    # Label each reference curve at its last point within the visible range
    for ax in axes:
        for speedup in REFERENCE_SPEEDUPS:
            curve = 1 - share * (1 - 1 / speedup)
            index = max(i for i in range(len(share)) if curve[i] >= low * 1.03 and share[i] <= 0.95)
            label = "\u221e" if speedup == math.inf else f"{speedup}\u00d7"
            ax.annotate(label, (share[index] * 100, curve[index]), fontsize=6, color=NEUTRAL, ha="left", va="bottom",
                        xytext=(2, 1), textcoords="offset points", zorder=2)
        if ax.get_subplotspec().is_first_col():
            ax.set_ylabel(f"Relative to {relative}")
    xlabel = f"Share of codegen in the compile time with {relative}"
    if len(run_names) == 1:
        axes[0].set_xlabel(xlabel)
    else:
        fig.supxlabel(xlabel, fontsize=9, color=TEXT_SECONDARY)
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(plt.Line2D([], [], color=GRID, linewidth=1))
    labels.append("Backend k\u00d7 faster")
    fig.legend(handles, labels, title="Backend", loc="outside right upper")
    fig.suptitle(title, fontweight="bold", fontsize=10)
    save(fig, plot_name)


def generate_heatmap_self_perf(plot_name, title, results, phases, relative="LLVM", limits=None):
    """generate_heatmap of several phases of self-profile results, one group of backend columns per phase."""
    generate_heatmap(plot_name, title, [self_perf_results(results, phase)[0] for phase in phases],
                     [Wrapper(phase) for phase in phases], relative, limits)
