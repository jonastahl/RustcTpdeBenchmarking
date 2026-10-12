import argparse
from pathlib import Path

from src.benchmarks import run_compiletime_benchmark, run_runtime_benchmark
from src.setup import run_setup
from src.self_profile import run_self_profile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rerun", action="store_true",
                        help="Delete the existing results.db and rerun all benchmarks")
    args = parser.parse_args()

    # Download and compile all dependencies
    run_setup()

    # Load the different variants
    config = [(f"../variants/{file.name}", file.stem) for file in Path("variants").iterdir()]

    # Run the actual benchmarks
    run_compiletime_benchmark(config, rerun=args.rerun)

    # Run benchmarks with cgu = 1
    run_compiletime_benchmark(config, db="results_1.db", suffix=" cgu=1", cargo_configs=["profile.dev.codegen-units=1"])

    # Measure the runtime performance of the generated code
    run_runtime_benchmark(config)

    # Self profile all crates of regex-automata
    run_self_profile(rerun=args.rerun)


if __name__ == '__main__':
    main()
