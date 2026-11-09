import math
import statistics
from pathlib import Path

import matplotlib

from src.runs import CompileTime

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
NEUTRAL = "#8a8984"

VARIANT_ORDER = ["LLVM", "LLVM O1", "LLVM O2", "LLVM O3", "TPDE", "TPDE inline",
                 "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100", "TPDE inline 500",
                 "TPDE LLVM", "Cranelift"]
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


def medians_of_backend(backends):
    return {key: median_of_series(backends) for (key, backends) in backends.items()}


def merge_dicts(a, b):
    return {k: (a.get(k), b.get(k)) for k in a.keys() | b.keys()}


def generate_box_plot(plot_name, title, results, runs, VARIANTS, relative=True):
    # Reduce everything to median
    results = [medians_of_backend(backend) for backend in results]

    fig, ax = plt.subplots()
    plot_data = []

    # Compute data and print
    for run, result in zip(runs, results):
        print(f"{run.name()}:")

        llvm = result["LLVM"]
        print(f"LLVM: {statistics.geometric_mean(llvm.values())}")
        for name, series in result.items():
            if relative and name == "LLVM":
                continue

            print(f"{name}")

            merge = merge_dicts(llvm, series)
            existing = {key: (a, b) for (key, (a, b)) in merge.items() if a is not None and b is not None}

            missing = sum(1 for a, b in merge.values() if b is None)
            if missing > 0:
                print(f"  missing: {missing}")

            # absolute values
            mean = statistics.geometric_mean(series.values())
            diff = mean - statistics.geometric_mean([a for (a, _) in existing.values()])
            diffs = [b - a for (a, b) in existing.values()]
            min_diff = min(diffs)
            max_diff = max(diffs)
            print(f"  absolute: mean: {mean:.2f}ms, diff: {diff:.2f}ms, min: {min_diff:.2f}ms, max: {max_diff:.2f}ms")

            ratio = [b / a * 100 for a, b in existing.values()]
            min_val = min(ratio) - 100
            max_val = max(ratio) - 100
            mean = statistics.geometric_mean(ratio) - 100
            geomstdev = math.exp(statistics.stdev([math.log(r) for r in ratio]))
            print(
                f"  relative: mean: {mean:.2f}%, geom-stdev: {geomstdev:.2f}, min: {min_val:.2f}%, max: {max_val:.2f}%")

            if relative:
                for r in ratio:
                    plot_data.append({
                        "Run": run.short_name(),
                        "Backend": name,
                        "Relative Change (%)": r - 100
                    })
            else:
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
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
        label.set_rotation_mode("anchor")

    ax.set_ylabel("Relative to LLVM O0 run")
    ax.axhline(0, color=TEXT_SECONDARY, linestyle='--', linewidth=1, zorder=1, label='LLVM O0 Baseline')
    plt.title(title)
    save(fig, plot_name)
