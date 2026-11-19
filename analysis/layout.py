"""Where baseline runs live on disk.

``{out_root}/{scenario}/{policy}__{strategy}/`` holds ``run_NNN.json``,
``raw_NNN.json`` and ``summary.csv`` for one inventory-policy x stock-strategy combo.
"""
from pathlib import Path
from typing import Iterable, Tuple

COMBO_SEPARATOR = "__"
SUMMARY_FILENAME = "summary.csv"
RUN_GLOB = "*/run_*.json"


def combo_label(inventory_policy: str, stock_strategy: str) -> str:
    return f"{inventory_policy}{COMBO_SEPARATOR}{stock_strategy}"


def split_combo_label(label: str) -> Tuple[str, str]:
    """Split a ``policy__strategy`` combo label into ``(policy, strategy)``.

    Raises ``ValueError`` on any label that is not exactly one ``__`` join, so an
    unexpected directory name fails loudly instead of mis-styling a point.
    """
    parts = label.split(COMBO_SEPARATOR)
    if len(parts) != 2:
        raise ValueError(f"Expected a 'policy__strategy' combo label, got {label!r}")
    return parts[0], parts[1]


def run_filename(replication_index: int) -> str:
    return f"run_{replication_index:03d}.json"


def raw_filename(replication_index: int) -> str:
    return f"raw_{replication_index:03d}.json"


def iter_combo_summaries(path: Path, root: bool) -> Iterable[Tuple[str, Path]]:
    """Yield ``(config_label, summary_csv_path)`` for each configuration under ``path``.

    Scenario mode (``root=False``): ``path`` is a scenario dir; each immediate
    subdir is a combo holding ``summary.csv``; the label is the combo name
    (e.g. ``push__on_demand``). Root mode (``root=True``): ``path`` holds scenario
    dirs, each holding combo dirs; the label is ``{scenario}__{combo}`` so the
    frontier spans (scenario x combo). Sorted so the artifact is deterministic.
    """
    glob_pattern = f"*/*/{SUMMARY_FILENAME}" if root else f"*/{SUMMARY_FILENAME}"
    for summary_path in sorted(path.glob(glob_pattern)):
        combo_dir = summary_path.parent
        if root:
            yield f"{combo_dir.parent.name}{COMBO_SEPARATOR}{combo_dir.name}", summary_path
        else:
            yield combo_dir.name, summary_path
