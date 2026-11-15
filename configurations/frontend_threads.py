"""Compile time with the parallel frontend (-Zthreads), restricted to different numbers of cores. Everything is relative
to LLVM -O0 without the parallel frontend on the same number of cores, so that the LLVM columns show the effect of the
parallel frontend alone."""
from src.plots import Wrapper, generate_heatmap
from src.runs import CompileTime

VARIANTS = ["LLVM", "TPDE"]

# None keeps the default of rustc (no parallel frontend)
FRONTEND_THREADS = [None, 1, 100]

# For now, the 32 cores include hyperthreading siblings
CORES = [32, 8, 2]

# The baseline of every run: LLVM without the parallel frontend on the same number of cores
BASELINE_VARIANT = "LLVM"
BASELINE = "LLVM -O0, no -Zthreads"


def get_config():
    return [CompileTime(VARIANTS, cores=cores, threads=threads) for cores in CORES for threads in FRONTEND_THREADS]


def evaluate(results):
    runs = get_config()
    by_settings = {(run.cores, run.threads): result for run, result in zip(runs, results)}

    heatmap_results, heatmap_runs = [], []
    for run, result in zip(runs, results):
        baseline = by_settings[(run.cores, None)].get(BASELINE_VARIANT)
        if baseline is None:
            continue
        # LLVM without the parallel frontend is the baseline itself
        variants = {name: series for name, series in result.items()
                    if not (run.threads is None and name == BASELINE_VARIANT)}
        heatmap_results.append({BASELINE: baseline, **variants})
        heatmap_runs.append(Wrapper(run.short_name()))

    generate_heatmap("frontend_threads_heatmap",
                     "Compiletime with the parallel frontend",
                     heatmap_results, heatmap_runs,
                     relative=BASELINE)
