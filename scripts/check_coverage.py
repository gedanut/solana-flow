"""Offline line-coverage gate using the Python standard library trace module.

This fallback does not measure branches; CI also runs coverage.py with branches.
No reports contain environment-specific absolute filenames.
"""

import sys
import trace
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_tests():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    return unittest.TextTestRunner(verbosity=1).run(suite)


def main():
    tracer = trace.Trace(count=True, trace=False)
    result = tracer.runfunc(run_tests)
    counts = tracer.results().counts
    hit_total = executable_total = 0
    for path in sorted((ROOT / "src/solana_flow").glob("*.py")):
        # Same executable-line discovery used by `python -m trace --missing`.
        executable = {
            line
            for line in trace._find_executable_linenos(str(path))
            if isinstance(line, int) and line > 0
        }
        hit = {line for filename, line in counts if filename == str(path)} & executable
        hit_total += len(hit)
        executable_total += len(executable)
        percent = len(hit) / len(executable) * 100 if executable else 100
        print(f"{path.relative_to(ROOT)}: {len(hit)}/{len(executable)} ({percent:.1f}%)")
        missing = sorted(executable - hit)
        if missing:
            print("  Missing lines: " + ", ".join(map(str, missing)))
    percent = hit_total / executable_total * 100
    print(f"Total line coverage: {hit_total}/{executable_total} ({percent:.1f}%); threshold 90%")
    return 0 if result.wasSuccessful() and percent >= 90 else 1


if __name__ == "__main__":
    raise SystemExit(main())
