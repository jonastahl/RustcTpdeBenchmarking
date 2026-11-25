"""Which LLVM passes of the O1 pipeline bring which improvements in compile time and runtime: the variants of
src.benchmarks.LLVM_PASS_VARIANTS on the runtime benchmarks, like compiletime_vs_runtime, relative to LLVM -O0.

`python3 -m configurations.llvm_passes` prints the passes of the O1 pipeline, from which the variants take the
parameters of their passes."""
from pathlib import Path

from src.benchmarks import RT_PREFIX, runtime_benchmark_groups, LLVM_PASS_OPTIMIZATIONS
from src.helper import run_task
from src.plots import generate_compile_runtime_heatmap
from src.runs import BackendTime, Runtime

VARIANTS = ["LLVM", "LLVM O1", *LLVM_PASS_OPTIMIZATIONS]

# None is the default of the dev profile, 256 codegen units
CGUS = [None]


def get_config():
    return [
        *[BackendTime(VARIANTS, cgu=cgu, suite="runtime") for cgu in CGUS],
        *[Runtime(VARIANTS, cgu=cgu) for cgu in CGUS],
    ]


def evaluate(results):
    runs = get_config()
    compiletimes, runtimes = results[:len(CGUS)], results[len(CGUS):]
    settings = [run.short_name() for run in runs[len(CGUS):]]
    for setting, compiletime, runtime in zip(settings, compiletimes, runtimes):
        suffix = f"_cgu{setting.split()[0]}" if len(CGUS) > 1 else ""
        generate_compile_runtime_heatmap(f"llvm_passes{suffix}_heatmap",
                                         f"LLVM passes: backend compile time and runtime relative to LLVM -O0, {setting}",
                                         [compiletime], [runtime], [""], runtime_benchmark_groups(), prefix=RT_PREFIX)


TOOLCHAIN = "+nightly-2026-10-28"
TARGET = "x86_64-unknown-linux-gnu"
PIPELINE_LEVEL = "O1"


def format_pipeline(pipeline):
    """One pass per line, nested passes indented."""
    lines, current, nesting, params = [], "", 0, 0

    def flush():
        nonlocal current
        if current:
            lines.append("  " * nesting + current)
        current = ""

    for char in pipeline:
        # Parameters like simplifycfg<...> are part of their pass
        if char == "<":
            params += 1
        elif char == ">":
            params -= 1
        if params == 0 and char == "(":
            current += char
            flush()
            nesting += 1
        elif params == 0 and char == ",":
            flush()
        elif params == 0 and char == ")":
            flush()
            nesting -= 1
            current = char
        else:
            current += char
    flush()
    return "\n".join(lines)


def print_pipeline():
    """Prints the passes of the PIPELINE_LEVEL pipeline and writes them to results/."""
    sysroot = run_task("Finding the sysroot", ["rustc", TOOLCHAIN, "--print", "sysroot"])
    opt = Path(sysroot) / "lib/rustlib" / TARGET / "bin/opt"
    if not opt.exists():
        raise SystemExit(f"opt not found: {opt}\nInstall it with: rustup component add llvm-tools {TOOLCHAIN}")
    pipeline = run_task(f"Printing the {PIPELINE_LEVEL} pipeline",
                        [str(opt), f"-passes=default<{PIPELINE_LEVEL}>", "-print-pipeline-passes", "-disable-output",
                         "/dev/null"])
    path = Path(__file__).resolve().parent.parent / "results" / f"{PIPELINE_LEVEL}_pipeline.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text(pipeline + "\n\n" + format_pipeline(pipeline) + "\n")
    print(format_pipeline(pipeline))
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    print_pipeline()
