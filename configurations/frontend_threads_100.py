"""Compile time with the parallel frontend (-Zthreads), restricted to different numbers of cores."""
from src.plots import generate_box_plot
from src.runs import CompileTime

VARIANTS = ["LLVM", "TPDE"]

# None keeps the default of rustc (no parallel frontend)
FRONTEND_THREADS = [100]

# For now, the 32 cores include hyperthreading siblings
CORES = [32, 8, 2]

def get_config():
    return [CompileTime(VARIANTS, cores=cores, threads=threads) for threads in FRONTEND_THREADS for cores in CORES]

def evaluate(results):
    runs = get_config()

    generate_box_plot("frontend_threads_100",
                      "Compiletime relative to LLVM -O0",
                      results, runs, VARIANTS,
                      relative=False)