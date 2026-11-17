"""Wall-time of the compilation sections of rustc (codegen, link) in the compile-time benchmarks, as rustc reports them
itself.

With --json=timings rustc emits the start and end of its sections: codegen spans from the start of codegen_crate to the
end of finish_ongoing_codegen, i.e. everything the backend does (IR generation, optimization, object generation,
including the waiting for its worker threads), but not linking, which has its own section. It is the same split as the
"Backend" of rustc-perf's compute_compilation_sections, and doesn't depend on the backend's own profiling events.

cargo passes --json=timings to rustc with -Zsection-timings and, with -Zbuild-analysis, writes one log per invocation
into ~/.cargo/log. The collector passes the CARGO_CONFIGS through to every cargo invocation of a compile-time benchmark:
one that builds the dependencies of the benchmark and one per iteration for the benchmark crate itself. Only the
sections of the benchmark crate (the unit cargo was asked for) are taken, so they cover the same compilation as the
wall-time of the collector.

The logs don't name the benchmark (the collector builds it in a temporary copy, and package names are not unique among
the benchmarks), so each log is assigned to the benchmark the collector was running when cargo started (Tracker)."""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from src.helper import print_table

COLLECTOR_DIR = Path(__file__).resolve().parent.parent / "deps/rustc-perf"
LOG_DIR = Path(os.environ.get("CARGO_HOME", "~/.cargo")).expanduser() / "log"

CARGO_CONFIGS = ["unstable.build-analysis=true", "unstable.section-timings=true", "build.analysis.enabled=true"]

# The section of everything the backend does
CODEGEN = "codegen"


class Tracker:
    """Records which benchmark the collector is running (on_line of run_task) and collects the cargo logs written
    meanwhile (between start and finish)."""

    # The collector runs the benchmarks one after another, printing both before any cargo invocation of the benchmark
    RUNNING = re.compile(r"(?:Preparing|Running) ([^\s:]+)")

    def __init__(self):
        self.running = []
        self.before = set()

    def start(self):
        self.before = set(LOG_DIR.glob("*.jsonl"))

    def on_line(self, line):
        if match := self.RUNNING.match(line.strip()):
            self.running.append((time.time(), match.group(1)))

    def finish(self):
        """{benchmark: {section: [samples]}} in seconds of the logs written since start, which are removed."""
        results = {}
        for log in sorted(set(LOG_DIR.glob("*.jsonl")) - self.before):
            parsed = parse_log(log)
            log.unlink()
            if parsed is None:
                continue
            started, sections = parsed
            benchmark = next((name for at, name in reversed(self.running) if at <= started), None)
            if benchmark is None:
                print(f"No benchmark was running when {log.name} started, skipped")
                continue
            for section, seconds in sections.items():
                results.setdefault(benchmark, {}).setdefault(section, []).append(seconds)
        return results


def parse_log(log):
    """(start of the cargo invocation as unix time, {section: seconds}) of the requested unit of one log, None for an
    invocation that didn't compile the requested unit (e.g. the one building the dependencies)."""
    started, requested, begins, sections = None, set(), {}, {}
    for line in log.read_text().splitlines():
        event = json.loads(line)
        reason = event["reason"]
        if reason == "build-started":
            started = datetime.fromisoformat(event["timestamp"]).timestamp()
        elif reason == "unit-registered" and event.get("requested"):
            requested.add(event["index"])
        elif reason == "unit-section-started" and event["index"] in requested:
            begins[event["section"]] = event["elapsed"]
        elif reason == "unit-section-finished" and event["index"] in requested and event["section"] in begins:
            section = event["section"]
            sections[section] = sections.get(section, 0.0) + event["elapsed"] - begins.pop(section)
    if started is None or CODEGEN not in sections:
        return None
    return started, sections


def sections_file(db):
    """The sections of the compile-time benchmarks with the database db."""
    return COLLECTOR_DIR / f"{db.removesuffix('.db')}_sections.json"


def store_sections(db, variant, results):
    """Adds the results of Tracker.finish of one variant to the sections of db, replacing earlier results of the same
    benchmarks."""
    file = sections_file(db)
    stored = json.loads(file.read_text()) if file.exists() else {}
    stored.setdefault(variant, {}).update(results)
    file.write_text(json.dumps(stored, indent=1))


def remove_sections(db, variant=None):
    """Removes the sections of db, only the ones of variant if given."""
    file = sections_file(db)
    if variant is None:
        file.unlink(missing_ok=True)
    elif file.exists():
        stored = json.loads(file.read_text())
        stored.pop(variant, None)
        file.write_text(json.dumps(stored, indent=1))


def section_results(db="results.db", suffix="", section=CODEGEN, baseline="LLVM", variants=None):
    """Prints and returns {variant: {benchmark: samples}} in seconds of one section, only of the given variants if not
    None."""
    file = sections_file(db)
    stored = json.loads(file.read_text()) if file.exists() else {}
    results = {variant: {benchmark: sections[section] for benchmark, sections in series.items() if section in sections}
               for variant, series in stored.items() if variants is None or variant in variants}
    print_table(results, f"Section {section} (wall-time){suffix}", baseline)
    return results
