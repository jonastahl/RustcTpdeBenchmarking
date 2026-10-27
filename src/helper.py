import os
import shutil
import statistics
import subprocess
import sys
from numbers import Number
from typing import Dict

# Ensure that the right cargo is used
env = os.environ.copy()
cargo_bin = os.path.expanduser("~/.cargo/bin")
env["PATH"] = f"{cargo_bin}{os.pathsep}{env.get('PATH', '')}"
env["CARGO_PROFILE_DEV_DEBUG"] = "0"
env["CARGO_PROFILE_RELEASE_DEBUG"] = "0"

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

def format_seconds(seconds, relative=None):
    """Formats seconds as ms, optionally followed by the change a relative value corresponds to (0.99 -> -1.0%)."""
    if seconds is None:
        return "- ms"
    if relative is None:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds * 1000:.1f} ms ({(relative - 1) * 100:+.1f}%)"

def print_table(table: Dict[str, Dict[str, Number]], title = "", baseline = None):
    """Prints one column per key of table. With a baseline column, every value is also shown relative to the baseline
    in the same row. The relative value of the average row is the geometric mean of the relative values of its column,
    so it only considers the rows the column has results for."""
    headers = sorted(table.keys())
    rows = sorted({key for column in table.values() for key in column})

    def relative(col, row):
        value = table[col].get(row)
        base = table.get(baseline, {}).get(row)
        if value is None or not base:
            return None
        return value / base

    def average(col):
        values = [v for v in (table[col].get(row) for row in rows) if v is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def average_relative(col):
        values = [r for r in (relative(col, row) for row in rows) if r]
        if not values:
            return None
        return statistics.geometric_mean(values)

    cells = ([[title, *headers]]
             + [[row, *[format_seconds(table[col].get(row), relative(col, row)) for col in headers]] for row in rows]
             + [["Average", *[format_seconds(average(col), average_relative(col)) for col in headers]]])
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
