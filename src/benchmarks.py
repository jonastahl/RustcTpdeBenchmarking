from src.helper import run_task


def run_benchmark(config):
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

    run_task("Spinning up website to compare results",
             [
                 "cargo", "run",
                 "--release",
                 "-p", "site",
                 "--",
                 "--db", "results.db"
             ])