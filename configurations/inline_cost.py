"""How the cost factor of the TPDE inliner affects compile time, runtime and the time of the optimization, all on the
runtime benchmarks (their compile-time copies src.benchmarks.RT_PREFIX for the compile time and the self-profiles)."""
from src.benchmarks import RT_PREFIX, runtime_benchmark_groups
from src.plots import Wrapper, compile_runtime_runs, generate_heatmap, self_perf_results, strip_prefix
from src.runs import CompileTime, Runtime, SelfProfile

VARIANTS = ["TPDE", "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100", "TPDE inline 500"]

# The default cost factor of the inliner. TPDE without inlining has (almost) no optimization time, so it would make a
# poor baseline for it.
BASELINE = "TPDE inline 50"

OPTIMIZATION = "Optimization"


def get_config():
    groups = runtime_benchmark_groups()
    return [
        CompileTime(VARIANTS, suite="runtime"),
        Runtime(VARIANTS),
        SelfProfile([f"{RT_PREFIX}{group}" for group in groups], VARIANTS),
    ]


def evaluate(results):
    compiletime, runtime, self_profile = results
    groups = runtime_benchmark_groups()
    optimization = strip_prefix(self_perf_results(self_profile, OPTIMIZATION)[0], RT_PREFIX)
    title = f"relative to {BASELINE}"

    # Everything together, one row per runtime benchmark group
    heatmap_results, heatmap_runs = compile_runtime_runs([compiletime], [runtime], [""], groups, RT_PREFIX)
    heatmap_results.append(optimization)
    heatmap_runs.append(Wrapper("Optimization time"))
    generate_heatmap("inline_costs_heatmap",
                     f"Inlining cost factors {title}",
                     heatmap_results, heatmap_runs,
                     relative=BASELINE)

    # And each separately
    generate_heatmap("inline_costs_compiletime_heatmap",
                     f"Compile time {title}",
                     [strip_prefix(compiletime, RT_PREFIX)], [Wrapper("Compile time")],
                     relative=BASELINE)
    generate_heatmap("inline_costs_runtime_heatmap",
                     f"Runtime {title}",
                     [runtime], [Wrapper("Runtime")],
                     relative=BASELINE)
    generate_heatmap("inline_costs_opt_time_heatmap",
                     f"Optimization time {title}",
                     [optimization], [Wrapper("Optimization time")],
                     relative=BASELINE)
