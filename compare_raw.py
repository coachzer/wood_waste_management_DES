"""Raw-vs-raw comparator for the frozen-oracle refactor gate.

The golden KPI comparator (``.scratch/golden/compare_baselines.py``) only reads
each run's ``kpis`` dict, so it cannot tell whether the raw history sidecars
(``raw_NNN.json``) survive the monitoring refactor unchanged. This tool closes
that gap. It has two jobs, one per subcommand:

  verify  -- hash every regenerated ``raw_NNN.json`` and check it against the
             committed ``frozen-oracle/manifest.sha256``. This is the
             tamper-evident byte gate: a regenerated sidecar whose bytes differ
             from the freeze fails here. Equivalent to ``sha256sum -c`` scoped
             to the raw sidecars, but reports a combo/run locator.

  diff    -- structurally compare two directories of ``raw_NNN.json`` sidecars
             (a golden capture vs a candidate). Comparison is parsed-JSON
             ``==``: dict equality is order-insensitive (an incidental
             key-ordering change from a module split is not a regression) while
             list equality is order-sensitive (time-series order is meaningful).
             Floats are compared EXACTLY -- a last-ULP drift is the reorder-bug
             signal the WasteMonitor split (ticket issues 08-10) must never
             produce. On mismatch it prints a readable locator
             (combo / run / series / index) for each divergence.

The byte gate (verify) is primary; diff exists to LOCALISE a failure the hash
gate flags -- regenerate the tag's sidecars into one dir, the refactor's into
another, and diff to see exactly which series/index moved.

Imports no project code, so it runs via ``-m`` with no circular-import risk
(unlike the ``monitoring`` package, whose ``__init__`` re-exports form a cycle
until ticket issue 03):

    python -m compare_raw verify
    python -m compare_raw verify --root . --manifest frozen-oracle/manifest.sha256
    python -m compare_raw diff GOLDEN_DIR CANDIDATE_DIR

Exit code 0 = match, 1 = mismatch, 2 = usage/IO error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator

# Default reference written by the freeze; one ``<sha256>  <path>`` line per
# blob, paths relative to repo root. Only the raw_*.json lines concern us here.
DEFAULT_MANIFEST = Path("frozen-oracle/manifest.sha256")

# Cap on per-file divergences printed by ``diff`` so a wholesale mismatch
# localises the first failures instead of flooding the terminal.
MAX_DIFFS_PER_FILE = 50

RAW_GLOB = "raw_*.json"


def _combo_run(rel_path: str) -> str:
    """Render '<combo>/<run>' from a manifest/sidecar path for a readable locator."""
    parts = Path(rel_path).parts
    if len(parts) >= 2:
        return f"{parts[-2]}/{Path(parts[-1]).stem}"
    return rel_path


# --------------------------------------------------------------------------- #
# verify -- candidate sidecars vs the committed manifest                        #
# --------------------------------------------------------------------------- #

def _combo_counts(rels: Iterator[str]) -> dict[str, int]:
    """Map each combo dir ('.../<combo>') to its number of raw sidecar paths."""
    counts: dict[str, int] = {}
    for rel in rels:
        combo = rel.rsplit("/", 1)[0]
        counts[combo] = counts.get(combo, 0) + 1
    return counts


def _replication_shortfall_hint(
    entries: list[tuple[str, str]], missing: list[str]
) -> str | None:
    """Explain a uniform rep-count shortfall, the inverse of the additive footgun.

    The frozen-oracle manifest is a 100-rep capture (600 raw sidecars); verifying
    a 10-rep regeneration against it leaves 540 sidecars missing, which reads like
    data loss when the real cause is the wrong ``--replications``. When every combo
    is short by the same factor (a clean fraction), return a one-line actionable
    hint mirroring the additive comparator's ``_replication_mismatch_hint``.
    Returns None when nothing is missing or the shortfall is not uniform (a genuine
    partial loss, which should NOT be explained away as a rep-count slip).
    """
    if not missing:
        return None
    expected_counts = _combo_counts(rel for _, rel in entries)
    missing_counts = _combo_counts(iter(missing))
    present_per_combo = {
        combo: expected_counts[combo] - missing_counts.get(combo, 0)
        for combo in expected_counts
    }
    present_values = set(present_per_combo.values())
    if len(present_values) != 1:
        return None
    present_reps = present_values.pop()
    expected_reps = max(expected_counts.values())
    if not 0 < present_reps < expected_reps:
        return None
    return (
        f"HINT: rep-count shortfall -- manifest expects {expected_reps} reps/combo "
        f"({len(entries)} sidecars), you regenerated {present_reps} "
        f"({len(entries) - len(missing)}). Regenerate with --replications "
        f"{expected_reps}, or you are verifying against the wrong oracle."
    )


def _sha256(path: Path) -> str:
    """Streaming SHA256 of a file (the raw sidecars run to gigabytes)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_manifest(manifest: Path) -> list[tuple[str, str]]:
    """Return [(expected_sha, rel_path), ...] for the raw_*.json lines only.

    Accepts the ``sha256sum`` text/binary line forms: '<hash>  <path>' and
    '<hash> *<path>'. Run-file lines are ignored -- this comparator is
    raw-vs-raw; the KPI run files are the golden comparator's surface.
    """
    entries: list[tuple[str, str]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, rest = line.partition(" ")
        rel = rest.lstrip(" *")
        if Path(rel).name.startswith("raw_") and rel.endswith(".json"):
            entries.append((sha, rel))
    return entries


def run_verify(root: Path, manifest: Path) -> int:
    """Hash each raw sidecar under ``root`` and check it against ``manifest``."""
    if not manifest.is_file():
        print(f"ERROR: manifest not found: {manifest}", file=sys.stderr)
        return 2
    entries = _parse_manifest(manifest)
    if not entries:
        print(f"ERROR: no raw_*.json entries in {manifest}", file=sys.stderr)
        return 2

    missing: list[str] = []
    mismatched: list[str] = []
    checked = 0
    for expected_sha, rel in entries:
        target = root / rel
        if not target.is_file():
            missing.append(rel)
            continue
        checked += 1
        if _sha256(target) != expected_sha:
            mismatched.append(rel)

    for rel in missing:
        print(f"MISSING  {_combo_run(rel)}  ({rel})")
    for rel in mismatched:
        print(f"MISMATCH {_combo_run(rel)}  ({rel})")

    ok = not missing and not mismatched
    print(
        f"\nverify  manifest={manifest}  raw_entries={len(entries)}  "
        f"checked={checked}  missing={len(missing)}  mismatched={len(mismatched)}"
    )
    print("RESULT:", "MATCH" if ok else "MISMATCH")
    hint = _replication_shortfall_hint(entries, missing)
    if hint:
        print(hint)
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# diff -- structural compare of two raw-sidecar directories                     #
# --------------------------------------------------------------------------- #

def _walk(golden: Any, cand: Any, path: str) -> Iterator[str]:
    """Yield a locator string for every leaf where ``golden`` and ``cand`` differ.

    dicts: order-insensitive (compare key sets, recurse shared keys).
    lists: order-sensitive (compare length, recurse by index).
    scalars (incl. float): exact ``!=``.
    Type mismatches are reported at the node rather than recursed into.
    """
    if isinstance(golden, dict) and isinstance(cand, dict):
        golden_keys, cand_keys = set(golden), set(cand)
        for key in sorted(golden_keys - cand_keys, key=repr):
            yield f"{path}[{key!r}]: only in golden"
        for key in sorted(cand_keys - golden_keys, key=repr):
            yield f"{path}[{key!r}]: only in candidate"
        for key in sorted(golden_keys & cand_keys, key=repr):
            yield from _walk(golden[key], cand[key], f"{path}[{key!r}]")
    elif isinstance(golden, list) and isinstance(cand, list):
        if len(golden) != len(cand):
            yield f"{path}: list length golden={len(golden)} cand={len(cand)}"
        for index in range(min(len(golden), len(cand))):
            yield from _walk(golden[index], cand[index], f"{path}[{index}]")
    elif type(golden) is not type(cand):
        yield f"{path}: type golden={type(golden).__name__} cand={type(cand).__name__}"
    elif golden != cand:
        yield f"{path}: golden={golden!r} cand={cand!r}"


def _raw_index(root: Path) -> dict[str, Path]:
    """Map '<combo>/raw_NNN.json' -> path for every raw sidecar under ``root``."""
    index: dict[str, Path] = {}
    for raw_path in sorted(root.rglob(RAW_GLOB)):
        index[raw_path.relative_to(root).as_posix()] = raw_path
    return index


def run_diff(golden_dir: Path, cand_dir: Path) -> int:
    """Structurally diff every shared raw sidecar between two directories."""
    for label, root in (("golden", golden_dir), ("candidate", cand_dir)):
        if not root.is_dir():
            print(f"ERROR: {label} dir not found: {root}", file=sys.stderr)
            return 2

    golden = _raw_index(golden_dir)
    cand = _raw_index(cand_dir)

    ok = True
    only_golden = sorted(set(golden) - set(cand))
    only_cand = sorted(set(cand) - set(golden))
    if only_golden:
        ok = False
        print(f"Sidecars only in golden ({len(only_golden)}): {only_golden[:5]}...")
    if only_cand:
        ok = False
        print(f"Sidecars only in candidate ({len(only_cand)}): {only_cand[:5]}...")

    shared = sorted(set(golden) & set(cand))
    mismatched_files = 0
    for rel in shared:
        golden_data = json.loads(golden[rel].read_text(encoding="utf-8"))
        cand_data = json.loads(cand[rel].read_text(encoding="utf-8"))
        if golden_data == cand_data:
            continue
        mismatched_files += 1
        ok = False
        locator = _combo_run(rel)
        print(f"MISMATCH {locator}  ({rel}):")
        for shown, line in enumerate(_walk(golden_data, cand_data, "")):
            if shown >= MAX_DIFFS_PER_FILE:
                print(f"    ... more than {MAX_DIFFS_PER_FILE} divergences, truncated")
                break
            print(f"    {locator} ::{line}")

    print(
        f"\ndiff  golden={golden_dir}  candidate={cand_dir}  "
        f"compared={len(shared)} sidecars  mismatched={mismatched_files}"
    )
    print("RESULT:", "MATCH" if ok else "MISMATCH")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# CLI                                                                           #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="hash raw sidecars against the manifest")
    verify.add_argument(
        "--root", type=Path, default=Path("."),
        help="repo root the manifest paths are relative to (default: .)",
    )
    verify.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST,
        help=f"sha256 manifest (default: {DEFAULT_MANIFEST})",
    )

    diff = sub.add_parser("diff", help="structurally compare two raw-sidecar dirs")
    diff.add_argument("golden", type=Path, help="golden raw-sidecar directory")
    diff.add_argument("candidate", type=Path, help="candidate raw-sidecar directory")

    args = parser.parse_args(argv)
    if args.command == "verify":
        return run_verify(args.root, args.manifest)
    return run_diff(args.golden, args.candidate)


if __name__ == "__main__":
    sys.exit(main())
