import re
import shutil
import subprocess
from pathlib import Path

from src.helper import env, run_task, print_table

ROOT = Path(__file__).resolve().parent.parent
BENCH_ROOT = ROOT / "deps/rustc-perf/collector/compile-benchmarks"
BENCHMARKS = ["ripgrep-14.1.1", "regression-31157", "regex-automata-0.4.8", "cranelift-codegen-0.119.0"]
FLAMEGRAPH_DIR = ROOT / "flamegraphs"
BACKEND_TPDE = ROOT / "deps/RustcTpde/target/release/librustc_codegen_tpde_dylib.so"
BACKEND_TPDE_NO_CACHE = ROOT / "deps/RustcTpde/target-no-cache/release/librustc_codegen_tpde_dylib.so"
BACKEND_TPDE_INLINE = ROOT / "deps/RustcTpde/target-inline/release/librustc_codegen_tpde_dylib.so"
BACKEND_TPDE_LLVM = ROOT / "deps/rustc_codegen_llvm_tpde/dist/lib/librustc_codegen_tpde.so"
TOOLCHAIN = "+nightly-2026-08-19"
TARGET = "x86_64-unknown-linux-gnu"

# LLVM's middle-end optimization of each codegen unit
LLVM_OPT = ["LLVM_module_optimize"]

# The ThinLTO events only occur with opt-level > 0, where rustc runs local ThinLTO across the codegen units of a crate.
# LLVM_thin_lto_optimize already includes the nested import/rename/LLVM_lto_optimize events.
LLVM_LTO = ["LLVM_thin_lto_global_analysis", "LLVM_thin_lto_optimize"]

# Linking is done by rustc_codegen_ssa for all backends. For libraries this is only archiving the rlib, for binaries
# (ripgrep) it includes running the linker.
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
    "TPDE no-cache": {
        "flag": f"-Zcodegen-backend={BACKEND_TPDE_NO_CACHE}",
        "ir": ["codegen_module"],
        "opt": ["TPDE_module_optimize"],
        "lto": [],
        "obj": ["TPDE_module_codegen_emit_obj"],
    },
    "TPDE inline": {
        "flag": f"-Zcodegen-backend={BACKEND_TPDE_INLINE}",
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

def event_times(description, profile):
    """Inclusive time (the "Time" column of summarize) per event of one profile and its
    total cpu time, in seconds."""
    output = run_task("Fetch self perf results of " + description,
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

def backend_key(name):
    return name.lower().replace(" ", "-")

def profiles(benchmark, name):
    """The self-profiles of all crates compiled for one benchmark with one backend. The `___` ones stem from cargo
    querying rustc for its configuration and are skipped."""
    prof_dir = BENCH_ROOT / benchmark / f"prof-{backend_key(name)}"
    return [profile for profile in prof_dir.glob("*.mm_profdata") if not profile.name.startswith("___-")]

def create_flamegraph(benchmark, name):
    """Render the self-profile of the largest crate of one benchmark and backend (all events) to
    flamegraphs/<benchmark>-<backend>.svg."""
    profile = max(profiles(benchmark, name), key=lambda path: path.stat().st_size)
    # The flamegraph tool takes the profile path without extension and writes rustc.svg into the cwd
    run_task(f"Create flamegraph of {benchmark} ({name})",
             ["flamegraph", profile.stem],
             cwd=profile.parent)
    FLAMEGRAPH_DIR.mkdir(exist_ok=True)
    shutil.move(profile.parent / "rustc.svg", FLAMEGRAPH_DIR / f"{benchmark}-{backend_key(name)}.svg")

def run_self_profile(rerun=False):
    """Self-profile every benchmark (all crates) with every backend. Backends that fail to compile a benchmark are
    skipped for it."""
    for benchmark in BENCHMARKS:
        bench_dir = BENCH_ROOT / benchmark
        for name, backend in BACKENDS.items():
            key = backend_key(name)
            target_dir = bench_dir / f"target-prof-{key}"
            prof_dir = bench_dir / f"prof-{key}"

            # Start from scratch so that every crate is compiled and profiled
            if rerun:
                shutil.rmtree(target_dir, ignore_errors=True)
                shutil.rmtree(prof_dir, ignore_errors=True)

            rustflags = f"-Znext-solver=coherence {backend['flag']} -Zself-profile={prof_dir.name}"
            output = run_task(f"Self profile on {benchmark} ({name})",
                     [
                         "env", f"RUSTFLAGS={rustflags}",
                         *([f"RUSTC={backend['rustc']}"] if "rustc" in backend else []),
                         *([f"CARGO_PROFILE_DEV_OPT_LEVEL={backend['opt_level']}"] if "opt_level" in backend else []),
                         "cargo", TOOLCHAIN, "build",
                         "--target", TARGET,
                         "--target-dir", target_dir.name,
                     ],
                     cwd=bench_dir,
                     allow_failure=True)

            # Drop partial profiles, so that the backend doesn't show up in the results of this benchmark. Also drop the
            # target dir, as otherwise the next run would only compile (and profile) the crates that failed.
            if output is None:
                shutil.rmtree(target_dir, ignore_errors=True)
                shutil.rmtree(prof_dir, ignore_errors=True)

def self_profile_results():
    for benchmark in BENCHMARKS:
        rows = {}
        for name, backend in BACKENDS.items():
            # Backends that failed on this benchmark have no profiles
            if not profiles(benchmark, name):
                continue
            ir = opt = lto = obj = link = total = 0.0
            # Sum over all crates (dependencies included) and all codegen units
            for profile in profiles(benchmark, name):
                times, profile_total = event_times(f"{benchmark} ({name})", profile)
                total += profile_total
                ir += sum(times.get(event, 0.0) for event in backend["ir"])
                opt += sum(times.get(event, 0.0) for event in backend["opt"])
                lto += sum(times.get(event, 0.0) for event in backend["lto"])
                obj += sum(times.get(event, 0.0) for event in backend["obj"])
                link += sum(times.get(event, 0.0) for event in LINK)
            rows[name] = {HEADER_IR: ir, HEADER_OPT: opt, HEADER_LTO: lto, HEADER_OBJ: obj, HEADER_LINK: link, HEADER_TOTAL: total}

        if not rows:
            print(f"No self-profile results for {benchmark}")
            continue
        print_table(rows, f"Self profile {benchmark}")

        for name in rows:
            create_flamegraph(benchmark, name)
