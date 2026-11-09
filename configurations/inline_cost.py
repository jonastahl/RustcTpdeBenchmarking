"""How the cost factor of the TPDE inliner affects compile time and runtime."""
from src.plots import generate_box_plot
from src.runs import CompileTime, Runtime, SelfProfile


VARIANTS_comp = ["LLVM", "TPDE", "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100",
            "TPDE inline 500"]
VARIANTS_run = ["LLVM", "LLVM O1", "TPDE", "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100",
            "TPDE inline 500"]


def get_config():
    return [
        CompileTime(VARIANTS_comp, cgu=1),
        Runtime(VARIANTS_run),
        SelfProfile(["cranelift-codegen-0.119.0", "regex-automata-0.4.8"], VARIANTS_comp),
    ]


def evaluate(results):
    runs = get_config()

    generate_box_plot("inline_costs_compiletime",
                      "Compiletime for different inline costs relative to LLVM -O0",
                      [results[0]], [runs[0]], VARIANTS_comp)

    generate_box_plot("inline_costs_runtime",
                      "Runtime for different inline costs relative to LLVM -O0",
                      [results[1]], [runs[1]], VARIANTS_run)