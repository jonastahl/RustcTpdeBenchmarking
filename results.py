from pathlib import Path

from src.benchmarks import COMPILE_CORES, compiletime_results, runtime_results
from src.self_profile import self_profile_results


def results():
    # Load the different variants
    config = [(f"../variants/{file.name}", file.stem) for file in Path("variants").iterdir()]

    compiletime_results()
    compiletime_results(db="results_1.db", suffix=" cgu=1")
    for cores in COMPILE_CORES:
        compiletime_results(db=f"results_cores_{cores}.db", suffix=f" {cores} cores")

    runtime_results()

    self_profile_results()

if __name__ == '__main__':
    results()