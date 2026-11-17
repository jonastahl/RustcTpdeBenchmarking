"""Compile time of all backends, depending on the number of cores and with a single codegen unit."""

from src.plots import codegen_shares, generate_heatmap
from src.runs import CheckTime, CompileTime, BackendTime

VARIANTS = ["LLVM", "LLVM O1", "Cranelift", "TPDE", "TPDE inline", "TPDE inline,promote", "TPDE MIR2", "TPDE inline MIR2", "TPDE inline,promote MIR2", "Custom LLVM", "Custom TPDE"]

# 32 is all physical cores of the benchmark machine. The cores 0..31 being distinct physical cores (no hyperthreading
# siblings) depends on the CPU numbering, check with `lscpu -e`.
CORES = [32, 8, 4, 2, 1]

# Settings of the runs: cores, and all cores with a single codegen unit
SETTINGS = [*[{"cores": cores} for cores in CORES], {"cgu": 1}]


def get_config():
    return [
        *[CompileTime(VARIANTS, **settings) for settings in SETTINGS],
        *[BackendTime(VARIANTS, **settings, suite="compile") for settings in SETTINGS],
        # The time without codegen, for the share of the backend in the compile time
        *[CheckTime(**settings) for settings in SETTINGS],
    ]


def evaluate(results):
    runs = get_config()
    compile_runs, backend_compile_runs, check_runs = runs[:len(SETTINGS)], runs[len(SETTINGS):len(SETTINGS)*2], runs[len(SETTINGS)*2:]
    compile_results, backend_compile_results, check_results = results[:len(SETTINGS)], results[len(SETTINGS):len(SETTINGS)*2], results[len(SETTINGS)*2:]
    title = "Compiletime relative to LLVM -O0"
    backend_title = "Backend compiletime relative to LLVM -O0"

    # The share of the backend (everything the check profile skips, linking included) in the compile time with LLVM,
    # per run at the end of each row
    shares = {run.short_name(): codegen_shares(result, check, "LLVM")
              for run, result, check in zip(compile_runs, compile_results, check_results) if "LLVM" in result}
    generate_heatmap("compiletime_compare_heatmap", title, compile_results, compile_runs,
                     extra=shares, extra_title="Backend share (LLVM)")

    generate_heatmap("compiletime_compare_backend_heatmap", backend_title, backend_compile_results, backend_compile_runs)
