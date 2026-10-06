import re
import shutil
import subprocess
from pathlib import Path

from src.helper import env, run_task

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "rustc-perf/collector/compile-benchmarks/regex-automata-0.4.8"
BACKEND = ROOT / "backend_tpde/target/release/librustc_codegen_tpde.so"
TOOLCHAIN = "+nightly-2026-08-19"
TARGET = "x86_64-unknown-linux-gnu"

# Per backend: the rustc flag selecting it and the self-profile events that make up
# IR generation and object generation. The times of all listed events are summed up.
BACKENDS = {
    "LLVM": {
        "flag": "",
        "ir": ["codegen_module"],
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "TPDE": {
        "flag": f"-Zcodegen-backend={BACKEND}",
        "ir": ["codegen_module"],
        "obj": ["TPDE_module_codegen_emit_obj"],
    },
    "Cranelift": {
        "flag": "-Zcodegen-backend=cranelift",
        "ir": ["codegen cgu"],
        "obj": ["compile functions", "compile assembly", "write object file"],
    },
    "GCC": {
        "flag": "-Zcodegen-backend=gcc",
        "ir": ["codegen_module"],
        "obj": ["GCC_module_codegen_emit_obj"],
    },
}

UNITS = {"ns": 1e-9, "µs": 1e-6, "us": 1e-6, "ms": 1e-3, "s": 1.0}

def parse_seconds(text):
    match = re.fullmatch(r"([\d.]+)\s*(ns|µs|us|ms|s)", text.strip())
    return float(match.group(1)) * UNITS[match.group(2)]


def event_times(profile):
    """Inclusive time (the "Time" column of summarize) per event of one profile and its
    total cpu time, in seconds."""
    output = subprocess.run(["summarize", "summarize", str(profile)],
                            capture_output=True, text=True, check=True, env=env).stdout
    times = {}
    total = 0.0
    for line in output.splitlines():
        match = re.fullmatch(r"Total cpu time: (.+)", line.strip())
        if match:
            total = parse_seconds(match.group(1))
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        # Only the main table has "Self time | % of total time | Time | ..." columns
        if len(cells) < 4 or not re.fullmatch(r"[\d.]+\s*(ns|µs|us|ms|s)", cells[3]):
            continue
        times[cells[0].rstrip(" .")] = parse_seconds(cells[3])
    return times, total


def format_seconds(seconds):
    return f"{seconds * 1000:.1f} ms"


def print_table(rows):
    header = ["", "IR generation", "Obj generation", "Total cpu time"]
    table = [header] + [[name, *map(format_seconds, times)] for name, *times in rows]
    widths = [max(len(row[i]) for row in table) for i in range(4)]
    separator = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    print(separator)
    for index, row in enumerate(table):
        print("| " + " | ".join(row[0].ljust(widths[0]) if i == 0 else row[i].rjust(widths[i])
                                for i in range(4)) + " |")
        if index == 0:
            print(separator)
    print(separator)


def run_self_profile():
    """Self-profile regex-automata-0.4.8 (all crates) with every backend and print a summary table."""
    for name, backend in BACKENDS.items():
        key = name.lower()
        target_dir = BENCH_DIR / f"target-prof-{key}"
        prof_dir = BENCH_DIR / f"prof-{key}"

        # Start from scratch so that every crate is compiled and profiled
        shutil.rmtree(target_dir, ignore_errors=True)
        shutil.rmtree(prof_dir, ignore_errors=True)

        rustflags = f"-Znext-solver=coherence {backend['flag']} -Zself-profile={prof_dir.name}"
        run_task(f"Self profile on regex-automata-0.4.8 ({name})",
                 [
                     "env", f"RUSTFLAGS={rustflags}",
                     "cargo", TOOLCHAIN, "build", "--lib",
                     "--target", TARGET,
                     "--target-dir", target_dir.name,
                 ],
                 cwd=BENCH_DIR)

    rows = []
    for name, backend in BACKENDS.items():
        ir = obj = total = 0.0
        # Sum over all crates (dependencies included) and all codegen units
        for profile in (BENCH_DIR / f"prof-{name.lower()}").glob("regex_automata-*.mm_profdata"):
            times, profile_total = event_times(profile)
            total += profile_total
            ir += sum(times.get(event, 0.0) for event in backend["ir"])
            obj += sum(times.get(event, 0.0) for event in backend["obj"])
        rows.append((name, ir, obj, total))

    print()
    print_table(rows)
