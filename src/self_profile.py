import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from src.helper import TMP_DIR, run_task, print_table

ROOT = Path(__file__).resolve().parent.parent
BENCH_ROOT = ROOT / "deps/rustc-perf/collector/compile-benchmarks"
FLAMEGRAPH_DIR = ROOT / "flamegraphs"
BACKEND_TPDE = ROOT / "deps/RustcTpde/target/release/librustc_codegen_tpde.so"
BACKEND_TPDE_NO_CACHE = ROOT / "deps/RustcTpde/target-no-cache/release/librustc_codegen_tpde.so"
BACKEND_TPDE_INLINE = ROOT / "deps/RustcTpde/target-inline/release/librustc_codegen_tpde.so"
BACKEND_TPDE_LLVM = ROOT / "deps/rustc_codegen_llvm_tpde/dist/lib/librustc_codegen_tpde.so"
TOOLCHAIN = "+nightly-2026-10-28"
TARGET = "x86_64-unknown-linux-gnu"

ITERATIONS = 5

# All other backends are shown relative to this one
BASELINE = "LLVM"

# The IR size is only shown for these backends. TPDE reports its IR size before any optimization (inlining included), so
# it is the same for all TPDE backends.
IR_SIZE_LLVM = "LLVM"
IR_SIZE_TPDE = "TPDE"
IR_SIZE_FILE = "ir_bytes.json"
IRSIZE = Path(TMP_DIR) / "irsize"

# LLVM's middle-end optimization of each codegen unit
LLVM_OPT = ["LLVM_module_optimize"]

# The ThinLTO events only occur with opt-level > 0, where rustc runs local ThinLTO across the codegen units of a crate.
# LLVM_thin_lto_optimize already includes the nested import/rename/LLVM_lto_optimize events.
LLVM_LTO = ["LLVM_thin_lto_global_analysis", "LLVM_thin_lto_optimize"]

# Linking is done by rustc_codegen_ssa for all backends. For libraries this is only archiving the rlib, for binaries
# (ripgrep) it includes running the linker.
LINK = ["link"]

