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

    # Install nightly toolchain
    run_task("Install nightly toolchain",
             ["rustup", "toolchain", "install", "nightly"])