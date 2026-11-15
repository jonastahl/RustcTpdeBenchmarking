"""Where the compile time goes: compiler phases of the backends."""
from src.plots import Wrapper, generate_heatmap, generate_heatmap_self_perf, self_perf_results
from src.runs import SelfProfile

BENCHMARKS = ["ripgrep-14.1.1", "regression-31157", "regex-automata-0.4.8", "cranelift-codegen-0.119.0"]
BACKENDS = ["LLVM", "TPDE", "TPDE inline", "TPDE inline,promote", "TPDE LLVM", "Cranelift"]

# The phases of src.self_profile, with the name of their plot
PHASES = {
    "IR generation": "ir_gen",
    "Optimization": "optimization",
    "Obj generation": "obj_gen",
    "Linking": "linking",
    "Total cpu time": "total",
}


def get_config():
    return [SelfProfile(BENCHMARKS, BACKENDS, ir_size=True)]


def evaluate(results):
    # All phases together
    generate_heatmap_self_perf("insights_phases_heatmap",
                               "Compiler phases relative to LLVM -O0",
                               results[0],
                               list(PHASES),
                               limits=(0.05, 1.1))

    # Each phase separately
    for phase, name in PHASES.items():
        generate_heatmap(f"insights_{name}_heatmap",
                         f"{phase} relative to LLVM -O0",
                         self_perf_results(results[0], phase), [Wrapper(phase)])
