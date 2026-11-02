"""Measures the compile time with the parallel frontend (-Zthreads), once without a core restriction and once restricted
to a limited number of cores.

The collector skips benchmarks that already have results, so an aborted run continues where it stopped. --rerun measures
everything again."""
import argparse
import shutil
from pathlib import Path

from benchmark import load_variants
from src.benchmarks import compiletime_results, run_compiletime_benchmark
from src.helper import TMP_DIR

ROOT = Path(__file__).resolve().parent

FRONTEND_THREADS = 100

# The number of cores of each run, None is no restriction
CORES = [None, 8]

# Result databases are relative to deps/rustc-perf
DB_DIR = ROOT / "deps/rustc-perf"


def db_name(cores):
    return f"results_threads_{FRONTEND_THREADS}{f'_cores_{cores}' if cores else ''}.db"


def suffix(cores):
    return f" {FRONTEND_THREADS} threads{f' {cores} cores' if cores else ''}"


def results():
    for cores in CORES:
        # Skip the databases of benchmarks that did not run yet
        if (DB_DIR / db_name(cores)).exists():
            compiletime_results(db=db_name(cores), suffix=suffix(cores))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rerun", action="store_true", help="Delete the previous results and rerun")
    parser.add_argument("--results", action="store_true", help="Only print the results of previous runs")
    args = parser.parse_args()

    if args.results:
        results()
        return

    config = load_variants()
    try:
        for cores in CORES:
            run_compiletime_benchmark(config, rerun=args.rerun, db=db_name(cores), suffix=suffix(cores), cores=cores,
                                      threads=FRONTEND_THREADS)
    finally:
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    results()


if __name__ == '__main__':
    main()
