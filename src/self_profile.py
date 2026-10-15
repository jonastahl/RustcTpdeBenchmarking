import re
import shutil
import subprocess
from pathlib import Path

from src.helper import env, run_task, print_table

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "deps/rustc-perf/collector/compile-benchmarks/regex-automata-0.4.8"
BACKEND_TPDE = ROOT / "deps/RustcTpde/target/release/librustc_codegen_tpde_dylib.so"
BACKEND_TPDE_LLVM = ROOT / "deps/rustc_codegen_llvm_tpde/dist/lib/librustc_codegen_tpde.so"
TOOLCHAIN = "+nightly-2026-08-19"
TARGET = "x86_64-unknown-linux-gnu"

# LLVM's middle-end optimization of each codegen unit
LLVM_OPT = ["LLVM_module_optimize"]

# The ThinLTO events only occur with opt-level > 0, where rustc runs local ThinLTO across the codegen units of a crate.
# LLVM_thin_lto_optimize already includes the nested import/rename/LLVM_lto_optimize events.
LLVM_LTO = ["LLVM_thin_lto_global_analysis", "LLVM_thin_lto_optimize"]

# Linking is done by rustc_codegen_ssa for all backends. For the rlibs built here this is only archiving.
LINK = ["link"]

# Per backend: the rustc flag selecting it (and optionally a custom rustc binary and opt-level) and the self-profile events that make up
# IR generation, optimization, LTO and object generation. The times of all listed events are summed up.
BACKENDS = {
    "LLVM": {
        "flag": "",
        "ir": ["codegen_module"],
        "opt": LLVM_OPT,
        "lto": LLVM_LTO,
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "LLVM O1": {
        "flag": "",
        "opt_level": 1,
        "ir": ["codegen_module"],
        "opt": LLVM_OPT,
        "lto": LLVM_LTO,
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "LLVM O2": {
        "flag": "",
        "opt_level": 2,
        "ir": ["codegen_module"],
        "opt": LLVM_OPT,
        "lto": LLVM_LTO,
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "LLVM O3": {
        "flag": "",
        "opt_level": 3,
        "ir": ["codegen_module"],
        "opt": LLVM_OPT,
        "lto": LLVM_LTO,
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "TPDE": {
        "flag": f"-Zcodegen-backend={BACKEND_TPDE}",
        "ir": ["codegen_module"],
        "opt": ["TPDE_module_optimize"],
        "lto": [],
        "obj": ["TPDE_module_codegen_emit_obj"],
    },
    "TPDE LLVM": {
        "flag": f"-Zcodegen-backend={BACKEND_TPDE_LLVM}",
        "ir": ["codegen_module"],
        "opt": LLVM_OPT,
        "lto": LLVM_LTO,
        "obj": ["LLVM_module_codegen_emit_obj"],
    },
    "Cranelift": {
        "flag": "-Zcodegen-backend=cranelift",
        "ir": ["codegen cgu"],
        "opt": [],
        "lto": [],
        "obj": ["compile functions", "compile assembly", "write object file"],
    },
}

HEADER_IR = "IR generation"
HEADER_OPT = "Optimization"
HEADER_LTO = "LTO"
HEADER_OBJ = "Obj generation"
HEADER_LINK = "Linking"
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

def create_flamegraph(name):
    """Render the self-profile of the main crate of one backend (all events) to flamegraph-<backend>.svg in the project root."""
    key = name.lower().replace(" ", "-")
    prof_dir = BENCH_DIR / f"prof-{key}"
    profile = max(prof_dir.glob("regex_automata-*.mm_profdata"), key=lambda path: path.stat().st_size)
    # The flamegraph tool takes the profile path without extension and writes rustc.svg into the cwd
    run_task(f"Create flamegraph of {name}",
             ["flamegraph", profile.stem],
             cwd=prof_dir)
    shutil.move(prof_dir / "rustc.svg", ROOT / f"flamegraph-{key}.svg")

def run_self_profile(rerun=False):
    """Self-profile regex-automata-0.4.8 (all crates) with every backend and print a summary table."""
    for name, backend in BACKENDS.items():
        key = name.lower().replace(" ", "-")
        target_dir = BENCH_DIR / f"target-prof-{key}"
        prof_dir = BENCH_DIR / f"prof-{key}"

        # Start from scratch so that every crate is compiled and profiled
        if rerun:
            shutil.rmtree(target_dir, ignore_errors=True)
            shutil.rmtree(prof_dir, ignore_errors=True)

        rustflags = f"-Znext-solver=coherence {backend['flag']} -Zself-profile={prof_dir.name}"
        run_task(f"Self profile on regex-automata-0.4.8 ({name})",
                 [
                     "env", f"RUSTFLAGS={rustflags}",
                     *([f"RUSTC={backend['rustc']}"] if "rustc" in backend else []),
                     *([f"CARGO_PROFILE_DEV_OPT_LEVEL={backend['opt_level']}"] if "opt_level" in backend else []),
                     "cargo", TOOLCHAIN, "build", "--lib",
                     "--target", TARGET,
                     "--target-dir", target_dir.name,
                 ],
                 cwd=BENCH_DIR)

def self_profile_results():
    rows = {}
    for name, backend in BACKENDS.items():
        ir = opt = lto = obj = link = total = 0.0
        # Sum over all crates (dependencies included) and all codegen units
        for profile in (BENCH_DIR / f"prof-{name.lower().replace(' ', '-')}").glob("regex_automata-*.mm_profdata"):
            times, profile_total = event_times(name, profile)
            total += profile_total
            ir += sum(times.get(event, 0.0) for event in backend["ir"])
            opt += sum(times.get(event, 0.0) for event in backend["opt"])
            lto += sum(times.get(event, 0.0) for event in backend["lto"])
            obj += sum(times.get(event, 0.0) for event in backend["obj"])
            link += sum(times.get(event, 0.0) for event in LINK)
        rows[name] = {HEADER_IR: ir, HEADER_OPT: opt, HEADER_LTO: lto, HEADER_OBJ: obj, HEADER_LINK: link, HEADER_TOTAL: total}

    print_table(rows, "Self profile")

    for name in BACKENDS:
        create_flamegraph(name)
