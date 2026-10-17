import argparse

from results import results
from src.benchmarks import run_compiletime_benchmark, run_runtime_benchmark
from src.setup import run_setup
from src.self_profile import run_self_profile

def load_variants():
    # all variants relative to deps/rustc-perf
    return [
        ("../../variants/rustc_cranelift.sh", "rustc_cranelift", []),
        ("../../variants/rustc_llvm.sh", "rustc_llvm", []),
        ("../../variants/rustc_llvm.sh", "rustc_llvm_O1", ["opt-level=1"]),
        ("../../variants/rustc_llvm.sh", "rustc_llvm_O2", ["opt-level=2"]),
        ("../../variants/rustc_llvm.sh", "rustc_llvm_O3", ["opt-level=3"]),
        ("../../variants/rustc_llvm_tpde.sh", "rustc_llvm_tpde", []),
        ("../../variants/rustc_tpde.sh", "rustc_tpde", []),
        ("../../variants/rustc_tpde_no_cache.sh", "rustc_tpde_no_cache", []),
    ]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rerun", action="store_true",
                        help="Delete the existing results.db and rerun all benchmarks")
    args = parser.parse_args()

    # Download and compile all dependencies
    run_setup()

    # Load the different variants
    config = load_variants()

    # Run the actual benchmarks
    run_compiletime_benchmark(config, rerun=args.rerun)

    # Run benchmarks with cgu = 1
    run_compiletime_benchmark(config, rerun=args.rerun, db="results_1.db", suffix=" cgu=1", cargo_configs=["profile.dev.codegen-units=1"])

    # Measure the runtime performance of the generated code
    run_runtime_benchmark(config)

    # Self profile all crates of regex-automata
    run_self_profile(rerun=args.rerun)

    results()

if __name__ == '__main__':
    main()
