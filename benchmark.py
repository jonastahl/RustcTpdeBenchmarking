"""Runs the benchmarks of the configurations in configurations/ and evaluates them.

Every configuration is a python file with two functions:
- get_config() returns the list of runs (see src/runs.py) it needs
- evaluate(results) receives the results of these runs as a list, in the same order as returned by get_config

The runs of all configurations are merged first, so that a variant is only run once per database and a backend only
once per self-profiled benchmark, even if several configurations need it. Benchmarks that already have results from
a previous run are skipped as well, unless --rerun is given. Afterwards all results are printed and handed to the
configurations."""
import argparse
import importlib
import shutil
from pathlib import Path

from src.benchmarks import (check_results, compiletime_db, compiletime_results, compiletime_suffix,
                            run_check_benchmark, run_compiletime_benchmark, run_runtime_benchmark, runtime_results,
                            variant_config)
from src.helper import TMP_DIR
from src.runs import CheckTime, CompileTime, Runtime, SelfProfile
from src.self_profile import run_self_profile, self_profile_results
from src.setup import run_setup

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "configurations"


def add_new(target, names):
    """Appends the names not yet in target, keeping their order."""
    target.extend(name for name in names if name not in target)


class Jobs:
    """The merged runs of all configurations."""

    def __init__(self, runs):
        # (cgu, cores, threads) -> variants
        self.compiletime = {}
        # (cgu, cores, threads) of the check runs
        self.check = []
        self.runtime = []
        # benchmark -> {"backends": [...], "ir_size": bool}
        self.self_profile = {}
        for run in runs:
            if isinstance(run, CompileTime):
                add_new(self.compiletime.setdefault(run.key, []), run.variants)
            elif isinstance(run, CheckTime):
                add_new(self.check, [run.key])
            elif isinstance(run, Runtime):
                add_new(self.runtime, run.variants)
            elif isinstance(run, SelfProfile):
                for benchmark in run.benchmarks:
                    job = self.self_profile.setdefault(benchmark, {"backends": [], "ir_size": False})
                    add_new(job["backends"], run.backends)
                    job["ir_size"] |= run.ir_size
            else:
                raise TypeError(f"Unknown run: {run!r}")

    def run(self, rerun):
        for key in dict.fromkeys([*self.compiletime, *self.check]):
            cgu, cores, threads = key
            variants = self.compiletime.get(key, [])
            settings = {"db": compiletime_db(cgu, cores, threads), "suffix": compiletime_suffix(cgu, cores, threads),
                        "cargo_configs": [f"profile.dev.codegen-units={cgu}"] if cgu else [],
                        "cores": cores, "threads": threads}
            if variants:
                run_compiletime_benchmark(variant_config(variants), rerun=rerun, **settings)
            # The check results share the database, which a rerun of the variants already removed
            if key in self.check:
                run_check_benchmark(rerun=rerun and not variants, **settings)
        if self.runtime:
            run_runtime_benchmark(variant_config(self.runtime))
        for benchmark, job in self.self_profile.items():
            run_self_profile(benchmark, job["backends"], ir_size=job["ir_size"], rerun=rerun)

    def results(self):
        """Prints the results of all jobs and returns them, in the same structure as the jobs."""
        return {
            "compiletime": {
                key: compiletime_results(db=compiletime_db(*key), suffix=compiletime_suffix(*key), variants=variants)
                for key, variants in self.compiletime.items()
            },
            "check": {key: check_results(db=compiletime_db(*key), suffix=compiletime_suffix(*key)) for key in self.check},
            "runtime": runtime_results(variants=self.runtime) if self.runtime else {},
            "self_profile": {
                benchmark: self_profile_results(benchmark, job["backends"], ir_size=job["ir_size"])
                for benchmark, job in self.self_profile.items()
            },
        }


def run_results(run, results):
    """The part of the merged results that belongs to one run of a configuration."""
    if isinstance(run, CompileTime):
        data = results["compiletime"][run.key]
        return {name: data[name] for name in run.variants if name in data}
    if isinstance(run, CheckTime):
        return results["check"][run.key]
    if isinstance(run, Runtime):
        data = results["runtime"]
        return {name: data[name] for name in run.variants if name in data}
    # SelfProfile
    selected = {}
    for benchmark in run.benchmarks:
        data = results["self_profile"][benchmark]
        selected[benchmark] = {
            "phases": {name: data["phases"][name] for name in run.backends if name in data["phases"]},
            "ir_size": data["ir_size"] if run.ir_size else None,
        }
    return selected


def available_configurations():
    return sorted(path.stem for path in CONFIG_DIR.glob("*.py") if not path.name.startswith("_"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("configurations", nargs="*", metavar="configuration",
                        help=f"Only run these configurations (default: all of {', '.join(available_configurations())})")
    parser.add_argument("--rerun", action="store_true",
                        help="Delete the existing results of the selected runs and rerun them")
    parser.add_argument("--results", action="store_true",
                        help="Skip setup and benchmarking, only evaluate the results of previous runs")
    args = parser.parse_args()

    unknown = set(args.configurations) - set(available_configurations())
    if unknown:
        parser.error(f"Unknown configurations: {', '.join(sorted(unknown))}")
    configurations = {name: importlib.import_module(f"configurations.{name}")
                      for name in args.configurations or available_configurations()}
    runs = {name: list(configuration.get_config()) for name, configuration in configurations.items()}
    jobs = Jobs(run for config in runs.values() for run in config)

    try:
        if not args.results:
            # Download and compile all dependencies
            run_setup()
            jobs.run(args.rerun)

        results = jobs.results()
        for name, configuration in configurations.items():
            print(f"\n=== Evaluate {name} ===")
            configuration.evaluate([run_results(run, results) for run in runs[name]])
    finally:
        # Also clean up the temporary directories when a benchmark aborted
        shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == '__main__':
    main()
