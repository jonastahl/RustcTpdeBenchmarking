import shutil
from pathlib import Path

from src.helper import run_task

ROOT = Path(__file__).resolve().parent
BENCH_DIR = ROOT / "rustc-perf/collector/compile-benchmarks/regex-automata-0.4.8"
BACKEND = ROOT / "backend_tpde/target/release/librustc_codegen_tpde.so"
TOOLCHAIN = "+nightly-2026-08-19"
TARGET = "x86_64-unknown-linux-gnu"

def run_self_profile():
    """Self-profile regex-automata-0.4.8 (all crates) with LLVM and TPDE and print the summaries."""
    backends = {
        "llvm": "",
        "tpde": f"-Zcodegen-backend={BACKEND}",
    }

    for name, backend_flag in backends.items():
        target_dir = BENCH_DIR / f"target-prof-{name}"
        prof_dir = BENCH_DIR / f"prof-{name}"

        # Start from scratch so that every crate is compiled and profiled
        shutil.rmtree(target_dir, ignore_errors=True)
        shutil.rmtree(prof_dir, ignore_errors=True)

        rustflags = f"-Znext-solver=coherence {backend_flag} -Zself-profile={prof_dir.name}"
        run_task(f"Self profile on regex-automata-0.4.8 ({name})",
                 [
                     "env", f"RUSTFLAGS={rustflags}",
                     "cargo", TOOLCHAIN, "build", "--lib",
                     "--target", TARGET,
                     "--target-dir", target_dir.name,
                 ],
                 cwd=BENCH_DIR)

    for name in backends:
        for profile in sorted((BENCH_DIR / f"prof-{name}").glob("*.mm_profdata")):
            run_task(f"Summary {name}: {profile.name}",
                     ["summarize", "summarize", str(profile)],
                     cwd=BENCH_DIR,
                     print_result=True)
