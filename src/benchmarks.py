import csv
import io

from src.helper import run_task, print_table

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
    # Inlining with the default cost factor of the backend
    "TPDE inline": ("rustc_tpde_inline.sh", []),
    **{f"TPDE inline {cost}": (f"rustc_tpde_inline_cost_{cost}.sh", []) for cost in [10, 20, 50, 100, 500]},
}

# they all contain so far unsupported asm code
EX_COMPILE_TESTS = ["cargo", "eza", "image", "stm32"]
EX_RUNTIME_TESTS = ["css"]

COMPILE_TESTS = ["diesel-2.2.10-new-solver", "nalgebra-0.33.0-new-solver", "ripgrep-14.1.1", "tokio-1.53.1"]

COMPILE_ITERATIONS = 5
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

def compiletime_db(cgu=None, cores=None, threads=None):
    """The database of the compile time results with these settings (None is the default)."""
    return ("results"
            + (f"_cgu_{cgu}" if cgu else "")
            + (f"_threads_{threads}" if threads else "")
            + (f"_cores_{cores}" if cores else "")
            + ".db")

def compiletime_suffix(cgu=None, cores=None, threads=None):
    return ((f" cgu={cgu}" if cgu else "")
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
                              include=None, purge=False, iterations=COMPILE_ITERATIONS, threads=None, profile="Debug"):
    """include: only run these benchmarks, purge: replace previous results of the same compiler in db,
    threads: number of threads of the parallel frontend (-Zthreads), profile: the cargo profile of rustc-perf"""
    if rerun:
        run_task("Remove previous results",
                 [
                     "rm", "-f", db,
                 ],
                 cwd="deps/rustc-perf")
    pin = ["taskset", "--cpu-list", f"0-{cores - 1}"] if cores else []
    for (compiler, name, settings) in config:
        run_task(f"Running benchmark with compiler {name}{suffix}",
                 [
                     *pin,
                     "./target/release/collector", "bench_local",
                     "--db", db,
                     "--profiles", profile,
                     "--scenarios", "Full",
                     "--iterations", str(iterations),
                     # The collector does not allow combining both filters
                     *(["--exact-match", ",".join(include)] if include else ["--exclude", ",".join(EX_COMPILE_TESTS)]),
                     *(["--purge"] if purge else []),
                     *(["--frontend-threads", str(threads)] if threads else []),
                     "--id", name,
                     *[arg for setting in settings for arg in ("--cargo-config", f"profile.dev.{setting}")],
                     *[arg for setting in cargo_configs for arg in ("--cargo-config", setting)],
                     compiler
                 ],
                 cwd="deps/rustc-perf",
                 allow_failure=True)

def read_wall_time(db, profile):
    """{compiler: {benchmark: samples}} in seconds of one profile (debug or check)."""
    output = run_task(f"Reading the results (wall-time, {profile})",
             [
                 "sqlite3", "-header", "-csv", db,
                 f"""
                 SELECT a.name as compiler, s.crate as benchmark, s.profile, p.value as seconds
                    FROM artifact a
                    JOIN pstat p ON a.id = p.aid
                    JOIN pstat_series s ON p.series = s.id
                    WHERE s.metric = 'wall-time' AND s.profile = '{profile}';
                 """
             ],
             cwd="deps/rustc-perf")
    return parse_results(output)

def compiletime_results(db="results.db", suffix = "", baseline=BASELINE, transpose=False, variants=None):
    """Prints and returns {variant: {benchmark: samples}} in seconds, only of the given variants if not None."""
    results = select(read_wall_time(db, "debug"), variants)
    print_table(results, f"Compiletime (wall-time){suffix}", baseline, transpose)
    return results

# The check profile doesn't run codegen, so it is the same for all variants and only measured with this one. It has its
# own id, so that it can't be mistaken for the debug results of the variant.
CHECK_VARIANT = "LLVM"
CHECK_ID = "LLVM check"

def run_check_benchmark(rerun=False, db="results.db", suffix="", cargo_configs=(), cores=None, threads=None):
    """The compile-time benchmarks with the check profile (frontend only) into db, see CheckTime."""
    run_compiletime_benchmark([(f"../../variants/{VARIANTS[CHECK_VARIANT][0]}", CHECK_ID, VARIANTS[CHECK_VARIANT][1])],
                              rerun=rerun, db=db, suffix=suffix, cargo_configs=cargo_configs, cores=cores,
                              threads=threads, profile="Check")

def check_results(db="results.db", suffix=""):
    """Returns {benchmark: samples} in seconds of the check profile."""
    results = read_wall_time(db, "check").get(CHECK_ID, {})
    print(f"Checktime{suffix}: {len(results)} benchmarks")
    return results

def run_runtime_benchmark(config, db="results.db", group=None, include=None, purge=False, iterations=RUNTIME_ITERATIONS):
    """group: only build this benchmark group, include: only run benchmarks starting with one of these names,
    purge: replace previous results of the same compiler in db"""
    for (compiler, name, settings) in config:
        # Variant specific settings override the ones of the dev profile
        profile = dict(setting.split("=", 1) for setting in DEV_PROFILE)
        profile.update(setting.split("=", 1) for setting in settings)
        run_task(f"Running runtime benchmark with compiler {name}",
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
