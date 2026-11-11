"""Where the compile time goes: compiler phases of the backends and the IR sizes of LLVM and TPDE."""
from src.plots import generate_distribution_plot_self_perf
from src.runs import SelfProfile

BENCHMARKS = ["ripgrep-14.1.1", "regression-31157", "regex-automata-0.4.8", "cranelift-codegen-0.119.0"]
BACKENDS = ["LLVM", "TPDE", "TPDE inline", "TPDE inline,promote", "TPDE LLVM", "Cranelift"]


def get_config():
    return [SelfProfile(BENCHMARKS, BACKENDS, ir_size=True)]

def evaluate(results):
    runs = get_config()

    generate_distribution_plot_self_perf("insights_ir_gen_distribution",
                                         "IR generation relative to LLVM -O0",
                                         results[0], runs[0],
                                         "IR generation")

    generate_distribution_plot_self_perf("insights_linking_distribution",
                                         "Link time relative to LLVM -O0",
                                         results[0], runs[0],
                                         "Linking")

    generate_distribution_plot_self_perf("insights_obj_gen_distribution",
                                         "Object generation relative to LLVM -O0",
                                         results[0], runs[0],
                                         "Obj generation")
