"""Self-profiles the cranelift-codegen crate with the TPDE backend of the stage 1 rustc in deps/rust and converts the
profile to the chrome trace chrome-profile-tpde.json (open in https://ui.perfetto.dev). A separate compilation is recorded
with perf into perf.data (perf report -i perf.data). The samples of its compile thread are written to perf-tpde.txt (open in
https://www.speedscope.app or https://profiler.firefox.com) and drawn as the flamegraph flamegraph-tpde.svg and the flame
chart (time ordered) flamechart-tpde.svg. Both compile without incremental compilation."""
import re
import shlex
import shutil
from pathlib import Path

from src.helper import TMP_DIR, run_task
from src.self_profile import BENCH_ROOT, TARGET, TOOLCHAIN, profiles
from src.setup import RUST_STAGE1_RUSTC, build_rustc_stage1, update_modules

BENCHMARK = "cranelift-codegen-0.119.0"
OUT_FILE = Path(__file__).resolve().parent / "chrome-profile-tpde.json"
PERF_FILE = Path(__file__).resolve().parent / "perf.data"
PERF_SCRIPT_FILE = Path(__file__).resolve().parent / "perf-tpde.txt"
FLAMEGRAPH_FILE = Path(__file__).resolve().parent / "flamegraph-tpde.svg"
FLAMECHART_FILE = Path(__file__).resolve().parent / "flamechart-tpde.svg"
# Folds the perf script samples into one line per sample, keeping their order (inferno-collapse-perf merges and sorts them)
FOLD_SAMPLES = (r'''NF==0{if(s!="")print s" "w; s=""; next} /^[^ \t]/{w=$(NF-1); s=""; next} '''
                r'''{sub(/^[ \t]*[0-9a-f]+ /,""); sub(/\+0x[0-9a-f]+ \(.*$/,""); sub(/ \(.*$/,""); gsub(/;/,":"); '''
                r'''s=(s==""?$0:$0";"s)} END{if(s!="")print s" "w}''')


def main():
    update_modules()
    build_rustc_stage1()
    run_task("Install crox", ["cargo", "install", "--git", "https://github.com/rust-lang/measureme", "crox"])
    run_task("Install inferno and rustfilt", ["cargo", "install", "inferno", "rustfilt"])

    prof_dir = Path(TMP_DIR) / BENCHMARK
    shutil.rmtree(prof_dir, ignore_errors=True)
    cargo = ["env", f"RUSTC={RUST_STAGE1_RUSTC}", "RUSTFLAGS=-Znext-solver=coherence -Zcodegen-backend=tpde",
             "CARGO_INCREMENTAL=0", "cargo", TOOLCHAIN, "rustc", "--target", TARGET]
    run_task(f"Perf profile {BENCHMARK} with TPDE",
             ["perf", "record", "--call-graph", "fp", "-o", PERF_FILE, "--",
              *cargo, "--target-dir", prof_dir / "target-perf"],
             cwd=BENCH_ROOT / BENCHMARK)
    # The compile thread of the benchmark crate is the thread with the most samples (perf's pid sort is per thread)
    threads = run_task("Find the compile thread", ["perf", "report", "-i", PERF_FILE, "--sort", "pid", "--stdio",
                                                   "--no-children", "-g", "none"])
    tid = re.search(r"(\d+):rustc", threads).group(1)
    run_task("Export the samples of the compile thread",
             ["sh", "-c", f"perf script -i '{PERF_FILE}' --tid {tid} | rustfilt > '{PERF_SCRIPT_FILE}'"])
    run_task("Create flamegraph",
             ["sh", "-c", f"inferno-collapse-perf '{PERF_SCRIPT_FILE}' | inferno-flamegraph > '{FLAMEGRAPH_FILE}'"])
    # The flame chart draws the lines in reverse order
    run_task("Create flame chart",
             ["sh", "-c", f"awk {shlex.quote(FOLD_SAMPLES)} '{PERF_SCRIPT_FILE}' | tac "
                          f"| inferno-flamegraph --flamechart > '{FLAMECHART_FILE}'"])
    run_task(f"Self profile {BENCHMARK} with TPDE",
             [*cargo, "--target-dir", prof_dir / "target", "--", f"-Zself-profile={prof_dir}"],
             cwd=BENCH_ROOT / BENCHMARK)

    profile, = profiles(prof_dir)
    # crox always writes chrome_profiler.json into its cwd
    run_task("Convert the profile to a chrome trace", ["crox", profile], cwd=prof_dir)
    shutil.move(prof_dir / "chrome_profiler.json", OUT_FILE)

    # The raw profile is large, only the chrome trace is kept
    shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == '__main__':
    main()
