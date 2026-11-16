import glob
import json
import os
import shutil

from src.benchmarks import RT_PREFIX, RUNTIME_BENCH_ROOT, runtime_benchmark_groups
from src.helper import run_task

HOST = "x86_64-unknown-linux-gnu"
RUST_DIR = os.path.abspath("deps/rust")
RUST_BUILD_DIR = os.path.join(RUST_DIR, "build-release")
RUST_INSTALL_DIR = os.path.join(RUST_DIR, "rustc-tpde-release")
RUST_STAGE1_RUSTC = os.path.join(RUST_DIR, "build", HOST, "stage1", "bin", "rustc")

# To build rustc we need a current version of LLVM as well as bolt for optimized builds
LLVM_VERSION = "23.1.5"
LLVM_MAJOR = LLVM_VERSION.split(".")[0]
LLVM_DIR = os.path.abspath("llvm")
LLVM_TOOLS = ["clang", "clang++", f"clang-{LLVM_MAJOR}", "lld", "ld.lld", "llvm-bolt", "merge-fdata", "llvm-profdata"]


def download_llvm():
    name = f"LLVM-{LLVM_VERSION}-Linux-X64.tar.xz"
    tarball = os.path.join(LLVM_DIR, name)
    # The tarball is removed after unpacking, so it only remains if a previous download didn't finish
    if os.path.exists(os.path.join(LLVM_DIR, "bin", f"clang-{LLVM_MAJOR}")) and not os.path.exists(tarball):
        return
    shutil.rmtree(LLVM_DIR, ignore_errors=True)
    os.makedirs(LLVM_DIR)
    run_task(f"Downloading LLVM {LLVM_VERSION} (~2 GB)",
             ["curl", "-fsSL", "-o", tarball,
              f"https://github.com/llvm/llvm-project/releases/download/llvmorg-{LLVM_VERSION}/{name}"])
    run_task(f"Unpacking LLVM {LLVM_VERSION}",
             ["tar", "-xJf", tarball, "-C", LLVM_DIR, "--strip-components=1", "--wildcards",
              *[f"*/bin/{tool}" for tool in LLVM_TOOLS],
              "*/lib/libbolt_rt_*.a", f"*/lib/clang/{LLVM_MAJOR}/*"])
    for driver in ["clang", "clang++"]:
        with open(os.path.join(LLVM_DIR, "bin", f"{driver}.cfg"), "w") as config:
            config.write("-fuse-ld=lld\n")
    os.remove(tarball)


def build_custom_rustc(rebuild):
    if os.path.exists(os.path.join(RUST_INSTALL_DIR, "bin", "rustc")) and not rebuild:
        print("[-] Custom rustc is already installed, skipping its build (pass --rebuild to rebuild it)")
        return

    run_task("Building opt-dist",
             ["./x", "build", "tools/opt-dist"],
             cwd=RUST_DIR)

    download_llvm()
    clang = os.path.join(LLVM_DIR, "bin", "clang")
    for cmake_build in glob.glob(os.path.join(RUST_BUILD_DIR, HOST, "stage*-codegen", HOST, "release", "build",
                                              "rustc_codegen_tpde")):
        shutil.rmtree(cmake_build)
    run_task("Building integrated llvm tpde (PGO + BOLT)",
             [
                 os.path.join(RUST_BUILD_DIR, HOST, "stage1-tools-bin", "opt-dist"), "local",
                 "--target-triple", HOST,
                 "--checkout-dir", RUST_DIR,
                 "--llvm-dir", LLVM_DIR,
                 "--build-llvm", "false",
                 "--use-bolt",
                 "--", "./x", "install",
             ],
             cwd=RUST_DIR,
             extra_env={
                 "CC": clang,
                 "CXX": clang + "++",
             })


def build_rustc_stage1():
    # Unoptimized (no PGO, BOLT or LTO) so that it quickly rebuilds after changes to the compiler
    run_task("Building stage 1 rustc",
             ["./x", "build", "--stage", "1", "library", "--set", "rust.lto=off", "--set", "rust.codegen-units=16",
              "--set", "rust.frame-pointers=true", "--set", "rust.debuginfo-level-rustc=line-tables-only"],
             cwd=RUST_DIR)