# Per backend: the rustc flag selecting it (and optionally a custom rustc binary, opt-level and environment variables)
# and the self-profile events that make up IR generation, optimization, LTO and object generation. The times of all listed
# events are summed up.
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
    **{
        f"TPDE inline {cost}": {
            "flag": f"-Zcodegen-backend={BACKEND_TPDE_INLINE}",
            "env": {"TPDE_INLINE_COST": str(cost)},
            "ir": ["codegen_module"],
            "opt": ["TPDE_module_optimize"],
            "lto": [],
            "obj": ["TPDE_module_codegen_emit_obj"],
        }
        for cost in [10, 20, 50, 100, 500]
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
        "opt": ["Remove unreachable blocks", "Remove constant phi-nodes"],
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

def iterations(benchmark, name):
    """The profile directories of all completed iterations of one benchmark with one backend."""
    prof_dir = BENCH_ROOT / benchmark / f"prof-{backend_key(name)}"
    return sorted((path for path in prof_dir.glob("*") if path.name.isdigit()), key=lambda path: int(path.name))

def profiles(iteration):
    """The self-profiles of all crates compiled in one iteration. The `___` ones stem from cargo querying rustc for its
    configuration and are skipped."""
    return [profile for profile in iteration.glob("*.mm_profdata") if not profile.name.startswith("___-")]

def create_flamegraph(benchmark, name):
    """Render the self-profile of the largest crate of the first iteration of one benchmark and backend (all events) to
    flamegraphs/<benchmark>-<backend>.svg."""
    profile = max(profiles(iterations(benchmark, name)[0]), key=lambda path: path.stat().st_size)
    # The flamegraph tool takes the profile path without extension and writes rustc.svg into the cwd
    run_task(f"Create flamegraph of {benchmark} ({name})",
             ["flamegraph", profile.stem],
             cwd=profile.parent)
    FLAMEGRAPH_DIR.mkdir(exist_ok=True)
    shutil.move(profile.parent / "rustc.svg", FLAMEGRAPH_DIR / f"{benchmark}-{backend_key(name)}.svg")

def measure_llvm_ir(benchmark):
    """Writes the heap size of the parsed unoptimized LLVM IR per crate into the profile directory of IR_SIZE_LLVM, like
    tpde_ir_bytes before any optimization. This is a separate build, since -Csave-temps would distort the timings."""
    bench_dir = BENCH_ROOT / benchmark
    prof_dir = bench_dir / f"prof-{backend_key(IR_SIZE_LLVM)}"
    # Backends that failed on this benchmark have no iterations
    if not iterations(benchmark, IR_SIZE_LLVM) or (prof_dir / IR_SIZE_FILE).exists():
        return

    target_dir = bench_dir / "target-ir-size"
    shutil.rmtree(target_dir, ignore_errors=True)
    output = run_task(f"Build {benchmark} with LLVM IR files",
                      [
                          "env", f"RUSTFLAGS=-Znext-solver=coherence {BACKENDS[IR_SIZE_LLVM]['flag']} -Csave-temps",
                          "cargo", TOOLCHAIN, "build",
                          "--target", TARGET,
                          "--target-dir", target_dir.name,
                      ],
                      cwd=bench_dir,
                      allow_failure=True)
    if output is None:
        return

    # irsize has to use the LLVM of the toolchain to be able to read its bitcode
    sysroot = Path(run_task("Find the sysroot", ["rustc", TOOLCHAIN, "--print", "sysroot"]))
    library = next((sysroot / "lib").glob("libLLVM*.so*"))
    run_task("Compile irsize",
             ["cc", "-O2", str(ROOT / "src/irsize.c"), str(library), f"-Wl,-rpath,{library.parent}", "-o", str(IRSIZE)])

    modules = defaultdict(list)
    for module in target_dir.rglob("*.no-opt.bc"):
        # Named <crate>-<hash>.<codegen unit>.rcgu.no-opt.bc
        modules[module.name.split(".")[0].rsplit("-", 1)[0]].append(str(module))
    sizes = {}
    for crate, files in modules.items():
        output = run_task(f"Measure the LLVM IR of {crate}", [str(IRSIZE), *files])
        sizes[crate] = sum(int(line.rsplit(" ", 1)[1]) for line in output.splitlines())
    (prof_dir / IR_SIZE_FILE).write_text(json.dumps(sizes))
    shutil.rmtree(target_dir, ignore_errors=True)

def run_self_profile(benchmark, backends, ir_size=False, rerun=False):
    """Self-profile the benchmark (all crates) with each of the given backends ITERATIONS times, each iteration into
    prof-<backend>/<iteration>. Iterations completed by a previous run are kept unless rerun is set. Backends that fail
    to compile the benchmark are skipped for it. With ir_size, the size of the unoptimized LLVM IR is measured as well."""
    bench_dir = BENCH_ROOT / benchmark
    for name in backends:
        backend = BACKENDS[name]
        key = backend_key(name)
        target_dir = bench_dir / f"target-prof-{key}"
        prof_dir = bench_dir / f"prof-{key}"

        if rerun:
            shutil.rmtree(prof_dir, ignore_errors=True)

        for iteration in range(ITERATIONS):
            iteration_dir = prof_dir / str(iteration)
            if iteration_dir.exists():
                continue

            # Profile into a separate dir first, so that an interrupted iteration isn't mistaken for a completed one
            partial_dir = prof_dir / f"{iteration}.partial"
            shutil.rmtree(partial_dir, ignore_errors=True)
            # Start from scratch so that every crate is compiled and profiled
            shutil.rmtree(target_dir, ignore_errors=True)

            rustflags = f"-Znext-solver=coherence {backend['flag']} -Zself-profile={partial_dir}"
            output = run_task(f"Self profile on {benchmark} ({name}, iteration {iteration + 1}/{ITERATIONS})",
                     [
                         "env", f"RUSTFLAGS={rustflags}",
                         *([f"RUSTC={backend['rustc']}"] if "rustc" in backend else []),
                         *([f"CARGO_PROFILE_DEV_OPT_LEVEL={backend['opt_level']}"] if "opt_level" in backend else []),
                         *[f"{variable}={value}" for variable, value in backend.get("env", {}).items()],
                         "cargo", TOOLCHAIN, "build",
                         "--target", TARGET,
                         "--target-dir", target_dir.name,
                     ],
                     cwd=bench_dir,
                     allow_failure=True)

            # Drop all profiles, so that the backend doesn't show up in the results of this benchmark
            if output is None:
                shutil.rmtree(prof_dir, ignore_errors=True)
                break
            partial_dir.rename(iteration_dir)

    if ir_size:
        measure_llvm_ir(benchmark)

def phase_times(description, backend, iteration):
    """The time of every phase of one iteration in seconds, summed over all crates (dependencies included) and all
    codegen units."""
    ir = opt = lto = obj = link = total = 0.0
    for profile in profiles(iteration):
        times, profile_total = event_times(description, profile)
        total += profile_total
        ir += sum(times.get(event, 0.0) for event in backend["ir"])
        opt += sum(times.get(event, 0.0) for event in backend["opt"])
        lto += sum(times.get(event, 0.0) for event in backend["lto"])
        obj += sum(times.get(event, 0.0) for event in backend["obj"])
        link += sum(times.get(event, 0.0) for event in LINK)
    return {HEADER_IR: ir, HEADER_OPT: opt, HEADER_LTO: lto, HEADER_OBJ: obj, HEADER_LINK: link, HEADER_TOTAL: total}

def llvm_ir_bytes(benchmark):
    """The LLVM IR size in bytes of the crates that have a self-profile, so that it covers the same crates as the table."""
    runs = iterations(benchmark, IR_SIZE_LLVM)
    file = BENCH_ROOT / benchmark / f"prof-{backend_key(IR_SIZE_LLVM)}" / IR_SIZE_FILE
    if not runs or not file.exists():
        return None
    crates = {profile.name.rsplit("-", 1)[0] for profile in profiles(runs[0])}
    return sum(size for crate, size in json.loads(file.read_text()).items() if crate in crates)

def tpde_ir_bytes(benchmark):
    """The tpde_ir_bytes artifact size summed over all crates. The IR doesn't change between iterations, so one is enough."""
    runs = iterations(benchmark, IR_SIZE_TPDE)
    if not runs:
        return None
    total = 0
    for profile in profiles(runs[0]):
        output = run_task(f"Fetch the IR size of {benchmark} ({IR_SIZE_TPDE})", ["summarize", "summarize", str(profile)])
        match = re.search(r"\|\s*tpde_ir_bytes\s*\|\s*(\d+) bytes", output)
        if match:
            total += int(match.group(1))
    # Backends built before the artifact size existed don't report it
    return total or None

def print_ir_sizes(sizes):
    llvm = sizes[IR_SIZE_LLVM]
    tpde = sizes[IR_SIZE_TPDE]
    if llvm is None and tpde is None:
        return
    relative = f" ({(tpde / llvm - 1) * 100:+.1f}%)" if llvm and tpde else ""
    print(f"IR size: {IR_SIZE_LLVM} {'-' if llvm is None else f'{llvm / 1e6:.1f} MB'}, "
          f"{IR_SIZE_TPDE} {'-' if tpde is None else f'{tpde / 1e6:.1f} MB'}{relative}")

def self_profile_results(benchmark, backends, ir_size=False):
    """Prints the phase times of the given backends on the benchmark (and creates their flamegraphs) and returns
    {"phases": {backend: {phase: samples}}, "ir_size": {IR_SIZE_LLVM: bytes, IR_SIZE_TPDE: bytes} or None}, the times
    in seconds. Backends without results are left out, IR sizes that could not be measured are None."""
    rows = {}
    for name in backends:
        # Backends that failed on this benchmark have no iterations
        runs = [phase_times(f"{benchmark} ({name}, iteration {index + 1})", BACKENDS[name], iteration)
                for index, iteration in enumerate(iterations(benchmark, name))]
        if not runs:
            continue
        rows[name] = {header: [run[header] for run in runs] for header in runs[0]}

    sizes = {IR_SIZE_LLVM: llvm_ir_bytes(benchmark), IR_SIZE_TPDE: tpde_ir_bytes(benchmark)} if ir_size else None
    if not rows:
        print(f"No self-profile results for {benchmark}")
        return {"phases": rows, "ir_size": sizes}
    print_table(rows, f"Self profile {benchmark}", BASELINE)
    if sizes:
        print_ir_sizes(sizes)

    for name in rows:
        create_flamegraph(benchmark, name)
    return {"phases": rows, "ir_size": sizes}
