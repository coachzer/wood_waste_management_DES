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
import json
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


@pytest.mark.slow
def test_generation_floor_is_policy_invariant(tmp_path):
    """The bullwhip source-variance floor (ADR 0004) must carry no policy signal.

    The floor is the CV^2 of *potential* (pre-saturation) generation, which is
    the exogenous source process: identical RNG draws and seasonal/efficiency
    factors across PUSH/PULL x strategy at a fixed seed, so it is policy- and
    strategy-invariant. (Committed generation is NOT -- finite-storage
    backpressure couples it to collection and thus to policy, swinging its CV^2
    ~0.9-1.3 across combos; that coupling is exactly what measuring potential
    avoids.) So ``bullwhip.generation_floor_cv2`` must be effectively identical
    across all six combos of one baseline run, while the echelon ratios differ.
    Needs a real run because the floor is computed from live
    ``generation_history`` inside ``extract_kpis``.
    """
    out_root = tmp_path / "run"
    _run_baseline(out_root)

    run_files = sorted(out_root.rglob("run_*.json"))
    assert len(run_files) == 6, (
        f"expected 6 policy x strategy run JSONs, got {len(run_files)}: "
        f"{[p.relative_to(out_root).as_posix() for p in run_files]}"
    )

    floors = {}
    for run_file in run_files:
        record = json.loads(run_file.read_text())
        combo = f"{record['inventory_policy']}__{record['stock_strategy']}"
        floor = record["kpis"]["bullwhip"]["generation_floor_cv2"]
        assert floor is not None and floor >= 0.0, f"{combo}: floor is {floor!r}"
        floors[combo] = floor

    reference_combo, reference_floor = next(iter(floors.items()))
    for combo, floor in floors.items():
        assert floor == pytest.approx(reference_floor, rel=1e-9), (
            f"generation floor carries a policy signal: {combo}={floor} vs "
            f"{reference_combo}={reference_floor}"
        )
