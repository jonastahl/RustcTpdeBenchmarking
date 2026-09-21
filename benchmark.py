from pathlib import Path

from src.benchmarks import run_benchmark
from src.setup import run_setup

# Download and compile all dependencies
run_setup()

# Load the different variants
config = [(f"../variants/{file.name}", file.stem) for file in Path("variants").iterdir()]

# Run the actual benchmarks
run_benchmark(config)