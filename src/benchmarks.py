from src.helper import run_task


def run_benchmark(config):
    run_task("Remove previous results",
             [
                 "rm", "-f", "results.db",
             ],
             cwd="rustc-perf")
    for (compiler, name) in config:
        run_task(f"Running benchmark with compiler {name}",
                 [
                     "./target/release/collector", "bench_local",
                     "--profiles", "Debug",
                     "--scenarios", "Full",
                     "--include", "helloworld,regex",
                     "--id", name,
                     compiler
                 ],
                 cwd="rustc-perf")

    run_task("Printing the results",
             [
                 "sqlite3", "-header", "-column", "results.db",
                 """
                 SELECT a.name as compiler, s.crate as benchmark, s.profile, p.value as seconds
                    FROM artifact a 
                    JOIN pstat p ON a.id = p.aid 
                    JOIN pstat_series s ON p.series = s.id 
                    WHERE s.metric = 'wall-time';
                 """
             ],
             cwd="rustc-perf",
             print_result=True)

    run_task("Self profile on regex-automata-0.4.8",
             ["bash", "../../../../self_profile.sh"],
             cwd="rustc-perf/collector/compile-benchmarks/regex-automata-0.4.8",
             print_result=True)