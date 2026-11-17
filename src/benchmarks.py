import csv
import io
import json
import re
from pathlib import Path

from src.helper import run_task, print_table
from src.sections import CARGO_CONFIGS as SECTION_CONFIGS, Tracker, remove_sections, store_sections

# The variants of the compile time and runtime benchmarks by name: the rustc wrapper script in variants/ and the cargo
# profile settings of the variant. The names are the same as the ones of the self-profile backends
# (src.self_profile.BACKENDS).
VARIANTS = {
    "Cranelift": ("rustc_cranelift.sh", []),
    "LLVM": ("rustc_llvm.sh", []),
    "LLVM O1": ("rustc_llvm.sh", ["opt-level=1"]),
    "LLVM O2": ("rustc_llvm.sh", ["opt-level=2"]),
    "LLVM O3": ("rustc_llvm.sh", ["opt-level=3"]),
    "TPDE LLVM": ("rustc_llvm_tpde.sh", []),
    "TPDE": ("rustc_tpde.sh", []),
    "TPDE no-cache": ("rustc_tpde_no_cache.sh", []),
    "TPDE inline": ("rustc_tpde_inline.sh", []),
    "TPDE inline,promote": ("rustc_tpde_inline_promote.sh", []),
    "TPDE MIR2": ("rustc_tpde.sh", ["opt-level=2"]),
    "TPDE inline MIR2": ("rustc_tpde_inline.sh", ["opt-level=2"]),
    "TPDE inline,promote MIR2": ("rustc_tpde_inline_promote.sh", ["opt-level=2"]),
    # Kept at opt-level 1 like their earlier results
    **{f"TPDE inline {cost}": (f"rustc_tpde_inline_cost_{cost}.sh", []) for cost in [10, 20, 50, 100, 500]},
    "Custom LLVM": ("rustc_custom_llvm.sh", []),
    "Custom TPDE": ("rustc_custom_tpde.sh", []),
}

# they all contain so far unsupported asm code
EX_COMPILE_TESTS = ["cargo", "eza", "image", "stm32"]
EX_RUNTIME_TESTS = ["css"]

# The runtime benchmark groups are also copied to the compile-time benchmarks (see src.setup), as rt-<group>, so that the
# compile time and runtime of the same code can be compared. They are only part of the compile-time runs of the
# "runtime" suite, the "compile" suite (all other compile-time benchmarks) leaves them out.
RT_PREFIX = "rt-"
SUITES = ["compile", "runtime"]
RUNTIME_BENCH_ROOT = Path(__file__).resolve().parent.parent / "deps/rustc-perf/collector/runtime-benchmarks"
COMPILE_BENCH_ROOT = RUNTIME_BENCH_ROOT.parent / "compile-benchmarks"

COMPILE_TESTS = ["diesel-2.2.10-new-solver", "nalgebra-0.33.0-new-solver", "ripgrep-14.1.1", "tokio-1.53.1"]

COMPILE_ITERATIONS = 5


def compile_benchmarks():
    """The benchmarks of the "compile" suite, the same selection as run_compiletime_benchmark: all compile-time
    benchmarks except EX_COMPILE_TESTS and the copies of the runtime benchmarks (both matched as name prefixes, like the
    --exclude of the collector), and except the ones whose perf-config.json excludes the Debug profile."""
    def included(bench_dir):
        if not (bench_dir / "Cargo.toml").exists():
            return False
        if bench_dir.name.startswith((*EX_COMPILE_TESTS, RT_PREFIX)):
            return False
        config = bench_dir / "perf-config.json"
        return not config.exists() or "Debug" not in json.loads(config.read_text()).get("excluded_profiles", [])

    return sorted(bench_dir.name for bench_dir in COMPILE_BENCH_ROOT.iterdir() if included(bench_dir))

RUNTIME_ITERATIONS = 5

DEV_PROFILE = [
    "opt-level=0",
    "debug=0",
    "debug-assertions=true",
    "overflow-checks=true",
    "codegen-units=256",
]

