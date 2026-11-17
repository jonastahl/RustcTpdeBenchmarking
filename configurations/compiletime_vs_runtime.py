"""Compile time and runtime of the same code: the runtime benchmarks of rustc-perf, whose groups are also run as
compile-time benchmarks (src.benchmarks.RT_PREFIX), with the default number of codegen units (256) and with one."""

from src.benchmarks import RT_PREFIX, runtime_benchmark_groups
from src.plots import generate_compile_runtime_heatmap
from src.runs import Runtime, BackendTime

VARIANTS = ["LLVM", "LLVM O1", "Cranelift", "TPDE", "TPDE inline", "TPDE inline,promote", "TPDE MIR2",
            "TPDE inline MIR2", "TPDE inline,promote MIR2"]

# None is the default of the dev profile, 256 codegen units
CGUS = [None, 1]


def get_config():
    return [
        *[BackendTime(VARIANTS, cgu=cgu, suite="runtime") for cgu in CGUS],
        *[Runtime(VARIANTS, cgu=cgu) for cgu in CGUS],
    ]


def evaluate(results):
    runs = get_config()
    compiletimes, runtimes = results[:len(CGUS)], results[len(CGUS):]
    settings = [run.short_name() for run in runs[len(CGUS):]]

    generate_compile_runtime_heatmap("compiletime_vs_runtime_heatmap",
                                     "Compile time and runtime relative to LLVM -O0",
                                     compiletimes, runtimes, settings, runtime_benchmark_groups(), prefix=RT_PREFIX)
    for setting, compiletime, runtime in zip(settings, compiletimes, runtimes):
        generate_compile_runtime_heatmap(f"compiletime_vs_runtime_cgu{setting.split()[0]}_heatmap",
                                         f"Compile time and runtime relative to LLVM -O0, {setting}",
                                         [compiletime], [runtime], [""], runtime_benchmark_groups(), prefix=RT_PREFIX)
