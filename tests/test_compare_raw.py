"""Tests for the raw-vs-raw comparator (compare_raw.py).

Locks the two gate behaviours issues 08-10 lean on: an unchanged candidate
reports MATCH with exit 0, and a single perturbed value in one history series
is reported as a MISMATCH with a locator naming the series and index. Also
covers the manifest byte gate (OK vs a corrupted sidecar).
"""
import hashlib
import json

import compare_raw


def _raw_payload(processing_value=42.0):
    """A minimal raw sidecar shaped like build_raw_payload output (enums already
    rewritten to .value), with one processing-history series we can perturb."""
    return {
        "generation_history": {"17 02 01": [1.0, 2.0, 3.0]},
        "processing_history": {"mdf": [10.0, 20.0, processing_value]},
        "consumption_events": [{"day": 5, "amount": 7.5}],
    }


def _write_sidecar(combo_dir, index, payload):
    combo_dir.mkdir(parents=True, exist_ok=True)
    path = combo_dir / f"raw_{index:03d}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# diff                                                                          #
# --------------------------------------------------------------------------- #

def test_diff_identical_reports_match(tmp_path, capsys):
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "pull__on_demand", 0, _raw_payload())
    _write_sidecar(cand / "pull__on_demand", 0, _raw_payload())

    code = compare_raw.run_diff(golden, cand)

    assert code == 0
    assert "RESULT: MATCH" in capsys.readouterr().out


def test_diff_perturbed_value_reports_locator(tmp_path, capsys):
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "push__reorder_90", 7, _raw_payload(processing_value=42.0))
    # One value, one entity: last element of the mdf processing series.
    _write_sidecar(cand / "push__reorder_90", 7, _raw_payload(processing_value=42.0001))

    code = compare_raw.run_diff(golden, cand)

    out = capsys.readouterr().out
    assert code == 1
    assert "RESULT: MISMATCH" in out
    # Locator must name combo/run, the series, and the index that moved.
    assert "push__reorder_90/raw_007" in out
    assert "processing_history" in out
    assert "['mdf'][2]" in out
    assert "42.0001" in out


def test_diff_float_compare_is_exact(tmp_path, capsys):
    """A last-ULP drift must register -- no tolerance."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    base = 0.1 + 0.2  # 0.30000000000000004
    _write_sidecar(golden / "pull__reorder_50", 0, {"h": {"x": [base]}})
    _write_sidecar(cand / "pull__reorder_50", 0, {"h": {"x": [0.3]}})

    assert compare_raw.run_diff(golden, cand) == 1
    assert "RESULT: MISMATCH" in capsys.readouterr().out


def test_diff_dict_key_order_insensitive(tmp_path, capsys):
    """Reordered dict keys are not a regression (a module split may reorder)."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "c", 0, {"a": 1, "b": 2})
    _write_sidecar(cand / "c", 0, {"b": 2, "a": 1})

    assert compare_raw.run_diff(golden, cand) == 0
    assert "RESULT: MATCH" in capsys.readouterr().out


def test_diff_list_order_sensitive(tmp_path, capsys):
    """Reordered list elements ARE a regression (time-series order is meaningful)."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "c", 0, {"series": [1, 2, 3]})
    _write_sidecar(cand / "c", 0, {"series": [3, 2, 1]})

    assert compare_raw.run_diff(golden, cand) == 1
    # First differing index is reported, not just a bare exit code.
    assert "['series'][0]: golden=1 cand=3" in capsys.readouterr().out


def test_diff_dropped_series_key_reports_locator(tmp_path, capsys):
    """The refactor silently dropping a history series must be flagged by key name."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "pull__on_demand", 3, _raw_payload())
    dropped = _raw_payload()
    del dropped["processing_history"]
    _write_sidecar(cand / "pull__on_demand", 3, dropped)

    code = compare_raw.run_diff(golden, cand)
    out = capsys.readouterr().out
    assert code == 1
    assert "pull__on_demand/raw_003" in out
    assert "['processing_history']: only in golden" in out


def test_diff_truncated_series_reports_length(tmp_path, capsys):
    """A time-series losing samples is a regression, located by length."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "c", 0, {"environmental_history": {"co2": [1.0, 2.0, 3.0]}})
    _write_sidecar(cand / "c", 0, {"environmental_history": {"co2": [1.0, 2.0]}})

    code = compare_raw.run_diff(golden, cand)
    out = capsys.readouterr().out
    assert code == 1
    assert "['co2']: list length golden=3 cand=2" in out


def test_diff_type_change_reports_type(tmp_path, capsys):
    """A series whose container type changes (list -> dict) is flagged as a type diff."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "c", 0, {"event_history": [1, 2]})
    _write_sidecar(cand / "c", 0, {"event_history": {"0": 1}})

    code = compare_raw.run_diff(golden, cand)
    out = capsys.readouterr().out
    assert code == 1
    assert "type golden=list cand=dict" in out


def test_diff_missing_candidate_sidecar_reports_mismatch(tmp_path, capsys):
    """A whole sidecar vanishing from the candidate is a mismatch, not a silent pass."""
    golden = tmp_path / "golden"
    cand = tmp_path / "cand"
    _write_sidecar(golden / "push__on_demand", 0, _raw_payload())
    _write_sidecar(golden / "push__on_demand", 1, _raw_payload())
    _write_sidecar(cand / "push__on_demand", 0, _raw_payload())  # run 1 absent

    code = compare_raw.run_diff(golden, cand)
    out = capsys.readouterr().out
    assert code == 1
    assert "only in golden" in out
    assert "push__on_demand/raw_001.json" in out


# --------------------------------------------------------------------------- #
# verify                                                                        #
# --------------------------------------------------------------------------- #