# All other variants are shown relative to this one
BASELINE = "LLVM"

def variant_config(names):
    """The (compiler relative to deps/rustc-perf, name, settings) of the given variants, as taken by
    run_compiletime_benchmark and run_runtime_benchmark."""
    return [(f"../../variants/{VARIANTS[name][0]}", name, VARIANTS[name][1]) for name in names]

def compiletime_db(cgu=None, cores=None, threads=None, suite="compile"):
    """The database of the compile time results with these settings (None is the default)."""
    return ("results"
            + ("_rt" if suite == "runtime" else "")
            + (f"_cgu_{cgu}" if cgu else "")
            + (f"_threads_{threads}" if threads else "")
            + (f"_cores_{cores}" if cores else "")
            + ".db")

def compiletime_suffix(cgu=None, cores=None, threads=None, suite="compile"):
    return ((" runtime benchmarks" if suite == "runtime" else "")
            + (f" cgu={cgu}" if cgu else "")
            + (f" {threads} threads" if threads else "")
            + (f" {cores} cores" if cores else ""))

def select(results, variants):
    """Only the results of the given variants, other ones might stem from earlier runs on the same database."""
    return results if variants is None else {name: results[name] for name in variants if name in results}

def parse_results(output):
    """Parse the csv output of the results query into {compiler: {benchmark: samples}} in seconds.

    The query returns one row per iteration, so every benchmark has one sample per iteration."""
    samples = {}
    for row in csv.DictReader(io.StringIO(output)):
        samples.setdefault(row["compiler"], {}).setdefault(row["benchmark"], []).append(float(row["seconds"]))
    return samples

def run_compiletime_benchmark(config, rerun=False, db="results.db", suffix="", cargo_configs=(), cores=None,
                              include=None, purge=False, iterations=COMPILE_ITERATIONS, threads=None,
                              suite="compile"):
    """include: only run these benchmarks, purge: replace previous results of the same compiler in db,
    threads: number of threads of the parallel frontend (-Zthreads),
    suite: "compile" for the compile-time benchmarks, "runtime" for the copies of the runtime benchmarks (RT_PREFIX)

    Also records the compilation sections of rustc (src.sections) next to db."""
    if include:
        selection = ["--exact-match", ",".join(include)]
    elif suite == "runtime":
        # --include and --exclude match name prefixes
        selection = ["--include", RT_PREFIX]
    else:
        selection = ["--exclude", ",".join([*EX_COMPILE_TESTS, RT_PREFIX])]
    if rerun:
        run_task("Remove previous results",
                 [
                     "rm", "-f", db,
                 ],
                 cwd="deps/rustc-perf")
        remove_sections(db)
    pin = ["taskset", "--cpu-list", f"0-{cores - 1}"] if cores else []
    for (compiler, name, settings) in config:
        tracker = Tracker()
        tracker.start()
        run_task(f"Running benchmark with compiler {name}{suffix}",
                 [
                     *pin,
                     "./target/release/collector", "bench_local",
                     "--db", db,
                     "--profiles", "Debug",
                     "--scenarios", "Full",
                     "--iterations", str(iterations),
                     # The collector does not allow combining both filters
                     *selection,
                     *(["--purge"] if purge else []),
                     *(["--frontend-threads", str(threads)] if threads else []),
                     "--id", name,
                     *[arg for setting in settings for arg in ("--cargo-config", f"profile.dev.{setting}")],
                     *[arg for setting in cargo_configs for arg in ("--cargo-config", setting)],
                     *[arg for setting in SECTION_CONFIGS for arg in ("--cargo-config", setting)],
                     compiler
                 ],
                 cwd="deps/rustc-perf",
                 allow_failure=True,
                 on_line=tracker.on_line)
        results = tracker.finish()
        if results:
            store_sections(db, name, results)

