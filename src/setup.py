import os
import shutil

from src.helper import run_task

HOST = "x86_64-unknown-linux-gnu"
RUST_DIR = os.path.abspath("deps/rust")
RUST_CONFIG = os.path.join(RUST_DIR, "bootstrap.release.toml")
RUST_BUILD_DIR = os.path.join(RUST_DIR, "build-release")


def opt_dist_llvm_dir():
    llvm_dir = os.path.join(RUST_BUILD_DIR, "opt-llvm")
    tools = {
        "llvm-profdata": os.path.join(RUST_BUILD_DIR, HOST, "ci-llvm", "bin", "llvm-profdata"),
        "llvm-bolt": shutil.which("llvm-bolt"),
        "merge-fdata": shutil.which("merge-fdata"),
    }
    os.makedirs(os.path.join(llvm_dir, "bin"), exist_ok=True)
    for name, target in tools.items():
        link = os.path.join(llvm_dir, "bin", name)
        if os.path.lexists(link):
            os.remove(link)
        if target:
            os.symlink(target, link)
    return llvm_dir, bool(tools["llvm-bolt"] and tools["merge-fdata"])


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

    # Build integrated rustc tpde variant. Like the official builds, rustc is optimized with PGO and BOLT by their
    # pipeline (opt-dist), so that it is comparable to the nightly toolchain of the other variants. CI LLVM is already
    # optimized, so LLVM isn't built (--build-llvm false). The tpde backend itself isn't PGO-trained.
    run_task("Building opt-dist",
             ["./x", "build", "opt-dist", "--config", RUST_CONFIG],
             cwd=RUST_DIR)

    llvm_dir, use_bolt = opt_dist_llvm_dir()
    run_task(f"Building integrated llvm tpde ({'PGO + BOLT' if use_bolt else 'PGO only, llvm-bolt/merge-fdata missing'})",
             [
                 os.path.join(RUST_BUILD_DIR, HOST, "stage1-tools-bin", "opt-dist"), "local",
                 "--target-triple", HOST,
                 # Absolute, the collector of the training runs in the rustc-perf directory with paths derived from it
                 "--checkout-dir", RUST_DIR,
                 "--llvm-dir", llvm_dir,
                 "--build-dir", RUST_BUILD_DIR,
                 # Wiped by opt-dist
                 "--artifact-dir", os.path.join(RUST_BUILD_DIR, "opt-artifacts"),
                 "--build-llvm", "false",
                 *(["--use-bolt"] if use_bolt else []),
                 # The final build, opt-dist adds the PGO profiles and --keep-stage
                 "--", "./x", "install",
             ],
             cwd=RUST_DIR,
             # The x calls of opt-dist can't take --config
             extra_env={"RUST_BOOTSTRAP_CONFIG": RUST_CONFIG})

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
