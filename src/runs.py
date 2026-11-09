"""The runs a configuration can request in get_config. Variants are referenced by their name in
src.benchmarks.VARIANTS, self-profile backends by their name in src.self_profile.BACKENDS.

benchmark.py merges the runs of all configurations, so that nothing is run twice, and hands every configuration the
results of its runs in evaluate. The docstring of every run describes the shape of its results, all times are in
seconds. Variants and backends that failed are missing from the results."""
from dataclasses import dataclass

from src.benchmarks import VARIANTS
from src.self_profile import BACKENDS, IR_SIZE_LLVM, IR_SIZE_TPDE


def check_names(names, available, kind):
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ValueError(f"Unknown {kind}: {', '.join(unknown)} (available: {', '.join(available)})")


@dataclass(frozen=True)
class CompileTime:
    """Compile time (wall-time) of the compile-time benchmarks of rustc-perf with each variant.

    cgu: number of codegen units, cores: only use the cores 0..cores-1, threads: threads of the parallel frontend
    (-Zthreads). None keeps the default.

    Results: {variant: {benchmark: [samples]}}"""
    variants: tuple
    cgu: int | None = None
    cores: int | None = None
    threads: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "variants", tuple(self.variants))
        check_names(self.variants, VARIANTS, "variants")

    @property
    def key(self):
        """Runs with the same key share a database."""
        return self.cgu, self.cores, self.threads

    def name(self):
        return f"Compiletime[cores={self.cores} cgu={self.cgu} threads={self.threads}]"

    def short_name(self):
        names = []
        if self.cores is not None:
            if self.cores == 1:
                names.append(f"{self.cores} Core")
            else:
                names.append(f"{self.cores} Cores")
        if self.cgu is not None:
            if self.cgu == 1:
                names.append(f"{self.cgu} Cgu")
            else:
                names.append(f"{self.cgu} Cgus")
        if self.threads is not None:
            if self.threads == 1:
                names.append(f"{self.threads} Thread")
            else:
                names.append(f"{self.threads} Threads")
        return ", ".join(names)


@dataclass(frozen=True)
class Runtime:
    """Runtime (wall-time) of the runtime benchmarks of rustc-perf, compiled with each variant.

    Results: {variant: {benchmark: [samples]}}"""
    variants: tuple

    def __post_init__(self):
        object.__setattr__(self, "variants", tuple(self.variants))
        check_names(self.variants, VARIANTS, "variants")

    def name(self):
        return f"Runtime"

    def short_name(self):
        return ""


@dataclass(frozen=True)
class SelfProfile:
    """Self-profile of every crate of the given compile-time benchmarks with each backend, split into compiler phases.
    With ir_size, the size of the unoptimized IR of LLVM and TPDE is measured too, which needs both IR_SIZE_LLVM and
    IR_SIZE_TPDE among the backends.

    Results: {benchmark: {"phases": {backend: {phase: [samples]}},
                          "ir_size": {IR_SIZE_LLVM: bytes or None, IR_SIZE_TPDE: bytes or None} or None}}"""
    benchmarks: tuple
    backends: tuple
    ir_size: bool = False

    def __post_init__(self):
        object.__setattr__(self, "benchmarks", tuple(self.benchmarks))
        object.__setattr__(self, "backends", tuple(self.backends))
        check_names(self.backends, BACKENDS, "self-profile backends")
        if self.ir_size:
            check_names([IR_SIZE_LLVM, IR_SIZE_TPDE], self.backends, "backends of the IR size, missing")

    def name(self):
        return f"SelfProfile"