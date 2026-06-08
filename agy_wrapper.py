import os
import sys
import subprocess

import shutil

# Dynamic resolution of the original agy binary path
script_dir = os.path.dirname(os.path.realpath(__file__))
REAL_AGY = os.path.join(script_dir, "agy.original")
if not os.path.exists(REAL_AGY):
    which_original = shutil.which("agy.original")
    if which_original:
        REAL_AGY = which_original
    else:
        REAL_AGY = os.path.expanduser("~/.local/bin/agy.original")

def main():
    args = sys.argv[1:]
    
    # If stdin is a TTY, run interactively via execv (replaces Python process)
    if sys.stdin.isatty():
        try:
            os.execv(REAL_AGY, [REAL_AGY] + args)
        except FileNotFoundError:
            print(f"Error: Real agy binary not found at {REAL_AGY}", file=sys.stderr)
            sys.exit(127)
    else:
        # Non-interactive mode (e.g. called from Hermes, IDE, or background scripts)
        # We redirect stdin to DEVNULL to prevent hanging
        res = subprocess.run(
            [REAL_AGY] + args,
            stdin=subprocess.DEVNULL,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
