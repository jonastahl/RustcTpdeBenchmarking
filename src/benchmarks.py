import csv
import io
import math

from src.helper import run_task, print_table

# they all contain so far unsupported asm code
EX_COMPILE_TESTS = ["cargo", "eza", "image", "stm32"]
EX_RUNTIME_TESTS = ["css"]

DEV_PROFILE = [
    "opt-level=0",
    "debug=0",
    "debug-assertions=true",
    "overflow-checks=true",
    "codegen-units=256",
]

COMPILER_NAMES = {
    "rustc_gcc": "GCC",
    "rustc_llvm": "LLVM",
    "rustc_tpde": "TPDE",
    "rustc_tpde_dynamic": "TPDE dynamic",
    "rustc_cranelift": "Cranelift",
}


def parse_results(output):
    """Parse the csv output of the results query into {compiler: {benchmark: seconds}}."""
    results = {}
    for row in csv.DictReader(io.StringIO(output)):
        results.setdefault(row["compiler"], {})[row["benchmark"]] = float(row["seconds"])
    return results

def run_compiletime_benchmark(config, rerun=False, db="results.db", suffix="", cargo_configs=()):
    if rerun:
        run_task("Remove previous results",
                 [
                     "rm", "-f", db,
                 ],
                 cwd="rustc-perf")
    for (compiler, name) in config:
        run_task(f"Running benchmark with compiler {name}{suffix}",
                 [
                     "./target/release/collector", "bench_local",
                     "--db", db,
                     "--profiles", "Debug",
                     "--scenarios", "Full",
                     "--exclude", ",".join(EX_COMPILE_TESTS),
                     "--id", name,
                     *[arg for setting in cargo_configs for arg in ("--cargo-config", setting)],
                     compiler
                 ],
                 cwd="rustc-perf")

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
             cwd="rustc-perf")

    results = parse_results(output)
    print_table(results, f"Compiletime (wall-time){suffix}")

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
                      cwd="rustc-perf")

    results = parse_results(output)
    print_table(results, f"Compiletime (cpu-clock){suffix}")

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
                      cwd="rustc-perf")

    results = parse_results(output)
    print_table(results, f"Compiletime (task-clock){suffix}")

def run_runtime_benchmark(config):
    for (compiler, name) in config:
        run_task(f"Running runtime benchmark with compiler {name}",
                 [
                     "./target/release/collector", "bench_runtime_local",
                     "--id", name,
                     # Try to resemble debug builds as close as possible
                     *[arg for setting in DEV_PROFILE for arg in ("--cargo-config", f"profile.release.{setting}")],
                     compiler
                 ],
                 cwd="rustc-perf")

    output = run_task("Reading the runtime results",
             [
                 "sqlite3", "-header", "-csv", "results.db",
                 """
                 SELECT a.name AS compiler, s.benchmark AS benchmark, MIN(p.value) / 1e9 AS seconds
                    FROM artifact a
                    JOIN runtime_pstat p ON a.id = p.aid
                    JOIN runtime_pstat_series s ON p.series = s.id
                    WHERE s.metric = 'wall-time'
                    GROUP BY a.name, s.benchmark;
                 """
             ],
             cwd="rustc-perf")

    print_table(parse_results(output), "Runtime")