"""Compile time of all backends, depending on the number of cores and with a single codegen unit."""

from src.plots import backend_shares, generate_heatmap
from src.runs import CompileTime, BackendTime

VARIANTS = ["LLVM", "LLVM O1", "Cranelift", "TPDE", "TPDE inline", "TPDE inline,promote", "TPDE MIR2", "TPDE inline MIR2", "TPDE inline,promote MIR2", "Custom LLVM", "Custom TPDE"]

# 32 is all physical cores of the benchmark machine. The cores 0..31 being distinct physical cores (no hyperthreading
# siblings) depends on the CPU numbering, check with `lscpu -e`.
CORES = [32, 8, 4, 2, 1]

# Settings of the runs: cores, and all cores with a single codegen unit
SETTINGS = [*[{"cores": cores} for cores in CORES], {"cgu": 1}]


def get_config():
    return [
        *[CompileTime(VARIANTS, **settings) for settings in SETTINGS],
        *[BackendTime(VARIANTS, **settings) for settings in SETTINGS],
    ]


def evaluate(results):
    runs = get_config()
    compile_runs, backend_runs = runs[:len(SETTINGS)], runs[len(SETTINGS):]
    compile_results, backend_results = results[:len(SETTINGS)], results[len(SETTINGS):]

    # The share of the backend (without linking, see BackendTime) in the compile time with LLVM, per run at the end of
    # each row
    shares = {run.short_name(): backend_shares(compiletime, backendtime, "LLVM")
              for run, compiletime, backendtime in zip(compile_runs, compile_results, backend_results)
              if "LLVM" in compiletime and "LLVM" in backendtime}
    generate_heatmap("compiletime_compare_heatmap", "Compiletime relative to LLVM -O0", compile_results, compile_runs,
                     extra=shares, extra_title="Backend share (LLVM)")
    generate_heatmap("compiletime_compare_backend_heatmap", "Backend compiletime relative to LLVM -O0",
                     backend_results, backend_runs)
