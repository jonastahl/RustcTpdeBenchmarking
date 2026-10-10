import csv
import io
import re

from src.helper import run_task, print_table

COMPILE_TESTS = ["helloworld", "regex"]

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

def run_benchmark(config):
    run_task("Remove previous results",
             [
                 "rm", "-f", "results.db",
             ],
             cwd="deps/rustc-perf")
    for (compiler, name) in config:
        run_task(f"Running benchmark with compiler {name}",
                 [
                     "./target/release/collector", "bench_local",
                     "--profiles", "Debug",
                     "--scenarios", "Full",
                     "--include", ",".join(COMPILE_TESTS),
                     "--id", name,
                     compiler
                 ],
                 cwd="deps/rustc-perf")

    output = run_task("Reading the results",
             [
                 "sqlite3", "-header", "-csv", "results.db",
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
    print_table(results, "Benchmarks")
