from src.helper import run_task

def run_setup():
    # Loading all submodules
    run_task("Loading all submodules",
             ["git", "submodule", "update", "--init", "--remote", "--recursive"])

    # Installing cxxbridge for cmake
    run_task("Install cxxbridge-cmd for cmake",
             ["cargo", "install", "cxxbridge-cmd"],
             "backend_tpde")

    # Building backend
    run_task("Building tpde backend",
             ["cargo", "build", "--release"],
             "backend_tpde")

    # Building rustc-perf
    run_task("Building rustc-perf",
             ["cargo", "build", "--release", "-p", "collector"],
             "rustc-perf")

    # Install measureme for results of self perf (summarize) and the flamegraph of it
    run_task("Install self-perf measureme",
             ["cargo", "install", "--git", "https://github.com/rust-lang/measureme", "summarize", "flamegraph"])

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