def read_wall_time(db):
    """{compiler: {benchmark: samples}} in seconds of the debug profile."""
    output = run_task("Reading the results (wall-time)",
             [
                 "sqlite3", "-header", "-csv", db,
                 f"""
                 SELECT a.name as compiler, s.crate as benchmark, s.profile, p.value as seconds
                    FROM artifact a
                    JOIN pstat p ON a.id = p.aid
                    JOIN pstat_series s ON p.series = s.id
                    WHERE s.metric = 'wall-time' AND s.profile = 'debug';
                 """
             ],
             cwd="deps/rustc-perf")
    return parse_results(output)

def compiletime_results(db="results.db", suffix = "", baseline=BASELINE, transpose=False, variants=None):
    """Prints and returns {variant: {benchmark: samples}} in seconds, only of the given variants if not None."""
    results = select(read_wall_time(db), variants)
    print_table(results, f"Compiletime (wall-time){suffix}", baseline, transpose)
    return results

def runtime_db(cgu=None):
    """The database of the runtime results with this number of codegen units (None is the one of DEV_PROFILE)."""
    return f"results_runtime_cgu_{cgu}.db" if cgu else "results.db"

def runtime_suffix(cgu=None):
    return f" cgu={cgu}" if cgu else ""

def run_runtime_benchmark(config, db="results.db", group=None, include=None, purge=False, iterations=RUNTIME_ITERATIONS,
                          cgu=None, suffix=""):
    """group: only build this benchmark group, include: only run benchmarks starting with one of these names,
    purge: replace previous results of the same compiler in db, cgu: number of codegen units instead of the one of
    DEV_PROFILE"""
    for (compiler, name, settings) in config:
        # Variant specific settings override the ones of the dev profile
        profile = dict(setting.split("=", 1) for setting in DEV_PROFILE)
        profile.update(setting.split("=", 1) for setting in settings)
        if cgu:
            profile["codegen-units"] = str(cgu)
        run_task(f"Running runtime benchmark with compiler {name}{suffix}",
                 [
                     "./target/release/collector", "bench_runtime_local",
                     "--db", db,
                     "--id", name,
                     "--iterations", str(iterations),
                     *(["--group", group] if group else []),
                     # Runtime benchmarks ignore --exact-match, --include matches name prefixes
                     *(["--include", ",".join(include)] if include else ["--exclude", ",".join(EX_RUNTIME_TESTS)]),
                     *(["--purge"] if purge else []),
                     # Try to resemble debug builds as close as possible
                     *[arg for key, value in profile.items() for arg in ("--cargo-config", f"profile.release.{key}={value}")],
                     compiler
                 ],
                 cwd="deps/rustc-perf",
                 allow_failure=True)

def runtime_results(db="results.db", suffix="", baseline=BASELINE, transpose=False, variants=None):
    """Prints and returns {variant: {benchmark: samples}} in seconds, only of the given variants if not None."""
    output = run_task("Reading the runtime results",
             [
                 "sqlite3", "-header", "-csv", db,
                 """
                 SELECT a.name AS compiler, s.benchmark AS benchmark, p.value / 1e9 AS seconds
                    FROM artifact a
                    JOIN runtime_pstat p ON a.id = p.aid
                    JOIN runtime_pstat_series s ON p.series = s.id
                    WHERE s.metric = 'wall-time';
                 """
             ],
             cwd="deps/rustc-perf")

    results = select(parse_results(output), variants)
    print_table(results, f"Runtime{suffix}", baseline, transpose)
    return results

def runtime_benchmark_groups():
    """{group: [benchmark]} of the runtime benchmarks that aren't excluded, read from the names their source registers."""
    groups = {}
    for manifest in sorted(RUNTIME_BENCH_ROOT.glob("*/Cargo.toml")):
        group = manifest.parent.name
        if group in EX_RUNTIME_TESTS:
            continue
        sources = "".join(path.read_text() for path in (manifest.parent / "src").rglob("*.rs"))
        groups[group] = re.findall(r'register_benchmark\(\s*"([^"]+)"', sources)
    return groups
