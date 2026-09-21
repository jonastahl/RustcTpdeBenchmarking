import os
import shutil
import subprocess
import sys


# Ensure that the right cargo is used
env = os.environ.copy()
cargo_bin = os.path.expanduser("~/.cargo/bin")
env["PATH"] = f"{cargo_bin}{os.pathsep}{env.get('PATH', '')}"

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
        if print_result:
            print("".join(full_output).strip())
    else:
        # Overwrite with red failure message and dump the full captured log
        print(f"\r{CLEAR_LINE}[{RED}✖{RESET}] {description}\n")
        print("".join(full_output).strip())
        sys.exit(1)
