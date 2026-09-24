"""Run WhiteboxTools tools directly and check that they really succeeded.

The `whitebox` package's `run_tool` never checks the process exit code and,
with verbose mode off, discards all output including errors, so a crashed
tool looks like success. WBT 2.3.6 FillDepressions also panics
intermittently (exit 101, ~1–6% of runs on identical input). This runner:

  - calls the WBT binary directly with absolute paths (WBT silently writes
    nothing for relative ones) and progress output off (no pipe stalls);
  - succeeds only on exit 0 *and* an existing output file;
  - retries panics (exit 101) — WBT is deterministic, so a rerun on the same
    input is safe — and raises with WBT's own error text otherwise.
"""

from __future__ import annotations

import subprocess
import time
from functools import cache
from pathlib import Path

_PANIC_EXIT = 101
_ATTEMPTS = 3


@cache
def _exe() -> Path:
    # Constructing the wrapper downloads the WBT binary on first use.
    from whitebox.whitebox_tools import WhiteboxTools
    w = WhiteboxTools()
    return Path(w.exe_path) / w.exe_name


def _flag(name: str, value) -> str | None:
    if value is True:
        return f"--{name}"
    if value is False or value is None:
        return None
    if isinstance(value, Path):
        value = value.resolve()
    return f"--{name}={value}"


def run(tool: str, output: Path, **args) -> Path:
    """Run WBT `tool` (CamelCase, e.g. "FillDepressions") writing `output`.

    Keyword args become flags: Path → absolute path, True → bare flag,
    False/None → omitted. Returns the resolved output path."""
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(_exe()), f"--run={tool}", f"--wd={output.parent}",
           f"--output={output}", "-v=false"]
    cmd += [f for k, v in args.items() if (f := _flag(k, v))]

    for attempt in range(1, _ATTEMPTS + 1):
        if output.exists():
            output.unlink()
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0 and output.exists():
            return output
        detail = (p.stderr or p.stdout).strip()[-500:]
        if p.returncode == _PANIC_EXIT and attempt < _ATTEMPTS:
            print(f"  WARNING: WBT {tool} panicked after {time.time()-t0:.0f}s "
                  f"(attempt {attempt}/{_ATTEMPTS}), retrying: {detail.splitlines()[-1:]}")
            continue
        raise RuntimeError(
            f"WBT {tool} failed (exit {p.returncode}, output "
            f"{'present' if output.exists() else 'missing'}):\n{detail}")
    raise AssertionError("unreachable")
