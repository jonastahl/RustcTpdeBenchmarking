import os
import shutil
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

def run_task(description, command, cwd=".", print_result=False):
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
        sys.exit(1)

def format_seconds(seconds):
    """Formats seconds, or a (min, median) tuple as `min (median)`."""
    if seconds is None:
        return "- ms"
    if isinstance(seconds, tuple):
        return f"{seconds[0] * 1000:.1f} ({seconds[1] * 1000:.1f}) ms"
    return f"{seconds * 1000:.1f} ms"

def print_table(table: Dict[str, Dict[str, Number]], title = ""):
    headers = sorted(table.keys())
    rows = sorted({key for column in table.values() for key in column})

    def average(col):
        values = [v for v in (table[col].get(row) for row in rows) if v is not None]
        if not values:
            return None
        if isinstance(values[0], tuple):
            return tuple(sum(v[i] for v in values) / len(values) for i in range(len(values[0])))
        return sum(values) / len(values)

    table = ([[title, *headers]]
             + [[row, *map(format_seconds, [table[col].get(row) for col in headers])] for row in rows]
             + [["Average", *map(format_seconds, [average(col) for col in headers])]])
    widths = [max(len(row[i]) for row in table) for i in range(len(headers) + 1)]
    separator = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    print(separator)
    for index, row in enumerate(table):
        if index == len(table) - 1:
            print(separator)
        print("| " + " | ".join(row[0].ljust(widths[0]) if i == 0 else row[i].rjust(widths[i])
                                for i in range(len(headers) + 1)) + " |")
        if index == 0:
            print(separator)
    print(separator)