def _write_manifest(tmp_path, entries):
    """entries: list of (relpath, sha) -> sha256sum-format manifest file."""
    lines = [f"{sha}  {rel}" for rel, sha in entries]
    manifest = tmp_path / "manifest.sha256"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def test_verify_matches_committed_hash(tmp_path, capsys):
    root = tmp_path / "root"
    rel = "outputs/baseline/Baseline/pull__on_demand/raw_000.json"
    target = root / rel
    target.parent.mkdir(parents=True)
    body = json.dumps(_raw_payload()).encode("utf-8")
    target.write_bytes(body)
    manifest = _write_manifest(tmp_path, [(rel, hashlib.sha256(body).hexdigest())])

    assert compare_raw.run_verify(root, manifest) == 0
    assert "RESULT: MATCH" in capsys.readouterr().out


def test_verify_flags_corrupted_sidecar(tmp_path, capsys):
    root = tmp_path / "root"
    rel = "outputs/baseline/Baseline/pull__on_demand/raw_000.json"
    target = root / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"changed": true}')
    # Manifest records the hash of DIFFERENT bytes -> must be flagged.
    manifest = _write_manifest(tmp_path, [(rel, hashlib.sha256(b"original").hexdigest())])

    code = compare_raw.run_verify(root, manifest)
    out = capsys.readouterr().out
    assert code == 1
    assert "MISMATCH" in out
    assert "pull__on_demand/raw_000" in out


def test_verify_flags_missing_sidecar(tmp_path, capsys):
    """The raw_NNN.json naming is load-bearing: if a refactor renames or fails to
    regenerate a sidecar, the manifest entry has no file and verify must flag it."""
    root = tmp_path / "root"
    rel = "outputs/baseline/Baseline/pull__on_demand/raw_000.json"
    # File deliberately NOT created under root -> MISSING.
    manifest = _write_manifest(tmp_path, [(rel, "ab" * 32)])

    code = compare_raw.run_verify(root, manifest)
    out = capsys.readouterr().out
    assert code == 1
    assert "MISSING" in out
    assert "pull__on_demand/raw_000" in out


def test_verify_errors_on_manifest_without_raw_entries(tmp_path):
    """A manifest with only run_*.json lines yields no raw work -> usage error (2)."""
    manifest = _write_manifest(tmp_path, [("outputs/x/run_000.json", "cd" * 32)])
    assert compare_raw.run_verify(tmp_path, manifest) == 2


def test_verify_ignores_run_files(tmp_path):
    """Only raw_*.json lines are checked; run_*.json lines are out of scope."""
    manifest = _write_manifest(
        tmp_path,
        [("outputs/x/run_000.json", "deadbeef" * 8)],  # bogus hash, but ignored
    )
    entries = compare_raw._parse_manifest(manifest)
    assert entries == []


# --------------------------------------------------------------------------- #
# verify -- rep-count shortfall hint (HANDOFF landmine #1 inverse)              #
# --------------------------------------------------------------------------- #

def _write_shortfall_fixture(tmp_path, combos, expected_reps, present_reps):
    """Build a root + manifest for `combos` combos at `expected_reps` reps/combo,
    with only the first `present_reps` sidecars per combo actually on disk.

    Returns (root, manifest). Present sidecars hash-match their manifest entry, so
    the only failure is the uniform shortfall the hint must explain.
    """
    root = tmp_path / "root"
    entries = []
    for combo in range(combos):
        for rep in range(expected_reps):
            rel = f"outputs/baseline/Baseline/combo_{combo}/raw_{rep:03d}.json"
            body = json.dumps({"rep": rep}).encode("utf-8")
            if rep < present_reps:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            entries.append((rel, hashlib.sha256(body).hexdigest()))
    return root, _write_manifest(tmp_path, entries)


def test_verify_prints_rep_shortfall_hint(tmp_path, capsys):
    """A uniform rep-shortfall (10-vs-100 footgun) must read as wrong-rep-count,
    not data loss: verify prints an actionable hint naming both rep counts."""
    # Manifest expects 3 reps across 2 combos (6 sidecars); only 1 rep/combo present.
    root, manifest = _write_shortfall_fixture(
        tmp_path, combos=2, expected_reps=3, present_reps=1
    )

    code = compare_raw.run_verify(root, manifest)
    out = capsys.readouterr().out

    assert code == 1  # a genuine shortfall is still a verify failure
    assert "HINT: rep-count shortfall" in out
    assert "expects 3 reps/combo" in out
    assert "you regenerated 1" in out


def test_verify_no_hint_when_counts_match(tmp_path, capsys):
    """No shortfall -> no hint (the hint must not fire on a clean MATCH)."""
    root, manifest = _write_shortfall_fixture(
        tmp_path, combos=2, expected_reps=3, present_reps=3
    )

    code = compare_raw.run_verify(root, manifest)
    out = capsys.readouterr().out

    assert code == 0
    assert "RESULT: MATCH" in out
    assert "rep-count shortfall" not in out


def test_verify_no_hint_on_nonuniform_loss(tmp_path, capsys):
    """A ragged partial loss is real data loss, not a rep slip -> no misleading hint."""
    # combo_0 keeps all 3 reps, combo_1 only 1 -> present counts differ -> not uniform.
    root = tmp_path / "root"
    entries = []
    for combo, present in ((0, 3), (1, 1)):
        for rep in range(3):
            rel = f"outputs/baseline/Baseline/combo_{combo}/raw_{rep:03d}.json"
            body = json.dumps({"rep": rep}).encode("utf-8")
            if rep < present:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            entries.append((rel, hashlib.sha256(body).hexdigest()))
    manifest = _write_manifest(tmp_path, entries)

    code = compare_raw.run_verify(root, manifest)
    out = capsys.readouterr().out

    assert code == 1
    assert "rep-count shortfall" not in out
