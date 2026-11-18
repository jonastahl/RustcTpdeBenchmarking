"""Backend time with the default number of codegen units (256) relative to a single codegen unit, on different numbers
of cores. Every backend is compared with itself with one codegen unit on the same number of cores, so that the cells
show what splitting into codegen units gains (or costs) for that backend."""
from src.plots import Wrapper, generate_heatmap, relative_to_own_baseline
from src.runs import BackendTime

# A subset of the variants of compiletime_compare, whose runs with the default number of codegen units are reused
VARIANTS = ["LLVM", "LLVM O1", "TPDE", "TPDE inline", "TPDE inline,promote"]

# 32 is all physical cores of the benchmark machine, see compiletime_compare
CORES = [32, 2, 1]

# None is the default of the dev profile, 256 codegen units
CGU = None
BASELINE_CGU = 1
BASELINE = "1 Cgu"


def get_config():
    return [BackendTime(VARIANTS, cgu=cgu, cores=cores) for cores in CORES for cgu in (CGU, BASELINE_CGU)]


def evaluate(results):
    runs = get_config()
    by_settings = {(run.cores, run.cgu): result for run, result in zip(runs, results)}

    heatmap_results, heatmap_runs = [], []
    for cores in CORES:
        result, baseline = by_settings[(cores, CGU)], by_settings[(cores, BASELINE_CGU)]
        heatmap_results.append(relative_to_own_baseline(
            {variant: (series, baseline.get(variant, {})) for variant, series in result.items()}, BASELINE))
        heatmap_runs.append(Wrapper(f"{cores} Core" if cores == 1 else f"{cores} Cores"))

    generate_heatmap("cgu_compare_backend_heatmap",
                     "Backend time with 256 Cgus relative to 1 Cgu of the same backend",
                     heatmap_results, heatmap_runs,
                     relative=BASELINE)
