"""Spec generation must work without site packages or simulation dependencies."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


class LightweightSpec(unittest.TestCase):
    def test_spec_without_site_packages_or_simulation_imports(self):
        components = Path(__file__).resolve().parents[1] / "components"
        code = """
import json, sys
sys.path.insert(0, sys.argv[1])
def deny_simulation(event, args):
    if event == "import" and args[0].split(".")[0] in {"mujoco", "numpy", "torch", "warp"}:
        raise RuntimeError("Simulation dependency imported during spec generation: " + args[0])
sys.addaudithook(deny_simulation)
from sim2realbench.g1.terrain import make_spec
spec = make_spec(2)
for invalid in [True, -1, 1000, 1.0, "0"]:
    try:
        make_spec(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid index accepted")
print(json.dumps(spec))
"""
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", code, str(components)],
            check=True,
            capture_output=True,
            text=True,
        )
        spec = json.loads(result.stdout)
        self.assertEqual("control-transfer-instance/2", spec["schema"])
        self.assertEqual("same-plant", spec["transfer_track"])
        self.assertEqual(4, len(spec["adaptation"]))
        self.assertEqual(12, len(spec["held_out"]))
        self.assertEqual({12100}, {case["plant_seed"] for case in spec["adaptation"] + spec["held_out"]})


if __name__ == "__main__":
    unittest.main()
