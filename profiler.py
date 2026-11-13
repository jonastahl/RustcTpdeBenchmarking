"""Self-profiles the cranelift-codegen crate with TPDE and converts the profile to the chrome trace
chrome-profile-tpde.json (open in https://ui.perfetto.dev)."""
import shutil
from pathlib import Path

from src.helper import TMP_DIR, run_task
from src.self_profile import BACKENDS, BENCH_ROOT, TARGET, TOOLCHAIN, profiles
from src.setup import build_tpde_lib, update_modules

BENCHMARK = "cranelift-codegen-0.119.0"
OUT_FILE = Path(__file__).resolve().parent / "chrome-profile-tpde.json"


def main():
    update_modules()
    build_tpde_lib()
    run_task("Install crox", ["cargo", "install", "--git", "https://github.com/rust-lang/measureme", "crox"])

    prof_dir = Path(TMP_DIR) / BENCHMARK
    shutil.rmtree(prof_dir, ignore_errors=True)
    run_task(f"Self profile {BENCHMARK} with TPDE",
             ["env", f"RUSTFLAGS=-Znext-solver=coherence {BACKENDS['TPDE']['flag']}",
              "cargo", TOOLCHAIN, "rustc", "--target", TARGET, "--target-dir", prof_dir / "target",
              "--", f"-Zself-profile={prof_dir}"],
             cwd=BENCH_ROOT / BENCHMARK)

    profile, = profiles(prof_dir)
    # crox always writes chrome_profiler.json into its cwd
    run_task("Convert the profile to a chrome trace", ["crox", profile], cwd=prof_dir)
    shutil.move(prof_dir / "chrome_profiler.json", OUT_FILE)

    # The raw profile is large, only the chrome trace is kept
    shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == '__main__':
    main()
