"""How the cost factor of the TPDE inliner affects compile time and runtime."""
from src.plots import generate_distribution_plot, generate_distribution_plot_self_perf, generate_heatmap
from src.runs import CompileTime, Runtime, SelfProfile


VARIANTS = ["TPDE", "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100", "TPDE inline 500"]


def get_config():
    return [
        CompileTime(VARIANTS, cgu=1),
        Runtime(VARIANTS),
        SelfProfile(["cranelift-codegen-0.119.0", "regex-automata-0.4.8"], VARIANTS),
    ]


def evaluate(results):
    runs = get_config()

    generate_distribution_plot("inline_costs_compiletime_distribution",
                               "Compiletime for different costs for inlining",
                               [results[0]], [runs[0]],
                               relative="TPDE")

    generate_distribution_plot("inline_costs_runtime_distribution",
                               "Runtime for different costs for inlining",
                               [results[1]], [runs[1]],
                               relative="TPDE")

    generate_distribution_plot_self_perf("inline_costs_opt_time_distribution",
                                         "Time taken for optimization (ms)",
                                         results[2], runs[2],
                                         "Optimization",
                                         relative=None)

