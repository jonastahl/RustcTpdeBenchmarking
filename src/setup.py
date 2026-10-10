from src.helper import run_task

def run_setup():
    # Loading all submodules
    run_task("Loading all submodules",
             ["git", "submodule", "update", "--init", "--remote", "--recursive"])

    # Installing cxxbridge for cmake
    run_task("Install cxxbridge-cmd for cmake",
             ["cargo", "install", "cxxbridge-cmd"],
             "deps/RustcTpde")

    # Building backend
    run_task("Building tpde backend",
             ["cargo", "build", "--release"],
             "deps/RustcTpde")

    # Building rustc-perf
    run_task("Building rustc-perf",
             ["cargo", "build", "--release", "-p", "collector"],
             "deps/rustc-perf")

    # Install measureme for results of self perf
    run_task("Install self-perf measureme",
             ["cargo", "install", "--git", "https://github.com/rust-lang/measureme", "summarize"])

    # Install the pinned nightly toolchain with cranelift and gcc components
    run_task("Install nightly toolchain with gcc and cranelift",
             [
                 "rustup", "toolchain", "install", "nightly-2026-08-19",
                 "--component", "rustc-codegen-cranelift",
                 "--component", "rustc-codegen-gcc",
             ])

    # Add gcc component
    run_task("Add gcc component for libgccjit",
             [
                 "rustup", "component", "add", "gcc-x86_64-unknown-linux-gnu-preview",
                 "--toolchain", "nightly-2026-08-19",
             ])

    # Build rustc_codegen_llvm_tpde
    run_task("Build rustc_codegen_llvm_tpde",
             ["./y.sh", "build", "--sysroot", "none"],
             cwd="deps/rustc_codegen_llvm_tpde")