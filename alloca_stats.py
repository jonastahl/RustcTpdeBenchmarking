"""Statistics about the allocas in the unoptimized LLVM IR of the runtime benchmarks (see src/allocas.py).

Every runtime benchmark group is built once with LLVM IR files and its allocas are extracted, groups with extracted IR
are skipped unless --rerun is given. Afterwards every analysis in ANALYSES prints a table with a row per group.

The crates all groups compile (benchlib and its dependencies) are counted in a separate "shared" row, so that each group
row only contains its own crates. TOTAL counts every crate once.

Adding an analysis: write a function that takes a list of allocas (src.allocas.Alloca) and returns the columns of its
row as {header: value}, and register it in ANALYSES. categorize() helps with analyses that sort every alloca into one
category."""
import argparse
import shutil
from collections import Counter

from src.allocas import STATS_DIR, build_extractor, extract, groups, load
from src.helper import TMP_DIR


# ---- Helpers for analyses ----

def pct(part, whole):
    return f"{100 * part / whole:.1f}%" if whole else "-"


def categorize(allocas, classify, categories):
    """Columns with the number of allocas and the share of each category, classify maps an alloca to its category."""
    counts = Counter(classify(alloca) for alloca in allocas)
    unknown = set(counts) - set(categories)
    if unknown:
        raise ValueError(f"Unknown categories: {', '.join(map(str, unknown))}")
    return {"allocas": len(allocas), **{category: pct(counts[category], len(allocas)) for category in categories}}


# ---- Analyses ----

WRITE_ONCE = "write once, read"


def write_once_category(alloca):
    if alloca.escapes:
        return "escapes"
    writes, reads = len(alloca.writes), len(alloca.reads)
    if writes == 0:
        return "unused" if reads == 0 else "only read"
    if writes == 1:
        return WRITE_ONCE if reads else "only written"
    return "multiple writes"


def reads_follow_write_in_block(alloca):
    """All reads are in the block of the single write and after it."""
    write, = alloca.writes
    return all(read.block == write.block and read.index > write.index for read in alloca.reads)


def write_once(allocas):
    """Allocas that are written exactly once and otherwise only read (any number of times), also through pointers
    derived by GEPs. Lifetime markers are ignored. "escapes" are allocas whose pointer is passed to a call, stored, or
    used otherwise (see src.allocas.Use.is_escape); the remaining categories only contain allocas that do not escape.
    The last columns split up the write-once allocas: accessed only directly (no GEPs) and all reads in the block of the
    write after it."""
    columns = categorize(allocas, write_once_category,
                         [WRITE_ONCE, "multiple writes", "only written", "only read", "unused", "escapes"])
    qualified = [alloca for alloca in allocas if write_once_category(alloca) == WRITE_ONCE]
    columns[f"{WRITE_ONCE}: direct"] = pct(sum(not alloca.derived_accesses for alloca in qualified), len(allocas))
    columns[f"{WRITE_ONCE}: same block"] = pct(sum(map(reads_follow_write_in_block, qualified)), len(allocas))
    return columns


USE_KINDS = {
    "reads": {"load", "copy_src"},
    "writes": {"store", "copy_dst", "memset"},
    "lifetime": {"lifetime"},
    "gep/cast": {"gep", "cast"},
    "call": {"call"},
    "intrinsic": {"intrinsic"},
    "stored": {"store_value"},
}


def use_kinds(allocas):
    """How the uses of the allocas are distributed, also through derived pointers."""
    counts = Counter()
    for alloca in allocas:
        for use in alloca.uses:
            counts[next((name for name, kinds in USE_KINDS.items() if use.kind in kinds), "other")] += 1
    total = sum(counts.values())
    return {"uses": total, "per alloca": f"{total / len(allocas):.1f}" if allocas else "-",
            **{name: pct(counts[name], total) for name in [*USE_KINDS, "other"]}}


# Title -> analysis, in the order they are printed
ANALYSES = {
    "Allocas written once and then only read": write_once,
    "Uses of allocas": use_kinds,
}


# ---- Output ----

def table(title, rows):
    """rows: [(name, {header: value})], all with the same headers"""
    header = ["", *rows[0][1]]
    cells = [header, *([name, *map(str, columns.values())] for name, columns in rows)]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    lines = [title, separator]
    for index, row in enumerate(cells):
        lines.append("| " + " | ".join(cell.ljust(widths[i]) if i == 0 else cell.rjust(widths[i])
                                       for i, cell in enumerate(row)) + " |")
        if index == 0 or index == len(cells) - 2:
            lines.append(separator)
    lines.append(separator)
    return "\n".join(lines)


def evaluate(names):
    loaded = [group for group in map(load, groups()) if group is not None]
    if not loaded:
        raise SystemExit("No extracted IR, run without --results first")
    # Crates every group compiles, determined from all groups so that it does not depend on the selection
    shared = set.intersection(*(set(group.crates) for group in loaded)) if len(loaded) > 1 else set()
    selected = [group for group in loaded if names is None or group.name in names]

    rows = [(group.name, group.allocas(set(group.crates) - shared)) for group in selected]
    if shared:
        rows.append(("shared", loaded[0].allocas(shared)))
    rows.append(("TOTAL", [alloca for _, allocas in rows for alloca in allocas]))

    text = "\n\n".join(table(title, [(name, analysis(allocas)) for name, allocas in rows])
                       for title, analysis in ANALYSES.items())
    if shared:
        text += f"\n\nShared crates: {', '.join(sorted(shared))}"
    print(text)
    (STATS_DIR / "summary.txt").write_text(text + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rerun", action="store_true", help="Extract groups again that already have results")
    parser.add_argument("--only", nargs="+", metavar="group", choices=groups(), help="Only these benchmark groups")
    parser.add_argument("--results", action="store_true", help="Only evaluate previously extracted IR")
    args = parser.parse_args()

    if not args.results:
        try:
            build_extractor()
            failed = [group for group in args.only or groups() if not extract(group, args.rerun)]
        finally:
            shutil.rmtree(TMP_DIR, ignore_errors=True)
        if failed:
            print(f"Failed groups: {', '.join(failed)}")
    evaluate(args.only)


if __name__ == '__main__':
    main()
