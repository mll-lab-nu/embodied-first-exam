"""Authoring tests: positive oracle, negative controls, trust boundary and hand selection for paper_half_fold.

Run from the repository root (about 4 minutes on one core; the physics is 40 substeps per control):

    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand OPENBLAS_NUM_THREADS=1 \
        python -m pytest -q scripts/dexhand/families/paper_half_fold/tests

The bit-for-bit comparison with the accepted episode's saved states needs the workspace evidence directory and lives
in `tools/verify_oracle.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
SHARED = REPO / "scripts/dexhand/shared"
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
for path in (str(SHARED), str(FAMILY)):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
for name in ("runtime", "replay", "hands", "shell"):
    sys.modules.pop(name, None)

import hands  # noqa: E402  (shared copy, as in a generated task)
import runtime  # noqa: E402
from runtime import Session  # noqa: E402

ORACLE = FAMILY / "solution/trajectory.npz"
FROZEN_SHARPA_MODEL = "665706cd6ef8a63dddba743a9d715e7ca289ccc16f9f0514c4cbcd72693afd51"


def oracle_rows() -> np.ndarray:
    with np.load(ORACLE, allow_pickle=False) as archive:
        return archive["actions"].copy()


def run_replay(traj: Path, *extra: str) -> tuple[dict, int]:
    """replay.py in a fresh process, laid out like a task directory (family files + shared hands.py)."""
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "out.json"
        env = dict(os.environ, PYTHONPATH=f"{FAMILY}{os.pathsep}{SHARED}", PYTHONDONTWRITEBYTECODE="1")
        env.pop("DEXHAND_HAND", None)
        done = subprocess.run(
            [sys.executable, str(FAMILY / "replay.py"), "--task", "paper_half_fold", "--traj", str(traj),
             "--out", str(out), *extra],
            env=env, capture_output=True, text=True, timeout=900,
        )
        result = json.loads(out.read_text()) if out.is_file() else {}
        return result, done.returncode


def save(path: Path, actions, **members) -> Path:
    np.savez_compressed(path, actions=np.asarray(actions), **members)
    return path


class OracleTests(unittest.TestCase):
    """One in-process oracle episode feeds several checks (snapshots avoid repeating long prefixes)."""

    @classmethod
    def setUpClass(cls):
        cls.rows = oracle_rows()
        s = Session()
        cls.model_sha = s.model_sha256
        cls.snapshots = {}
        cls.first_success = None
        for i, row in enumerate(cls.rows):
            if i in (60, 585, 600):
                cls.snapshots[i] = s.snapshot()
            s.step(row)
            if s.success and cls.first_success is None:
                cls.first_success = i + 1
        cls.final = s.status()
        cls.features = s.features()
        s.step(cls.rows[-1])  # a row after success is not executed
        cls.after = s.status()
        cls.session = s

    @classmethod
    def tearDownClass(cls):
        cls.session.close()

    def test_frozen_model_identity(self):
        self.assertEqual(self.model_sha, FROZEN_SHARPA_MODEL)

    def test_oracle_succeeds_at_its_last_row(self):
        self.assertTrue(self.final["success"])
        self.assertEqual(self.final["reason"], "success")
        self.assertEqual(self.first_success, 1108)  # the accepted episode's last row; 250 hold rows follow
        self.assertEqual(self.final["stage"], 4)
        f = self.features
        self.assertGreater(f["fold_angle_rad"], 2.6)
        self.assertGreater(f["crease_angle_rad"], 2.2)
        self.assertGreaterEqual(f["crease_coverage"], 0.9)
        self.assertLess(f["edge_alignment_m"], 0.018)
        self.assertEqual(f["hand_contacts"], 0)
        self.assertTrue(f["on_table"])

    def test_success_is_terminal(self):
        self.assertEqual(self.after["steps"], self.final["steps"])
        self.assertEqual(self.after["state_sha"], self.final["state_sha"])

    def test_snapshot_restore_is_exact(self):
        s = self.session
        s.restore(self.snapshots[600])
        for row in self.rows[600:700]:
            s.step(row)
        first = s.state_sha()
        s.restore(self.snapshots[600])
        for row in self.rows[600:700]:
            s.step(row)
        self.assertEqual(first, s.state_sha())

    def test_partial_fold_without_crease_press_fails(self):
        s = self.session
        s.restore(self.snapshots[585])  # fold, release and reposition done; skip the crease press
        hold = self.rows[584].copy()
        hold[2] = 0.425
        for _ in range(400):
            s.step(hold)
        f = s.features()
        self.assertFalse(s.success)
        self.assertIsNone(s.failure)
        self.assertGreater(f["fold_angle_rad"], 2.6)  # folded and released ...
        self.assertLess(f["crease_angle_rad"], 2.2)  # ... but the crease is not permanent
        self.assertLess(s.peak_stage, 2)

    def test_early_stop_before_hold_window_fails(self):
        s = self.session
        s.restore(self.snapshots[600])
        for row in self.rows[600:1050]:
            s.step(row)
        self.assertFalse(s.success)
        self.assertLess(s.released_hold, 100)

    def test_pull_over_table_edge_fails_fast_and_permanently(self):
        s = self.session
        s.restore(self.snapshots[60])
        start = s.hold_action().copy()
        for i in range(1, 101):
            q = start.copy()
            q[2] -= 0.10 * i / 100
            q[0] += 0.04 * i / 100
            s.step(q)
            if s.done:
                break
        self.assertEqual(s.failure, "paper_fell_below_table")
        steps = s.steps
        for row in self.rows[60:200]:  # later rows cannot recover a failure
            s.step(row)
        self.assertEqual(s.steps, steps)
        self.assertFalse(s.success)
        self.assertEqual(s.status()["reason"], "paper_fell_below_table")


class ReplayTests(unittest.TestCase):
    def test_two_fresh_oracle_replays_agree(self):
        a, rc_a = run_replay(ORACLE)
        b, rc_b = run_replay(ORACLE)
        self.assertEqual((rc_a, rc_b), (0, 0))
        self.assertTrue(a["success"] and b["success"])
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertEqual(a["steps"], 1108)
        self.assertEqual(a["n_actions"], 1358)
        self.assertEqual(a["hand"], "sharpa")
        self.assertEqual(a["model_sha256"], FROZEN_SHARPA_MODEL)

    def test_wuji_reference_solution_succeeds_in_two_fresh_replays(self):
        """solution/wuji/trajectory.npz (tools/wuji_gen.py): the packaged Wuji Hand 2.2 oracle."""
        a, rc_a = run_replay(FAMILY / "solution/wuji/trajectory.npz")
        b, rc_b = run_replay(FAMILY / "solution/wuji/trajectory.npz")
        self.assertEqual((rc_a, rc_b), (0, 0))
        self.assertTrue(a["success"] and b["success"])
        self.assertEqual((a["hand"], a["steps"], a["n_actions"]), ("wuji", 554, 620))
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertEqual(a["state_sha"], "adb93d95571774763087564f6ec092412c86e3a9898c67658af008b62276ec2d")

    def test_float32_rounded_oracle_still_succeeds(self):
        """The standard client sends float32 rows; the packaged hold margin absorbs the rounding."""
        with tempfile.TemporaryDirectory() as folder:
            rows = oracle_rows().astype(np.float32)
            result, rc = run_replay(save(Path(folder) / "f32.npz", rows, hand=np.array("sharpa")))
        self.assertEqual(rc, 0)
        self.assertTrue(result["success"])
        self.assertLessEqual(result["steps"], len(rows))

    def test_nop_fails_at_the_episode_budget(self):
        s = Session()
        hold = s.hold_action()
        with tempfile.TemporaryDirectory() as folder:
            result, rc = run_replay(save(Path(folder) / "nop.npz", np.repeat(hold[None], 1500, 0), hand=np.array("sharpa")))
        self.assertEqual(rc, 0)
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "episode_budget")
        self.assertEqual(result["bad_trajectory"], 0)

    def test_forged_metadata_is_ignored_or_rejected(self):
        s = Session()
        hold = np.repeat(s.hold_action()[None], 20, 0)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            forged, rc = run_replay(save(folder / "forged.npz", hold, hand=np.array("sharpa"), success=np.array(True),
                                         stage=np.array(4), released_hold_steps=np.array(100),
                                         config=np.array(json.dumps({"goal_fold_angle_rad": 0.0}))))
            self.assertEqual(rc, 0)
            self.assertFalse(forged["success"])
            self.assertEqual(forged["bad_trajectory"], 0)
            cases = {
                "sharpa rows labelled wuji": save(folder / "a.npz", hold, hand=np.array("wuji")),
                "unknown hand": save(folder / "b.npz", hold, hand=np.array("shadow")),
                "other task": save(folder / "c.npz", hold, task=np.array("assemble_hamburger")),
                "wrong actuator order": save(folder / "d.npz", hold, actuator_names=np.array(s.actuator_names[::-1])),
                "wuji rows labelled sharpa": save(folder / "e.npz", np.zeros((20, 26))),
                "27 columns": save(folder / "f.npz", np.zeros((20, 27))),
                "non-finite": save(folder / "g.npz", np.where(np.arange(28) == 3, np.nan, hold)),
                "out of range": save(folder / "h.npz", hold + np.r_[np.zeros(6), 10.0 * np.ones(22)]),
                "too many rows": save(folder / "i.npz", np.repeat(hold[:1], 1501, 0)),
                "object array": folder / "j.npz",
                "hand array": save(folder / "k.npz", hold, hand=np.array(["sharpa", "wuji"])),
            }
            with open(cases["object array"], "wb") as stream:
                np.savez(stream, actions=np.array([[None] * 28], dtype=object))
            cases["not a zip"] = folder / "l.npz"
            cases["not a zip"].write_bytes(b"PK\x03\x04" + os.urandom(2000))
            truncated = save(folder / "m.npz", hold, hand=np.array("sharpa"))
            truncated.write_bytes(truncated.read_bytes()[:-200])
            cases["truncated archive"] = truncated
            import zipfile
            cases["ambiguous member"] = folder / "n.npz"
            with zipfile.ZipFile(cases["ambiguous member"], "w") as archive:
                buffer = __import__("io").BytesIO()
                np.save(buffer, hold)
                archive.writestr("actions.npy", buffer.getvalue())
                archive.writestr("actions", buffer.getvalue())
            for label, path in cases.items():
                result, rc = run_replay(path)
                self.assertEqual(rc, 0, label)
                self.assertEqual(result.get("bad_trajectory"), 1, label)
                self.assertFalse(result.get("success"), label)
            missing, rc = run_replay(folder / "missing.npz")
            self.assertEqual(rc, 0)
            self.assertFalse(missing["success"])

    def test_trusted_service_hand_must_match(self):
        result, rc = run_replay(ORACLE, "--trusted-service", "--hand", "wuji")
        self.assertEqual(rc, 0)
        self.assertEqual(result["bad_trajectory"], 1)


class HandTests(unittest.TestCase):
    def test_hand_selection(self):
        os.environ["DEXHAND_HAND"] = "wuji"
        try:
            s = Session()
            self.assertEqual(s.hand, "wuji")
        finally:
            del os.environ["DEXHAND_HAND"]
        self.assertEqual(Session().hand, "sharpa")
        with self.assertRaises(ValueError):
            Session(hand="shadow")

    def test_wuji_scene_same_wrist_and_paper(self):
        sharpa, wuji = Session(), Session(hand="wuji")
        self.assertEqual(wuji.action_dim, 26)
        self.assertEqual(wuji.actuator_names[:6], sharpa.actuator_names[:6])
        self.assertTrue(all(name.startswith("r_wuji_") for name in wuji.actuator_names[6:]))
        self.assertTrue(np.array_equal(wuji.model.actuator_ctrlrange[:6], sharpa.model.actuator_ctrlrange[:6]))
        self.assertTrue(np.array_equal(wuji.model.actuator_gainprm[:6], sharpa.model.actuator_gainprm[:6]))
        self.assertTrue(np.array_equal(wuji.hold_action()[:6], sharpa.hold_action()[:6]))
        self.assertTrue(np.array_equal(wuji.data.flexvert_xpos, sharpa.data.flexvert_xpos))
        self.assertEqual(wuji.data.ncon, 0)  # the curled initial fingers touch neither table nor paper
        self.assertEqual(wuji.model.opt.timestep, sharpa.model.opt.timestep)
        self.assertEqual(wuji.substeps, 40)

    def test_wuji_nop_and_seeded_replay_are_deterministic(self):
        s = Session(hand="wuji")
        rng = np.random.default_rng(6)
        hold = s.hold_action()
        lo, hi = s.model.actuator_ctrlrange.T
        rows = np.repeat(hold[None], 150, 0)
        rows[:, 6:] = np.clip(hold[6:] + 0.15 * np.sin(np.linspace(0, 6, 150))[:, None] * rng.uniform(-1, 1, 20), lo[6:], hi[6:])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            s.save_trajectory(rows, folder / "wuji.npz")
            a, rc_a = run_replay(folder / "wuji.npz")
            b, rc_b = run_replay(folder / "wuji.npz")
            nop, rc_n = run_replay(save(folder / "nop.npz", np.repeat(hold[None], 300, 0), hand=np.array("wuji")))
        self.assertEqual((rc_a, rc_b, rc_n), (0, 0, 0))
        self.assertEqual(a["hand"], "wuji")
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertFalse(a["success"])
        self.assertFalse(nop["success"])
        self.assertIsNone(nop["verdict"]["failure"])
        self.assertEqual(nop["steps"], 300)


if __name__ == "__main__":
    unittest.main()
