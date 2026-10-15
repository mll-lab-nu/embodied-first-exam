"""Authoring tests: positive oracle, negative controls, trust boundary and hand selection for coffee_stir.

Run from the repository root (about 2 minutes on one core):

    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand OPENBLAS_NUM_THREADS=1 \
        python -m pytest -q scripts/dexhand/families/coffee_stir/tests
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
SHARED = REPO / "scripts/dexhand/shared"
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
for path in (str(SHARED), str(FAMILY), str(FAMILY / "tools")):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
for name in ("runtime", "replay", "hands", "scene", "checker", "demo", "knock"):
    sys.modules.pop(name, None)

import hands  # noqa: E402  (shared copy, as in a generated task)
from runtime import Session  # noqa: E402

TASK = "coffee_stir"
ORACLE = FAMILY / "solution/trajectory.npz"
SUCCESS_AT = 1165
MAX_ROWS = 3000


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
            [sys.executable, str(FAMILY / "replay.py"), "--task", TASK, "--traj", str(traj), "--out", str(out), *extra],
            env=env, capture_output=True, text=True, timeout=900,
        )
        result = json.loads(out.read_text()) if out.is_file() else {}
        return result, done.returncode


def save(path: Path, actions, **members) -> Path:
    np.savez_compressed(path, actions=np.asarray(actions), **members)
    return path


class OracleTests(unittest.TestCase):
    """One in-process oracle episode feeds several checks."""

    @classmethod
    def setUpClass(cls):
        cls.rows = oracle_rows()
        s = Session()
        cls.snapshot = None
        cls.first_success = None
        cls.stage2_at = None
        for i, row in enumerate(cls.rows):
            if i == 400:
                cls.snapshot = s.snapshot()
            s.step(row)
            if cls.stage2_at is None and s.status()["stage"] >= 2:
                cls.stage2_at = i + 1
            if s.success and cls.first_success is None:
                cls.first_success = i + 1
        cls.final = s.status()
        cls.final_sha = s.state_sha()
        s.step(cls.rows[-1])  # a row after success is not executed
        cls.after = s.status()
        cls.after_sha = s.state_sha()
        cls.session = s

    @classmethod
    def tearDownClass(cls):
        cls.session.close()

    def test_oracle_succeeds_with_slack(self):
        self.assertTrue(self.final["success"])
        self.assertEqual(self.final["reason"], "success")
        self.assertEqual(self.final["stage"], 3)
        self.assertEqual(self.first_success, SUCCESS_AT)
        self.assertGreaterEqual(len(self.rows) - self.first_success, 50)
        self.assertGreaterEqual(self.final["revolutions"], 3.0)
        self.assertLess(self.stage2_at, self.first_success)

    def test_success_is_terminal(self):
        self.assertEqual(self.after["steps"], self.final["steps"])
        self.assertEqual(self.after_sha, self.final_sha)

    def test_snapshot_restore_is_exact(self):
        s = Session()
        for row in self.rows[:400]:
            s.step(row)
        snap = s.snapshot()
        for row in self.rows[400:520]:
            s.step(row)
        first = s.state_sha()
        s.restore(snap)
        for row in self.rows[400:520]:
            s.step(row)
        self.assertEqual(s.state_sha(), first)
        s.close()

    def test_truncated_episodes_fail(self):
        s = Session()
        for rows, stage in ((self.rows[:600], 1), (self.rows[:900], 2), (self.rows[: SUCCESS_AT - 1], 2)):
            st = s.replay(rows)
            self.assertFalse(st["success"])
            self.assertFalse(st["failed"])
            self.assertEqual(st["stage"], stage)
        s.close()

    def test_float32_rounded_oracle_still_succeeds(self):
        s = Session()
        st = s.replay(self.rows.astype(np.float32).astype(np.float64))
        self.assertTrue(st["success"])
        s.close()

    def test_two_fresh_oracle_replays_agree(self):
        a, rc_a = run_replay(ORACLE)
        b, rc_b = run_replay(ORACLE)
        self.assertEqual((rc_a, rc_b), (0, 0))
        self.assertTrue(a["success"] and b["success"])
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertEqual(a["steps"], SUCCESS_AT)
        self.assertEqual(a["stage"], 3)


class NegativeTests(unittest.TestCase):
    def test_nop_fails_at_the_episode_budget(self):
        s = Session()
        cup0 = s.data.xpos[s.model.body("cup").id].copy()
        spoon0 = s.data.xpos[s.model.body("spoon").id].copy()
        st = s.replay(np.repeat(s.hold_action()[None], MAX_ROWS, 0))
        self.assertFalse(st["success"])
        self.assertEqual(st["reason"], "episode_budget")
        self.assertEqual(st["stage"], 0)
        self.assertLess(np.linalg.norm(s.data.xpos[s.model.body("cup").id] - cup0), 1e-3)
        self.assertLess(np.linalg.norm(s.data.xpos[s.model.body("spoon").id] - spoon0), 1e-3)
        s.close()

    def test_knock_fails_fast_and_permanently(self):
        import knock

        s, rows = knock.knock_rows()
        st = s.status()
        self.assertEqual(st["reason"], "cup_moved")
        failed_at = st["steps"]
        self.assertLess(failed_at, len(rows) + 1)
        # Later rows (here: the whole oracle) cannot undo the failure.
        for row in oracle_rows()[:50]:
            s.step(row)
        self.assertEqual(s.status()["steps"], failed_at)
        self.assertEqual(s.status()["reason"], "cup_moved")
        s.close()

    def test_drop_and_midair_release_fail_fast(self):
        import demo

        args = dict(out=None, grasp_offset=[0] * 6, approach=0.04, squeeze=1.0, tilt=0.15, bowl_z=0.037, radius=0.018,
                    turns=5.0, rows_per_turn=110, closed_loop=1, extra_hold=60, mode="pendulum", upright_rows=80,
                    settle_rows=50, start_angle=0.0, rest_bowl_z=0.026, lean=[0.0, -0.045, -0.02],
                    retreat=[-0.06, -0.02, 0.10], kp=0.0, kd=0.0, kz=0.2)
        for variant in ("drop", "midair"):
            s, c = demo.run_pendulum(argparse.Namespace(**args, variant=variant))
            st = s.status()
            self.assertEqual(st["reason"], "spoon_dropped", variant)
            self.assertEqual(st["stage"], 2, variant)  # stirring was complete; the drop still fails the episode
            self.assertIn("unsupported_fall_speed_m_s", st["failure_detail"], variant)
            s.close()

    def test_spoon_dropped_on_worktop_fails(self):
        """A spoon released above the worktop fails while falling, at the first unsupported falling substep."""
        s = Session()
        s.reset()
        sid = s.model.body("spoon").id
        # Probe the checker directly: put the free spoon in the air (test-only state edit) and step once.
        qadr = s.model.jnt_qposadr[s.model.joint("spoon_free").id]
        s.data.qpos[qadr:qadr + 3] = [0.30, -0.25, 0.90]
        import mujoco

        mujoco.mj_forward(s.model, s.data)
        for _ in range(20):
            s.step(s.hold_action())
            if s.done:
                break
        self.assertEqual(s.status()["reason"], "spoon_dropped")
        self.assertGreater(s.data.xpos[sid, 2], 0.80)  # failed long before reaching the worktop
        s.close()


class TrustBoundaryTests(unittest.TestCase):
    def test_forged_metadata_is_ignored_or_rejected(self):
        s = Session()
        hold = np.repeat(s.hold_action()[None], 20, 0)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            forged, rc = run_replay(save(folder / "forged.npz", hold, hand=np.array("sharpa"), success=np.array(True),
                                         stage=np.array(3), revolutions=np.array(9.0),
                                         config=np.array(json.dumps({"stir_revolutions": 0}))))
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
                "infinite": save(folder / "g2.npz", np.where(np.arange(28) == 8, np.inf, hold)),
                "out of range": save(folder / "h.npz", hold + np.r_[np.zeros(6), 10.0 * np.ones(22)]),
                "too many rows": save(folder / "i.npz", np.repeat(hold[:1], MAX_ROWS + 1, 0)),
                "object array": folder / "j.npz",
                "hand array": save(folder / "k.npz", hold, hand=np.array(["sharpa", "wuji"])),
                "empty": save(folder / "o.npz", np.zeros((0, 28))),
            }
            with open(cases["object array"], "wb") as stream:
                np.savez(stream, actions=np.array([[None] * 28], dtype=object))
            cases["not a zip"] = folder / "l.npz"
            cases["not a zip"].write_bytes(b"PK\x03\x04" + os.urandom(2000))
            truncated = save(folder / "m.npz", hold, hand=np.array("sharpa"))
            truncated.write_bytes(truncated.read_bytes()[:-200])
            cases["truncated archive"] = truncated
            cases["ambiguous member"] = folder / "n.npz"
            with zipfile.ZipFile(cases["ambiguous member"], "w") as archive:
                buffer = io.BytesIO()
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
        s.close()

    def test_trusted_service_hand_must_match(self):
        result, rc = run_replay(ORACLE, "--trusted-service", "--hand", "wuji")
        self.assertEqual(rc, 0)
        self.assertEqual(result["bad_trajectory"], 1)

    def test_step_validates_rows(self):
        s = Session()
        with self.assertRaises(ValueError):
            s.step(np.zeros(26))
        bad = s.hold_action()
        bad[0] = 5.0
        with self.assertRaises(ValueError):
            s.step(bad)
        bad = s.hold_action()
        bad[7] = np.nan
        with self.assertRaises(ValueError):
            s.step(bad)
        s.close()


class HandTests(unittest.TestCase):
    def test_hand_selection(self):
        os.environ["DEXHAND_HAND"] = "wuji"
        try:
            self.assertEqual(Session().hand, "wuji")
        finally:
            del os.environ["DEXHAND_HAND"]
        self.assertEqual(Session().hand, "sharpa")
        with self.assertRaises(ValueError):
            Session(hand="shadow")

    def test_wuji_scene_same_wrist_and_objects(self):
        sharpa, wuji = Session(), Session(hand="wuji")
        self.assertEqual(wuji.action_dim, 26)
        self.assertEqual(wuji.actuator_names[:6], sharpa.actuator_names[:6])
        self.assertTrue(all(name.startswith("r_wuji_") for name in wuji.actuator_names[6:]))
        self.assertTrue(np.array_equal(wuji.model.actuator_ctrlrange[:6], sharpa.model.actuator_ctrlrange[:6]))
        self.assertTrue(np.array_equal(wuji.model.actuator_gainprm[:6], sharpa.model.actuator_gainprm[:6]))
        self.assertTrue(np.array_equal(wuji.hold_action()[:6], sharpa.hold_action()[:6]))
        for body in ("cup", "spoon"):
            self.assertTrue(np.array_equal(wuji.data.xpos[wuji.model.body(body).id],
                                           sharpa.data.xpos[sharpa.model.body(body).id]))
        self.assertEqual(len(wuji.checker.fingertip_sites), 5)
        self.assertEqual(wuji.substeps, sharpa.substeps)

    def test_wuji_nop_and_seeded_replay_are_deterministic(self):
        s = Session(hand="wuji")
        rng = np.random.default_rng(6)
        hold = s.hold_action()
        lo, hi = s.model.actuator_ctrlrange.T
        rows = np.repeat(hold[None], 150, 0)
        rows[:, 6:] = np.clip(hold[6:] + 0.3 * np.sin(np.linspace(0, 6, 150))[:, None] * rng.uniform(-1, 1, 20),
                              lo[6:], hi[6:])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            s.save_trajectory(rows, folder / "wuji.npz")
            a, rc_a = run_replay(folder / "wuji.npz")
            b, rc_b = run_replay(folder / "wuji.npz")
            nop, rc_n = run_replay(save(folder / "nop.npz", np.repeat(hold[None], MAX_ROWS, 0), hand=np.array("wuji")))
        self.assertEqual((rc_a, rc_b, rc_n), (0, 0, 0))
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertEqual(a["hand"], "wuji")
        self.assertFalse(nop["success"])
        self.assertEqual(nop["reason"], "episode_budget")
        s.close()


if __name__ == "__main__":
    unittest.main()
