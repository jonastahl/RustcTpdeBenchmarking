from src.helper import run_task

def run_setup():
    # Loading all submodules
    run_task("Loading all submodules",
             ["git", "submodule", "update", "--init", "--recursive"])

    # Install needed rustc version via cargo
    run_task("Installing needed rustc version",
             ["rustup", "install"],
             "backend_tpde")

    # Building backend
    run_task("Building tpde backend",
             ["cargo", "build", "--release"],
             "backend_tpde")

    # Building rustc-perf
    run_task("Building rustc-perf",
             ["cargo", "build", "--release", "-p", "collector"],
             "rustc-perf")