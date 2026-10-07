from pathlib import Path

from src.benchmarks import run_benchmark
from src.setup import run_setup
from src.self_profile import run_self_profile

def main():
    # Download and compile all dependencies
    run_setup()

    # Load the different variants
    config = [(f"../variants/{file.name}", file.stem) for file in Path("variants").iterdir()]

    # Run the actual benchmarks
    run_benchmark(config)

    # Self profile all crates of regex-automata
    run_self_profile()


if __name__ == '__main__':
    main()
