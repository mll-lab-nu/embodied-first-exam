"""The DexJoCo privileged verifier (shared/grade.py) on a stand-in Session, and the frozen instances' `meta`; needs
numpy, no MuJoCo.

    python3 scripts/dexjoco/tests/test_grade_privileged.py

- A rebuilt instance that does not match its recorded hash is no verdict on the agent: `instance_mismatch`,
  `grader_error` and `infra_error` = 1, nothing replayed (board 0105, B6-3; before, the agent's 0 with infra_error 0).
- The agent reads instance.npz (/app/instance.npz) and every reference is the actions of the demonstration the instance
  was restored from: no committed instance names it (board 0105, B-M3); the tooling refuses to save such a `meta`, and
  the generator refuses an instance that carries one.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEXJOCO = HERE.parent
GRADE = DEXJOCO / "shared" / "grade.py"

# what grade.py uses of rcb_dexjoco; STUB_EXACT = 0: the image no longer rebuilds the frozen instance
STUB_TOOL = '''import os
SESSION_LOG = ""
MAX_TRAJECTORY_ROWS = 50_000
REPLAYS = []


class PrimitiveError(RuntimeError):
    pass


def blas_threads():
    return {"visible_cpus": 8, "openblas_num_threads_env": 4, "blas_threads": 4, "threads_ok": 1}


def threads_message(t):
    return "stub"


class Session:
    action_dim = 23

    def __init__(self, task, instance=None):
        self.instance_exact = os.environ["STUB_EXACT"] == "1"
        self.instance_sha = "recorded"

    def state_sha(self):
        return "recorded" if self.instance_exact else "other"

    def replay(self, acts):
        open(os.environ["STUB_REPLAYS"], "a").write("replay\\n")
        ok = os.environ.get("STUB_SUCCESS", "1") == "1"
        return {"success": ok, "state_sha": "end", "steps": len(acts), "reason": "success" if ok else None,
                "replayed_rows": len(acts)}

    def close(self):
        pass
'''


class InstanceMismatch(unittest.TestCase):
    def grade(self, exact: bool, success: bool = True) -> tuple[str, dict, int]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); log = d / "log"
            shutil.copy(GRADE, d / "grade.py")
            (d / "rcb_dexjoco.py").write_text(STUB_TOOL)
            np.savez(d / "trajectory.npz", task="water_plant", actions=np.zeros((5, 23)))
            r = subprocess.run([sys.executable, "-B", str(d / "grade.py"), "--family", "water_plant", "--instance", "x",
                                "--traj", str(d / "trajectory.npz"), "--no-video"], capture_output=True, text=True, cwd=d,
                               env={**os.environ, "RCB_VERIFIER_LOG_DIR": str(log), "STUB_EXACT": str(int(exact)),
                                    "STUB_SUCCESS": str(int(success)), "STUB_REPLAYS": str(d / "replays")})
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            n = len((d / "replays").read_text().splitlines()) if (d / "replays").exists() else 0
            return (log / "reward.txt").read_text().strip(), json.loads((log / "reward.json").read_text()), n

    def test_exact_instance_success(self):
        txt, rw, n = self.grade(True)
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["grader_error"], rw["instance_ok"], n), ("1", 1, 0, 0, 1, 2), rw)

    def test_exact_instance_failure_is_the_agents_0(self):
        txt, rw, n = self.grade(True, success=False)
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["grader_error"]), ("0", 0, 0, 0), rw)

    def test_an_instance_that_does_not_rebuild_is_no_verdict(self):
        txt, rw, n = self.grade(False)
        self.assertEqual((txt, rw["success"], rw["infra_error"], rw["grader_error"], rw["instance_mismatch"],
                          rw["instance_ok"], n), ("0", 0, 1, 1, 1, 0, 0), rw)


class NoProvenance(unittest.TestCase):
    def test_no_committed_instance_names_its_demonstration(self):
        for d in sorted((DEXJOCO / "instances").iterdir()):
            with np.load(d / "instance.npz", allow_pickle=False) as z:
                meta = json.loads(str(z["meta"]))
            self.assertEqual(meta, {"dexjoco": "8d23b0f"}, d.name)

    def test_the_tooling_refuses_a_meta_with_provenance(self):
        sys.path.insert(0, str(DEXJOCO / "shared"))
        import rcb_dexjoco as R      # numpy only at import (MuJoCo is imported by a Session)
        R.check_instance_meta({"dexjoco": "8d23b0f"})
        for bad in ({"demo": "x"}, {"source": "x"}, {"note": "water_plant_demo_10_2026-02-05"},
                    {"origin": "DexJoCo-Datasets-Raw episode 3"}, {"demo_id": 3}):
            with self.assertRaises(ValueError, msg=bad):
                R.check_instance_meta(bad)

    @unittest.skipIf(sys.version_info < (3, 12), "generate.py needs Python 3.12 (f-strings)")
    def test_the_generator_refuses_an_instance_with_provenance(self):
        sys.path.insert(0, str(DEXJOCO))
        import generate as G
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "instance.npz"
            np.savez_compressed(p, task="water_plant", physics=np.zeros(3), meta=json.dumps({"dexjoco": "8d23b0f"}))
            self.assertEqual(G.instance_meta(p), {"dexjoco": "8d23b0f"})
            G.check_instance(p)
            np.savez_compressed(p, task="water_plant", meta=json.dumps({"source": "DexJoCo-Datasets-Raw", "demo": "d"}))
            with self.assertRaises(SystemExit):
                G.check_instance(p)


if __name__ == "__main__":
    unittest.main()
