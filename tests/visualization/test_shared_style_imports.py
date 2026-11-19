"""Figure scripts share styling and summary readers through library modules, not each other (issue #4)."""
import ast
from pathlib import Path

VISUALIZATION_DIR = Path(__file__).resolve().parents[2] / "visualization"
SHARED_MODULES = {"visualization.figure_style", "visualization.visualization_utils"}
# Runs the Plotly comparison scripts in turn, so it imports their entry points.
SUITE_RUNNER = "scenario_comparison.py"


def _visualization_imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [f"visualization.{node.module}" if node.level == 1 else node.module or ""]
        else:
            continue
        yield from (module for module in modules if module.startswith("visualization."))


def test_no_figure_script_imports_from_another_figure_script():
    cross_imports = {
        (path.name, module)
        for path in sorted(VISUALIZATION_DIR.glob("*.py"))
        if path.name != SUITE_RUNNER
        for module in _visualization_imports(path)
        if module not in SHARED_MODULES
    }

    assert cross_imports == set()
