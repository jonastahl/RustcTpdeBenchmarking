import csv
import io

from src.helper import run_task, print_table

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
BASELINE = "rustc_llvm"

def parse_results(output):
    """Parse the csv output of the results query into {compiler: {benchmark: samples}} in seconds.

    The query returns one row per iteration, so every benchmark has one sample per iteration."""
    samples = {}
    for row in csv.DictReader(io.StringIO(output)):
        samples.setdefault(row["compiler"], {}).setdefault(row["benchmark"], []).append(float(row["seconds"]))
    return samples

def run_compiletime_benchmark(config, rerun=False, db="results.db", suffix="", cargo_configs=()):
    if rerun:
        run_task("Remove previous results",
                 [
                     "rm", "-f", db,
                 ],
                 cwd="deps/rustc-perf")
    for (compiler, name, settings) in config:
        run_task(f"Running benchmark with compiler {name}{suffix}",
                 [
                     "./target/release/collector", "bench_local",
                     "--db", db,
                     "--profiles", "Debug",
                     "--scenarios", "Full",
                     "--iterations", str(COMPILE_ITERATIONS),
                     "--exclude", ",".join(EX_COMPILE_TESTS),
                     "--id", name,
                     *[arg for setting in settings for arg in ("--cargo-config", f"profile.dev.{setting}")],
                     *[arg for setting in cargo_configs for arg in ("--cargo-config", setting)],
                     compiler
                 ],
                 cwd="deps/rustc-perf",
                 allow_failure=True)

def compiletime_results(db="results.db", suffix = ""):
    output = run_task("Reading the results (wall-time)",
             [
                 "sqlite3", "-header", "-csv", db,
                 """
                 SELECT a.name as compiler, s.crate as benchmark, s.profile, p.value as seconds
                    FROM artifact a 
                    JOIN pstat p ON a.id = p.aid 
                    JOIN pstat_series s ON p.series = s.id 
                    WHERE s.metric = 'wall-time';
                 """
             ],
             cwd="deps/rustc-perf")

    results = parse_results(output)
    print_table(results, f"Compiletime (wall-time){suffix}", BASELINE)

    output = run_task("Reading the results (cpu-clock)",
                      [
                          "sqlite3", "-header", "-csv", db,
                          """
                          SELECT a.name as compiler, s.crate as benchmark, s.profile, p.value / 1000 as seconds
                          FROM artifact a
                                   JOIN pstat p ON a.id = p.aid
                                   JOIN pstat_series s ON p.series = s.id
                          WHERE s.metric = 'cpu-clock';
                          """
                      ],
                      cwd="deps/rustc-perf")

    results = parse_results(output)
    print_table(results, f"Compiletime (cpu-clock){suffix}", BASELINE)

    output = run_task("Reading the results (task-clock)",
                      [
                          "sqlite3", "-header", "-csv", db,
                          """
                          SELECT a.name as compiler, s.crate as benchmark, s.profile, p.value / 1000 as seconds
                          FROM artifact a
                                   JOIN pstat p ON a.id = p.aid
                                   JOIN pstat_series s ON p.series = s.id
                          WHERE s.metric = 'task-clock';
                          """
                      ],
                      cwd="deps/rustc-perf")

    results = parse_results(output)
    print_table(results, f"Compiletime (task-clock){suffix}", BASELINE)

def run_runtime_benchmark(config):
    for (compiler, name, settings) in config:
        # Variant specific settings override the ones of the dev profile
        profile = dict(setting.split("=", 1) for setting in DEV_PROFILE)
        profile.update(setting.split("=", 1) for setting in settings)
        run_task(f"Running runtime benchmark with compiler {name}",
                 [
                     "./target/release/collector", "bench_runtime_local",
                     "--id", name,
                     "--iterations", str(RUNTIME_ITERATIONS),
                     "--exclude", ",".join(EX_RUNTIME_TESTS),
                     # Try to resemble debug builds as close as possible
                     *[arg for key, value in profile.items() for arg in ("--cargo-config", f"profile.release.{key}={value}")],
                     compiler
                 ],
                 cwd="deps/rustc-perf",
                 allow_failure=True)

def runtime_results():
    output = run_task("Reading the runtime results",
             [
                 "sqlite3", "-header", "-csv", "results.db",
                 """
                 SELECT a.name AS compiler, s.benchmark AS benchmark, p.value / 1e9 AS seconds
                    FROM artifact a
                    JOIN runtime_pstat p ON a.id = p.aid
                    JOIN runtime_pstat_series s ON p.series = s.id
                    WHERE s.metric = 'wall-time';
                 """
             ],
             cwd="deps/rustc-perf")

    print_table(parse_results(output), "Runtime", BASELINE)