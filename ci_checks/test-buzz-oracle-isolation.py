#!/usr/bin/env python3
"""Check the Buzz oracle's development-tool boundary, without simulating it."""
import ast
import importlib
import importlib.abc
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PREFIX = "topogym.planning.calibration_tools"


class DenyCalibrationImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == PREFIX or fullname.startswith(PREFIX + "."):
            raise AssertionError("Oracle depends on development tools: " + fullname)


class BuzzOracleIsolation(unittest.TestCase):
    def test_oracle_imports_without_calibration_tools(self):
        files = sorted((ROOT / "topogym/planning/buzz_wire_3d").glob("*.py"))
        files += sorted((ROOT / "scripts/oracle_runners").glob("run_buzz_wire*policy.py"))
        # The optional v12 runner freezes and imports this upstream helper.
        files.append(ROOT / "harbor_templates/topogym/common/rcb_topogym.py")
        self.assertFalse(any(name.startswith(PREFIX) for name in sys.modules),
                         "Run this check in a fresh Python process")
        guard = DenyCalibrationImports()
        sys.meta_path.insert(0, guard)
        try:
            for file in files:
                # Also inspect imports nested in functions that cold imports
                # do not execute. The guard covers dependencies loaded indirectly.
                for node in ast.walk(ast.parse(file.read_text())):
                    names = ([v.name for v in node.names] if isinstance(node, ast.Import)
                             else [node.module or ""] if isinstance(node, ast.ImportFrom)
                             else [])
                    self.assertFalse(any("calibration_tools" in n for n in names), str(file))
                name = ".".join(file.relative_to(ROOT).with_suffix("").parts)
                importlib.import_module(name.removesuffix(".__init__"))
            from topogym.config.registry import task_definition
            for variant in ("medium", "hard"):
                task_definition("buzz_wire_3d", variant)(seed=0).build_layout().validate()
        finally:
            sys.meta_path.remove(guard)
        self.assertFalse(any(name.startswith(PREFIX) for name in sys.modules))


if __name__ == "__main__":
    unittest.main()
