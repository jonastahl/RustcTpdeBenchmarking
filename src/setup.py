import os

from src.helper import run_task

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

    # Build integrated rustc tpde variant
    run_task("Building integrated llvm tpde",
             ["./x", "install", "--config", "bootstrap.release.toml"],
             cwd="deps/rust")

    run_task("Register built rustc toolchain",
             ["rustup", "toolchain", "link", "tpde-release", os.path.abspath("deps/rust/rustc-tpde-release")])

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