def update_modules():
    run_task("Loading all submodules",
             ["git", "submodule", "update", "--init", "--remote"])

    for dep in ["deps/RustcTpde", "deps/rustc_codegen_llvm_tpde"]:
        run_task(f"Loading submodules of {dep}",
                 ["git", "submodule", "update", "--init", "--recursive"],
                 cwd=dep)

    run_task("Loading tpde backend of rustc",
             ["git", "submodule", "update", "--init", "--recursive", "compiler/rustc_codegen_tpde"],
             cwd="deps/rust")

def build_tpde_lib():
    # Building backend
    run_task("Building tpde backend",
             ["cargo", "build", "--release"],
             "deps/RustcTpde")

COMPILE_BENCH_ROOT = RUNTIME_BENCH_ROOT.parent / "compile-benchmarks"
# The self-profile results and target dirs in a benchmark (src.self_profile), kept when copying
SELF_PROFILE_DIRS = ("prof-", "target-prof-")


def copy_runtime_benchmarks():
    benchlib = RUNTIME_BENCH_ROOT.parent / "benchlib"
    data = RUNTIME_BENCH_ROOT / "data"
    groups = runtime_benchmark_groups()
    # Copies of groups that no longer exist or are excluded now
    for stale in COMPILE_BENCH_ROOT.glob(f"{RT_PREFIX}*"):
        if stale.name.removeprefix(RT_PREFIX) not in groups:
            shutil.rmtree(stale)
    for group in groups:
        target = COMPILE_BENCH_ROOT / f"{RT_PREFIX}{group}"
        # Everything but the results of the self-profiles (src.self_profile) is copied again
        if target.exists():
            for item in target.iterdir():
                if item.name.startswith(SELF_PROFILE_DIRS):
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        shutil.copytree(RUNTIME_BENCH_ROOT / group, target, ignore=shutil.ignore_patterns("target"), dirs_exist_ok=True)

        manifest = target / "Cargo.toml"
        manifest.write_text(manifest.read_text().replace('"../../benchlib"', json.dumps(str(benchlib))))
        for source in (target / "src").rglob("*.rs"):
            text = source.read_text()
            if '"../../data/' in text:
                source.write_text(text.replace('"../../data/', json.dumps(f"{data}/")[:-1]))

        (target / "perf-config.json").write_text(json.dumps({"category": "primary", "artifact": "binary"}, indent=4))
    print(f"[-] Copied {len(groups)} runtime benchmark groups to the compile-time benchmarks ({RT_PREFIX}*)")


def run_setup(rebuild=False):
    update_modules()

    # Installing cxxbridge for cmake
    run_task("Install cxxbridge-cmd for cmake",
             ["cargo", "install", "cxxbridge-cmd"],
             "deps/RustcTpde")

    build_tpde_lib()

    # Build backend without caching
    run_task("Building tpde backend no-cache",
             ["cargo", "build", "--release", "--features", "no-cache", "--target-dir", "target-no-cache"],
             "deps/RustcTpde")

    # Build llvm tpde backend
    run_task("Building llvm-tpde backend",
             ["./y.sh", "build", "--sysroot", "none"],
             cwd="deps/rustc_codegen_llvm_tpde")

    build_custom_rustc(rebuild)

    run_task("Register built rustc toolchain",
             ["rustup", "toolchain", "link", "tpde-release", RUST_INSTALL_DIR])

    # Building rustc-perf
    run_task("Building rustc-perf",
             ["cargo", "build", "--release", "-p", "collector"],
             "deps/rustc-perf")

    copy_runtime_benchmarks()

    # Install measureme for results of self perf (summarize) and the flamegraph of it
    run_task("Install self-perf measureme",
             ["cargo", "install", "--git", "https://github.com/rust-lang/measureme", "summarize", "flamegraph"])

    # Install the pinned nightly toolchain with cranelift and gcc components
    run_task("Install nightly toolchain with gcc and cranelift",
             [
                 "rustup", "toolchain", "install", "nightly-2026-10-28",
                 "--component", "rustc-codegen-cranelift",
                 "--component", "rustc-codegen-gcc",
             ])

    # Add gcc component
    run_task("Add gcc component for libgccjit",
             [
                 "rustup", "component", "add", "gcc-x86_64-unknown-linux-gnu-preview",
                 "--toolchain", "nightly-2026-10-28",
             ])
