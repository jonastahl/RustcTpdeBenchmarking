"""Compile time of all backends, depending on the number of cores and with a single codegen unit."""

from src.plots import generate_distribution_plot, generate_heatmap, generate_scatter_plot
from src.runs import CheckTime, CompileTime

VARIANTS = ["LLVM", "Cranelift", "TPDE", "TPDE inline"]

# 32 is all physical cores of the benchmark machine. The cores 0..31 being distinct physical cores (no hyperthreading
# siblings) depends on the CPU numbering, check with `lscpu -e`.
CORES = [32, 8, 4, 2, 1]

# Settings of the runs: cores, and all cores with a single codegen unit
SETTINGS = [*[{"cores": cores} for cores in CORES], {"cgu": 1}]


def get_config():
    return [
        *[CompileTime(VARIANTS, **settings) for settings in SETTINGS],
        # The time without codegen, for the share of codegen in the scatter plot
        *[CheckTime(**settings) for settings in SETTINGS],
    ]


def evaluate(results):
    runs = get_config()
    compile_runs, check_runs = runs[:len(SETTINGS)], runs[len(SETTINGS):]
    compile_results, check_results = results[:len(SETTINGS)], results[len(SETTINGS):]
    title = "Compiletime relative to LLVM -O0"

    generate_distribution_plot("compiletime_compare_distribution", title, compile_results, compile_runs)
    generate_scatter_plot("compiletime_compare_scatter", title, compile_results, compile_runs, check_results)
    generate_heatmap("compiletime_compare_heatmap", title, compile_results, compile_runs)
