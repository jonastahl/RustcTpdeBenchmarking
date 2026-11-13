import glob
import os
import shutil

from src.helper import run_task

HOST = "x86_64-unknown-linux-gnu"
RUST_DIR = os.path.abspath("deps/rust")
RUST_BUILD_DIR = os.path.join(RUST_DIR, "build-release")

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


def run_setup():
    run_task("Loading all submodules",
             ["git", "submodule", "update", "--init", "--remote"])

    for dep in ["deps/RustcTpde", "deps/rustc_codegen_llvm_tpde"]:
        run_task(f"Loading submodules of {dep}",
                 ["git", "submodule", "update", "--init", "--recursive"],
                 cwd=dep)

    run_task("Loading tpde backend of rustc",
             ["git", "submodule", "update", "--init", "--recursive", "compiler/rustc_codegen_tpde"],
             cwd="deps/rust")

    # Installing cxxbridge for cmake
    run_task("Install cxxbridge-cmd for cmake",
             ["cargo", "install", "cxxbridge-cmd"],
             "deps/RustcTpde")

    # Building backend
    run_task("Building tpde backend",
             ["cargo", "build", "--release"],
             "deps/RustcTpde")

    # Build backend without caching
    run_task("Building tpde backend no-cache",
             ["cargo", "build", "--release", "--features", "no-cache", "--target-dir", "target-no-cache"],
             "deps/RustcTpde")

    # Build llvm tpde backend
    run_task("Building llvm-tpde backend",
             ["./y.sh", "build", "--sysroot", "none"],
             cwd="deps/rustc_codegen_llvm_tpde")

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

    run_task("Register built rustc toolchain",
             ["rustup", "toolchain", "link", "tpde-release", os.path.join(RUST_DIR, "rustc-tpde-release")])

    # Building rustc-perf
    run_task("Building rustc-perf",
             ["cargo", "build", "--release", "-p", "collector"],
             "deps/rustc-perf")

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
