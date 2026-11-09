"""Where the compile time goes: compiler phases of the backends and the IR sizes of LLVM and TPDE."""
from src.plots import generate_box_plot_self_perf
from src.runs import SelfProfile

BENCHMARKS = ["ripgrep-14.1.1", "regression-31157", "regex-automata-0.4.8", "cranelift-codegen-0.119.0"]
BACKENDS = ["LLVM", "TPDE", "TPDE inline", "TPDE LLVM", "Cranelift"]


def get_config():
    return [SelfProfile(BENCHMARKS, BACKENDS, ir_size=True)]

def evaluate(results):
    runs = get_config()

    generate_box_plot_self_perf("insights_ir_gen",
                                "IR generation relative to LLVM -O0",
                                results[0], runs[0], BACKENDS,
                                "IR generation")

    generate_box_plot_self_perf("insights_linking",
                                "Link time relative to LLVM -O0",
                                results[0], runs[0], BACKENDS,
                                "Linking")

    generate_box_plot_self_perf("insights_obj_gen",
                                "Object generation relative to LLVM -O0",
                                results[0], runs[0], BACKENDS,
                                "Obj generation")
