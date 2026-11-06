"""The allocas of the unoptimized LLVM IR of the runtime benchmarks and how they are used.

Every runtime benchmark group is built like run_runtime_benchmark does (release profile with the settings of the dev
profile) with -Csave-temps. src/alloca_ir.c extracts the allocas of the IR before LLVM's optimizations (*.no-opt.bc)
together with all their uses, the result is stored per group in alloca_stats/runtime/<group>.jsonl.gz and loaded into the
classes below. See src/alloca_ir.c for the extracted fields."""
import gzip
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from src.benchmarks import DEV_PROFILE, EX_RUNTIME_TESTS
from src.helper import TMP_DIR, run_task
from src.self_profile import TARGET, TOOLCHAIN

ROOT = Path(__file__).resolve().parent.parent
GROUP_ROOT = ROOT / "deps/rustc-perf/collector/runtime-benchmarks"
STATS_DIR = ROOT / "alloca_stats/runtime"
EXTRACTOR = Path(TMP_DIR) / "alloca_ir"

# Kinds of uses (see src/alloca_ir.c)
WRITES = {"store", "copy_dst", "memset"}
READS = {"load", "copy_src"}
# Only mark the lifetime, they neither read nor write
MARKERS = {"lifetime"}
# Derive another pointer, whose uses are reported as derived uses of the alloca
DERIVATIONS = {"gep", "cast"}


@dataclass
class Use:
    kind: str
    block: int
    index: int
    # Whether the use is of a pointer derived from the alloca (GEPs, casts) instead of the alloca itself
    derived: bool
    # Byte offset of the used pointer into the alloca, None if not constant
    offset: int | None
    # All extracted fields, e.g. bytes, callee, arg, attrs
    data: dict

    @property
    def is_write(self):
        return self.kind in WRITES

    @property
    def is_read(self):
        return self.kind in READS

    @property
    def is_marker(self):
        return self.kind in MARKERS

    @property
    def is_derivation(self):
        return self.kind in DERIVATIONS

    @property
    def is_escape(self):
        """The pointer leaves the scope of the analysis (call argument, stored, phi, ...)."""
        return not (self.is_write or self.is_read or self.is_marker or self.is_derivation)

    @property
    def position(self):
        return self.block, self.index


@dataclass
class Function:
    name: str
    crate: str
    blocks: int
    instructions: int
    allocas: list = field(default_factory=list)


@dataclass
class Alloca:
    function: Function
    name: str
    type: str
    # Bytes, None for a dynamic size
    size: int | None
    align: int
    block: int
    index: int
    uses: list

    @property
    def crate(self):
        return self.function.crate

    @cached_property
    def accesses(self):
        """The uses that read or write it (also through derived pointers)."""
        return [use for use in self.uses if use.is_read or use.is_write]

    @cached_property
    def writes(self):
        return [use for use in self.uses if use.is_write]

    @cached_property
    def reads(self):
        return [use for use in self.uses if use.is_read]

    @cached_property
    def escapes(self):
        return [use for use in self.uses if use.is_escape]

    @property
    def derived_accesses(self):
        return [use for use in self.accesses if use.derived]


@dataclass
class Group:
    """The extracted IR of one runtime benchmark group, per crate (crate name -> functions)."""
    name: str
    crates: dict

    def functions(self, crates=None):
        return [function for crate, functions in self.crates.items() if crates is None or crate in crates
                for function in functions]

    def allocas(self, crates=None):
        return [alloca for function in self.functions(crates) for alloca in function.allocas]


def groups():
    """The runtime benchmark groups run_runtime_benchmark measures."""
    return sorted(path.name for path in GROUP_ROOT.iterdir()
                  if (path / "Cargo.toml").is_file() and path.name not in EX_RUNTIME_TESTS)


def stats_file(group):
    return STATS_DIR / f"{group}.jsonl.gz"


def build_extractor():
    # It has to use the LLVM of the toolchain to be able to read its bitcode
    sysroot = Path(run_task("Find the sysroot", ["rustc", TOOLCHAIN, "--print", "sysroot"]))
    library = next((sysroot / "lib").glob("libLLVM*.so*"))
    run_task("Compile alloca_ir",
             ["cc", "-O2", str(ROOT / "src/alloca_ir.c"), str(library), f"-Wl,-rpath,{library.parent}",
              "-o", str(EXTRACTOR)])


def extract(group, rerun=False):
    """Builds the group with LLVM IR files and extracts its allocas. Returns whether it succeeded, groups with results
    of a previous run are skipped unless rerun is set. Needs build_extractor first."""
    output_file = stats_file(group)
    if output_file.exists() and not rerun:
        return True

    target_dir = Path(TMP_DIR) / f"alloca-target-{group}"
    shutil.rmtree(target_dir, ignore_errors=True)
    try:
        output = run_task(f"Build {group} with LLVM IR files",
                          [
                              "env", "RUSTFLAGS=-Csave-temps", "CARGO_INCREMENTAL=0",
                              "cargo", TOOLCHAIN, "build", "--release",
                              # Keeps build scripts and proc macros (compiled for the host) out of the target's deps
                              "--target", TARGET,
                              "--target-dir", str(target_dir),
                              # Resemble debug builds like run_runtime_benchmark
                              *[arg for setting in DEV_PROFILE for arg in ("--config", f"profile.release.{setting}")],
                          ],
                          cwd=GROUP_ROOT / group,
                          allow_failure=True)
        if output is None:
            return False

        # Both in deps/ (old layout) or build/<crate>/<hash>/out/ (new build-dir layout of cargo)
        modules = sorted(str(path) for path in (target_dir / TARGET / "release").rglob("*.no-opt.bc"))
        raw_file = target_dir / "allocas.jsonl"
        if run_task(f"Extract the allocas of {group}", [str(EXTRACTOR), str(raw_file), *modules],
                    allow_failure=True) is None:
            return False

        STATS_DIR.mkdir(parents=True, exist_ok=True)
        partial_file = output_file.with_suffix(".partial")
        with open(raw_file, "rb") as raw, gzip.open(partial_file, "wb") as compressed:
            shutil.copyfileobj(raw, compressed)
        # Only complete results are seen as done
        partial_file.replace(output_file)
        return True
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def crate_of(module):
    """Modules are named <crate>[-<hash>].<crate>.<hash>-cgu.<n>.rcgu.no-opt.bc, binaries have no hash"""
    return re.sub(r"-[0-9a-f]{16}$", "", Path(module).name.split(".")[0])


def load(group):
    """The extracted IR of a group, None if it has none."""
    path = stats_file(group)
    if not path.exists():
        return None
    crates = defaultdict(list)
    crate = function = None
    with gzip.open(path, "rt") as lines:
        for line in lines:
            record = json.loads(line)
            if "module" in record:
                crate = crate_of(record["module"])
            elif "function" in record:
                function = Function(record["function"], crate, record["blocks"], record["instructions"])
                crates[crate].append(function)
            else:
                uses = [Use(use["kind"], use["b"], use["i"], use.get("derived", False),
                            use.get("offset", None if use.get("derived") else 0), use)
                        for use in record["uses"]]
                function.allocas.append(Alloca(function, record["name"], record["type"], record["size"],
                                               record["align"], record["b"], record["i"], uses))
    return Group(group, dict(crates))
