"""Static CI checks: this module and family spec require only the Python stdlib."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.control_transfer.trusted.go2_spec import TASKS, make_spec
from scripts.control_transfer.control_public.go2_data import default_policy, validate


class StaticSpec(unittest.TestCase):
    def test_all_families_generate_without_site_packages(self):
        code = """
import json, sys
from scripts.control_transfer.trusted.go2_spec import TASKS, make_spec
from scripts.control_transfer.trusted.go2 import make_spec as compatible, validate
for task in TASKS:
    spec = make_spec(2, task)
    assert spec == compatible(2, task)
    json.dumps(spec, allow_nan=False)
    validate(spec['public']['default_policy'])
assert not any(name.split('.')[0] in ('numpy', 'mujoco', 'torch') for name in sys.modules)
assert 'scripts.control_transfer.control_public.go2' not in sys.modules
assert not any('.quadrupedbench' in name for name in sys.modules)
"""
        subprocess.run([sys.executable, "-S", "-c", code], cwd=Path(__file__).resolve().parents[3], check=True)

    def test_banks_and_numeric_artifact(self):
        for task in TASKS:
            spec = make_spec(2, task)
            self.assertEqual(spec["schema"], "control-transfer-instance/2")
            self.assertEqual(spec["transfer_track"], "same-plant")
            banks = spec["bank"]
            self.assertEqual({c["plant_seed"] for b in banks.values() for c in b}, {12100})
            self.assertEqual(len(banks["adaptation"]), 3)
            self.assertEqual(len(banks["held_out"]), 10)
            self.assertEqual(len(spec["public"]["channels"]), 37)
            self.assertEqual(json.loads(validate(default_policy())), spec["public"]["default_policy"])


if __name__ == "__main__":
    unittest.main()
