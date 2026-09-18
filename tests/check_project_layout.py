"""Catch active imports and task-card asset references broken by archival."""
import ast
from pathlib import Path
import unittest

from topogym.tasks.catalog import TASK_IDS, load_card

ROOT = Path(__file__).resolve().parents[1]


class ProjectLayoutChecks(unittest.TestCase):
    def test_current_absolute_imports_resolve_without_archive(self):
        for folder in ("topogym", "demos", "scripts", "tests"):
            for path in (ROOT / folder).rglob("*.py"):
                for node in ast.walk(ast.parse(path.read_text())):
                    modules = []
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                        modules = [node.module]
                    for module in modules:
                        self.assertFalse(module == "legacy" or module.startswith("legacy."), (path, module))
                        if module.split(".")[0] not in {"topogym", "demos"}:
                            continue
                        target = ROOT.joinpath(*module.split("."))
                        self.assertTrue(target.is_dir() or target.with_suffix(".py").is_file(),
                                        (path.relative_to(ROOT), module))

    def test_local_task_card_assets_exist(self):
        for task_id in TASK_IDS:
            card = load_card(task_id)
            for asset in card["assets"]:
                location = asset.get("location", "")
                if location.startswith(("topogym/", "configs/", "assets/")):
                    with self.subTest(task=task_id, location=location):
                        self.assertTrue((ROOT / location).exists())


if __name__ == "__main__":
    unittest.main()
