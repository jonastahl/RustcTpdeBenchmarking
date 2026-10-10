import re
import shutil
import subprocess
from pathlib import Path

from src.helper import env, run_task, print_table

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "deps/rustc-perf/collector/compile-benchmarks/regex-automata-0.4.8"
BACKEND = ROOT / "deps/RustcTpde/target/release/librustc_codegen_tpde_dylib.so"
BACKEND_LLVM_TPDE = ROOT / "deps/backend_tpde_llvm/build/cg_tpde/x86_64-unknown-linux-gnu/release/librustc_codegen_tpde.so"
RUSTC_TPDE = ROOT / "deps/RustcTpde/target/release/rustc_tpde"
TOOLCHAIN = "+nightly-2026-08-19"
TARGET = "x86_64-unknown-linux-gnu"

# Per backend: the rustc flag selecting it (and optionally a custom rustc binary) and the self-profile events that make up
# IR generation and object generation. The times of all listed events are summed up.
BACKENDS = {
    "LLVM": {
        "flag": "",
        "ir": ["codegen_module"],
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "TPDE": {
        "flag": "",
        "rustc": str(RUSTC_TPDE),
        "ir": ["codegen_module"],
        "obj": ["TPDE_module_codegen_emit_obj"],
    },
    "TPDE dynamic": {
        "flag": f"-Zcodegen-backend={BACKEND}",
        "ir": ["codegen_module"],
        "obj": ["TPDE_module_codegen_emit_obj"],
    },
    "LLVM-TPDE dynamic": {
        "flag": f"-Zcodegen-backend={BACKEND_LLVM_TPDE}",
        "ir": ["codegen_module"],
        "obj": ["TPDE_LLVM_module_codegen_emit_obj"]
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

HEADER_IR = "IR generation"
HEADER_OBJ = "Obj generation"
HEADER_TOTAL = "Total cpu time"

UNITS = {"ns": 1e-9, "µs": 1e-6, "us": 1e-6, "ms": 1e-3, "s": 1.0}

def parse_seconds(text):
    match = re.fullmatch(r"([\d.]+)\s*(ns|µs|us|ms|s)", text.strip())
    return float(match.group(1)) * UNITS[match.group(2)]

def event_times(name, profile):
    """Inclusive time (the "Time" column of summarize) per event of one profile and its
    total cpu time, in seconds."""
    output = run_task("Fetch self perf results of " + name,
                      ["summarize", "summarize", str(profile)])
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

def run_self_profile():
    """Self-profile regex-automata-0.4.8 (all crates) with every backend and print a summary table."""
    for name, backend in BACKENDS.items():
        key = name.lower().replace(" ", "-")
        target_dir = BENCH_DIR / f"target-prof-{key}"
        prof_dir = BENCH_DIR / f"prof-{key}"

        # Start from scratch so that every crate is compiled and profiled
        shutil.rmtree(target_dir, ignore_errors=True)
        shutil.rmtree(prof_dir, ignore_errors=True)

        rustflags = f"-Znext-solver=coherence {backend['flag']} -Zself-profile={prof_dir.name}"
        run_task(f"Self profile on regex-automata-0.4.8 ({name})",
                 [
                     "env", f"RUSTFLAGS={rustflags}",
                     *([f"RUSTC={backend['rustc']}"] if "rustc" in backend else []),
                     "cargo", TOOLCHAIN, "build", "--lib",
                     "--target", TARGET,
                     "--target-dir", target_dir.name,
                 ],
                 cwd=BENCH_DIR)

    rows = {}
    for name, backend in BACKENDS.items():
        ir = obj = total = 0.0
        # Sum over all crates (dependencies included) and all codegen units
        for profile in (BENCH_DIR / f"prof-{name.lower().replace(' ', '-')}").glob("regex_automata-*.mm_profdata"):
            times, profile_total = event_times(name, profile)
            total += profile_total
            ir += sum(times.get(event, 0.0) for event in backend["ir"])
            obj += sum(times.get(event, 0.0) for event in backend["obj"])
        rows[name] = {HEADER_IR: ir, HEADER_OBJ: obj, HEADER_TOTAL: total}

    print_table(rows, "Self profile")
