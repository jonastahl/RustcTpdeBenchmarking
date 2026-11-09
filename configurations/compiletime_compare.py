"""Compile time of all backends, depending on the number of cores and with a single codegen unit."""

from src.plots import generate_box_plot
from src.runs import CompileTime

VARIANTS = ["LLVM", "Cranelift", "TPDE", "TPDE inline"]

# 32 is all physical cores of the benchmark machine. The cores 0..31 being distinct physical cores (no hyperthreading
# siblings) depends on the CPU numbering, check with `lscpu -e`.
CORES = [32, 8, 4, 2, 1]


def get_config():
    return [
        *[CompileTime(VARIANTS, cores=cores) for cores in CORES],
        # All cores
        CompileTime(VARIANTS, cgu=1),
    ]


def evaluate(results):
    runs = get_config()

    generate_box_plot("compiletime_compare",
                      "Compiletime relative to LLVM -O0",
                      results, runs, VARIANTS)
