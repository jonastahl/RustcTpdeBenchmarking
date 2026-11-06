"""How the cost factor of the TPDE inliner affects compile time and runtime."""
from src.runs import CompileTime, Runtime, SelfProfile

VARIANTS = ["LLVM", "LLVM O1", "TPDE", "TPDE inline 10", "TPDE inline 20", "TPDE inline 50", "TPDE inline 100",
            "TPDE inline 500"]


def get_config():
    return [
        Runtime(VARIANTS),
        CompileTime(VARIANTS, cgu=1),
        SelfProfile(["cranelift-codegen-0.119.0", "regex-automata-0.4.8"], VARIANTS),
    ]


def evaluate(results):
    runtime, compiletime_cgu_1, self_profile = results
