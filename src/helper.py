import os
import shutil
import statistics
import subprocess
import sys
from typing import Dict, List

# Ensure that the right cargo is used
env = os.environ.copy()
cargo_bin = os.path.expanduser("~/.cargo/bin")
env["PATH"] = f"{cargo_bin}{os.pathsep}{env.get('PATH', '')}"
env["CARGO_PROFILE_DEV_DEBUG"] = "0"
env["CARGO_PROFILE_RELEASE_DEBUG"] = "0"

TMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
os.makedirs(TMP_DIR, exist_ok=True)
env["TMPDIR"] = TMP_DIR

def run_task(description, command, cwd=".", print_result=False, allow_failure=False):
    # ANSI escape codes for terminal colors and actions
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'
    CLEAR_LINE = '\033[K'

    # 1. Print initial yellow loading state
    print(f"[{YELLOW}⋯{RESET}] {description}", end="", flush=True)

    # 2. Run the command using Popen to stream output live
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # Merge stderr into stdout so we don't miss errors
        text=True,
        env=env
    )

    full_output = []

    # Calculate visible length of "[⋯] description > " to avoid line-wrap calculations
    visible_prefix_len = 4 + len(description) + 3

    # 3. Read output live and overwrite the end of the line
    for line in iter(process.stdout.readline, ''):
        full_output.append(line)

        clean_line = line.strip().replace('\t', ' ')
        columns, _ = shutil.get_terminal_size()

        # Determine how much space is left on the terminal line
        available_space = max(0, columns - visible_prefix_len)
        truncated_line = clean_line[:available_space]

        # \r goes to start, CLEAR_LINE wipes the row, then we print the new frame
        sys.stdout.write(f"\r{CLEAR_LINE}[{YELLOW}⋯{RESET}] {description} > {truncated_line}")
        sys.stdout.flush()

    process.wait()

    # 4. Handle success or failure
    if process.returncode == 0:
        # Overwrite with green success message
        print(f"\r{CLEAR_LINE}[{GREEN}✔{RESET}] {description}")
        output = "".join(full_output).strip()
        if print_result:
            print(output)
        return output
    else:
        # Overwrite with red failure message and dump the full captured log
        print(f"\r{CLEAR_LINE}[{RED}✖{RESET}] {description}\n")
        print("".join(full_output).strip())
        if not allow_failure:
            sys.exit(1)
        # Partial results (e.g. benchmarks a backend does support) are still usable
        print(f"\n[{YELLOW}!{RESET}] Continuing despite failure of: {description}")
        return None

def format_value(value, stdev=None, unit=" ms", signed=False):
    """Formats a value with one decimal (and an explicit sign if signed), followed by its standard deviation if given."""
    text = f"{value:+.1f}{unit}" if signed else f"{value:.1f}{unit}"
    return text if stdev is None else f"{text} ± {stdev:.1f}{unit}"

def print_table(table: Dict[str, Dict[str, List[float]]], title = "", baseline = None):
    """Prints one column per key of table, reducing the samples (in seconds) of every cell to their median and standard
    deviation. The baseline column comes first and is the only one with absolute values. All other columns show the
    change of their median relative to the median of the baseline in the same row (1.1 * baseline -> +10.0%) and their
    standard deviation in percent of the baseline median. Where the baseline median is 0, there is no relative change,
    so the absolute difference is shown instead.

    The average row is the mean of the medians for the baseline and the geometric mean of the relative medians for all
    other columns, so the latter only considers the rows both columns have results for."""
    headers = sorted(table.keys(), key=lambda header: (header != baseline, header))
    rows = sorted({key for column in table.values() for key in column})
    medians = {col: {row: statistics.median(samples) for row, samples in column.items()} for col, column in table.items()}

    def stdev(col, row):
        # The standard deviation needs at least two samples
        samples = table[col].get(row, [])
        return statistics.stdev(samples) if len(samples) > 1 else None

    def cell(col, row):
        value = medians[col].get(row)
        if value is None:
            return "-"
        spread = stdev(col, row)
        if baseline is None or col == baseline:
            return format_value(value * 1000, None if spread is None else spread * 1000)
        base = medians.get(baseline, {}).get(row)
        if base is None:
            return "-"
        if base == 0:
            return format_value(value * 1000, None if spread is None else spread * 1000, signed=True)
        return format_value((value / base - 1) * 100, None if spread is None else spread / base * 100,
                            unit="%", signed=True)

    def average(col):
        if baseline is None or col == baseline:
            values = [v for v in (medians[col].get(row) for row in rows) if v is not None]
            return format_value(sum(values) / len(values) * 1000) if values else "-"
        relatives = [medians[col][row] / medians[baseline][row] for row in rows
                     if medians[col].get(row) and medians.get(baseline, {}).get(row)]
        return format_value((statistics.geometric_mean(relatives) - 1) * 100, unit="%", signed=True) if relatives else "-"

    cells = ([[title, *headers]]
             + [[row, *[cell(col, row) for col in headers]] for row in rows]
             + [["Average", *[average(col) for col in headers]]])
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers) + 1)]
    separator = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    print(separator)
    for index, row in enumerate(cells):
        if index == len(cells) - 1:
            print(separator)
        print("| " + " | ".join(row[0].ljust(widths[0]) if i == 0 else row[i].rjust(widths[i])
                                for i in range(len(headers) + 1)) + " |")
        if index == 0:
            print(separator)
    print(separator)
