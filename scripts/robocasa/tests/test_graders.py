"""The RoboCasa-series verifiers (shared/grade_standard.py, shared/grade_privileged.py; RoboCasa365 and RoboCasa-GR1
carry byte copies) on forged records: standard library only, no simulator.

    python3 scripts/robocasa/tests/test_graders.py
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "shared"


def load(name: str, **paths):
    spec = importlib.util.spec_from_file_location(f"casa_{name}", SHARED / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in paths.items():
        setattr(mod, k, v)
    return mod


class Standard(unittest.TestCase):
    def grade(self, final: dict) -> dict:
        with tempfile.TemporaryDirectory() as d:
            data, log = Path(d, "data"), Path(d, "log")
            data.mkdir()
            (data / "final.json").write_text(json.dumps(final))
            load("grade_standard", DATA=str(data), LOG=str(log)).main()
            self.assertEqual((log / "reward.txt").read_text().strip(), str(json.loads((log / "reward.json").read_text())["success"]))
            return json.loads((log / "reward.json").read_text())

    def test_evidence_fields_of_the_wrong_type_cost_no_verdict(self):
        """Before: int("many") raised and the trial had no reward file."""
        ok = {"success": True, "deterministic": True, "live_success": True, "replay_success": True, "finalized": True}
        r = self.grade({**ok, "control_steps": "many", "calls": [3], "elapsed_s": {"s": 1}, "final_reward": "1.0x"})
        self.assertEqual((r["success"], r["infra_error"], r["control_steps"], r["calls"], r["elapsed_s"]), (1, 0, 0, 0, 0.0))
        r = self.grade({**ok, "success": False, "live_success": False, "control_steps": 7, "elapsed_s": 2.5})
        self.assertEqual((r["success"], r["infra_error"], r["control_steps"], r["elapsed_s"]), (0, 0, 7, 2.5))


class Privileged(unittest.TestCase):
    def test_a_verifier_that_cannot_import_its_tool_is_a_grader_error(self):
        """Before: the import failed inside the trajectory check and was booked as the agent's invalid trajectory."""
        self.assertNotIn("casa_tool", sys.modules)
        with tempfile.TemporaryDirectory() as d:
            traj, log = Path(d, "trajectory.npz"), Path(d, "log")
            traj.write_bytes(b"anything")
            load("grade_privileged", TRAJ=traj, LOG=log).main()
            r = json.loads((log / "reward.json").read_text())
            self.assertEqual((r["success"], r["grader_error"], r["invalid_trajectory"]), (0, 1, 0), r)
            self.assertIn("casa_tool", (log / "grader_error.txt").read_text())


if __name__ == "__main__":
    unittest.main()
