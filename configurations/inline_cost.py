"""How the cost factor of the TPDE inliner affects compile time, backend time, runtime and the time of the optimization,
all on the runtime benchmarks (their compile-time copies src.benchmarks.RT_PREFIX for the compile time, backend time and
the self-profiles)."""
from src.benchmarks import RT_PREFIX, runtime_benchmark_groups
from src.plots import Wrapper, generate_heatmap, runtime_per_group, self_perf_results, strip_prefix
from src.runs import BackendTime, CompileTime, Runtime, SelfProfile

VARIANTS = ["TPDE", "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100", "TPDE inline 500"]

BASELINE = "TPDE"

OPTIMIZATION = "Optimization"


def get_config():
    groups = runtime_benchmark_groups()
    return [
        CompileTime(VARIANTS, suite="runtime"),
        BackendTime(VARIANTS, suite="runtime"),
        Runtime(VARIANTS),
        SelfProfile([f"{RT_PREFIX}{group}" for group in groups], VARIANTS),
    ]


def evaluate(results):
    compiletime, backend, runtime, self_profile = results
    groups = runtime_benchmark_groups()
    optimization = strip_prefix(self_perf_results(self_profile, OPTIMIZATION)[0], RT_PREFIX)
    title = f"relative to {BASELINE}"

    backend = strip_prefix(backend, RT_PREFIX)
    generate_heatmap("inline_costs_heatmap",
                     f"Inlining cost factors {title}",
                     [backend, runtime_per_group(runtime, groups), optimization],
                     [Wrapper("Backend time"), Wrapper("Runtime"), Wrapper("Optimization time")],
                     relative=BASELINE)

    # And each separately
    generate_heatmap("inline_costs_compiletime_heatmap",
                     f"Compile time {title}",
                     [strip_prefix(compiletime, RT_PREFIX)], [Wrapper("Compile time")],
                     relative=BASELINE)
    generate_heatmap("inline_costs_backend_time_heatmap",
                     f"Backend time {title}",
                     [backend], [Wrapper("Backend time")],
                     relative=BASELINE)
    generate_heatmap("inline_costs_runtime_heatmap",
                     f"Runtime {title}",
                     [runtime], [Wrapper("Runtime")],
                     relative=BASELINE)
    generate_heatmap("inline_costs_opt_time_heatmap",
                     f"Optimization time {title}",
                     [optimization], [Wrapper("Optimization time")],
                     relative=BASELINE)
