"""Where the compile time goes: compiler phases of the backends and the IR sizes of LLVM and TPDE."""
from src.runs import SelfProfile

BENCHMARKS = ["ripgrep-14.1.1", "regression-31157", "regex-automata-0.4.8", "cranelift-codegen-0.119.0"]
BACKENDS = ["LLVM", "LLVM O1", "TPDE", "TPDE inline", "TPDE LLVM"]


def get_config():
    return [SelfProfile(BENCHMARKS, BACKENDS, ir_size=True)]


def evaluate(results):
    self_profile, = results
