"""Compile time and backend time of the custom rustc builds, each relative to the stock rustc with the same backend on
the same number of cores: Custom LLVM against LLVM and Custom TPDE against TPDE."""
from src.plots import Wrapper, generate_heatmap, relative_to_own_baseline
from src.runs import BackendTime, CompileTime

# Each custom variant with the stock variant it is compared with
PAIRS = {"Custom LLVM": "LLVM", "Custom TPDE": "TPDE"}
VARIANTS = [*PAIRS.values(), *PAIRS]

# The same cores as compiletime_compare, whose runs of the stock variants are reused
CORES = [32, 2, 1]

BASELINE = "Stock rustc"


def get_config():
    return [
        *[CompileTime(VARIANTS, cores=cores) for cores in CORES],
        *[BackendTime(VARIANTS, cores=cores) for cores in CORES],
    ]


def relative_results(results):
    """The results of the runs of one kind (one per entry of CORES) for generate_heatmap, every custom variant relative
    to its stock variant on the same number of cores."""
    return [relative_to_own_baseline({custom: (result.get(custom, {}), result.get(stock, {}))
                                      for custom, stock in PAIRS.items()}, BASELINE)
            for result in results]


def evaluate(results):
    runs = [Wrapper(f"{cores} Core" if cores == 1 else f"{cores} Cores") for cores in CORES]
    compile_results, backend_results = results[:len(CORES)], results[len(CORES):]

    generate_heatmap("custom_compare_heatmap",
                     "Compile time of the custom rustc relative to stock rustc with the same backend",
                     relative_results(compile_results), runs, relative=BASELINE)
    generate_heatmap("custom_compare_backend_heatmap",
                     "Backend time of the custom rustc relative to stock rustc with the same backend",
                     relative_results(backend_results), runs, relative=BASELINE)
