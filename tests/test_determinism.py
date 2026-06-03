"""Cross-process reproducibility guard.

Locks in the property described in CLAUDE.md and HANDOFF.md: a given seed must
yield byte-identical run JSONs across SEPARATE process invocations. The hazard is
unsorted iteration over a ``set`` of ``WasteType``/``OutputType`` members on an
ordered-work path -- enum members hash by ``id()`` (which ``PYTHONHASHSEED`` does
not control), so set iteration order follows per-process memory layout and
silently diverges between processes.

This must run as two real subprocesses: an in-process "run twice" check could not
catch the bug, because within one process the memory order is stable. The test is
marked ``slow`` (two full baseline invocations) and is opt-in via ``--run-slow``;
see ``tests/conftest.py``.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_baseline(out_root: Path) -> None:
    """Run one isolated single-replication baseline into ``out_root``."""
    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--mode",
            "baseline",
            "--scenario",
            "Baseline",
            "--replications",
            "1",
            "--out-root",
            str(out_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"baseline run failed (exit {result.returncode})\n"
        f"--- stdout tail ---\n{result.stdout[-2000:]}\n"
        f"--- stderr tail ---\n{result.stderr[-2000:]}"
    )


@pytest.mark.slow
def test_baseline_runs_are_byte_identical_across_processes(tmp_path):
    """Two separate-process baseline runs at the same seed must match byte-for-byte."""
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    _run_baseline(out_a)
    _run_baseline(out_b)

    runs_a = sorted(out_a.rglob("run_*.json"))
    runs_b = sorted(out_b.rglob("run_*.json"))

    rels_a = [p.relative_to(out_a).as_posix() for p in runs_a]
    rels_b = [p.relative_to(out_b).as_posix() for p in runs_b]

    assert rels_a, "no run JSONs produced -- check --out-root wiring in main.py"
    assert rels_a == rels_b, f"run-file set differs across processes: {rels_a} vs {rels_b}"

    mismatched = [
        rel
        for rel, pa, pb in zip(rels_a, runs_a, runs_b)
        if pa.read_bytes() != pb.read_bytes()
    ]
    assert not mismatched, (
        "non-deterministic output across processes (likely unsorted set-of-enum "
        f"iteration on an ordered-work path): {mismatched}"
    )
