"""Authoring tests (not shipped): trust boundary, negative controls and the physical predicate.

Run: ``python -m pytest -q scripts/dexhand/families/binder_page_load/tests`` (oracle tests replay ~2,000 controls each).
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from replay import replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"


def cli(path, *extra):
    """Run replay.py as the graders do (fresh process) and return its JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.json"
        done = subprocess.run([sys.executable, str(HERE / "replay.py"), "--traj", str(path), "--out", str(out), *extra],
                              cwd=HERE, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return json.loads(out.read_text())


def oracle_rows():
    actions, hand, _ = hands.read_trajectory(ORACLE, widths={"sharpa": 28, "wuji": 26}, max_rows=None)
    return actions, hand


class TaskTests(unittest.TestCase):
    def test_only_robot_is_actuated(self):
        for hand, width in (("sharpa", 28), ("wuji", 26)):
            s = Session(hand=hand)
            self.assertEqual(s.model.nu, width)
            self.assertEqual(s.model.nmocap, 0)
            names = [s.model.joint(j).name for j in s.model.actuator_trnid[:, 0]]
            self.assertEqual(names[:6], ["wrist_x", "wrist_y", "wrist_z", "wrist_rx", "wrist_ry", "wrist_rz"])
            self.assertTrue(all(n.startswith(("wrist_", "right_", "r_wuji_")) for n in names))
            # The only equality constraints are the binder's internal linkage (no welds, no object-hand attachments).
            eqs = {s.model.equality(i).name for i in range(s.model.neq)}
            self.assertEqual(eqs, {"paired_toggle_plates", "booster_link_-1", "booster_link_1"})
            self.assertTrue(all(s.model.eq_type[i] == mujoco.mjtEq.mjEQ_JOINT for i in range(s.model.neq)))
            for k in range(2):
                self.assertEqual(s.model.joint(f"page_{k}_free").type, mujoco.mjtJoint.mjJNT_FREE)

    def test_nop_fails_and_is_deterministic(self):
        for hand in ("sharpa", "wuji"):
            s = Session(hand=hand)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "nop.npz"
                s.save_trajectory(np.tile(s.hold_action(), (200, 1)), path)
                a, b = replay(path), replay(path)
            self.assertFalse(a["success"])
            self.assertEqual(a["stage"], 0)
            self.assertEqual(a["state_sha"], b["state_sha"])

    def test_wrong_width_and_hand_label_rejected(self):
        actions, _ = oracle_rows()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.npz"
            hands.write_trajectory(path, actions[:10, :26], hand="sharpa", task="binder_page_load")
            with self.assertRaises(ValueError):
                replay(path)
            hands.write_trajectory(path, actions[:10], hand="wuji", task="binder_page_load")
            with self.assertRaises(ValueError):
                replay(path)

    def test_forged_and_malformed_archives_are_bad_trajectories(self):
        actions, _ = oracle_rows()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            nan = actions[:20].copy()
            nan[5, 3] = np.nan
            np.savez(tmp / "nan.npz", actions=nan, hand=np.array("sharpa"))
            np.savez(tmp / "obj.npz", actions=np.array([[None] * 28], dtype=object))
            hands.write_trajectory(tmp / "task.npz", actions[:20], hand="sharpa", task="assemble_hamburger")
            with zipfile.ZipFile(tmp / "shadow.npz", "w") as z:  # raw member that could shadow actions.npy
                z.writestr("actions", b"junk")
                buf = tmp / "a.npy"
                np.save(buf, actions[:20])
                z.write(buf, "actions.npy")
            hands.write_trajectory(tmp / "range.npz", actions[:20] + 10.0, hand="sharpa", task="binder_page_load")
            for name in ("nan", "obj", "task", "shadow", "range"):
                r = cli(tmp / f"{name}.npz")
                self.assertEqual(r["bad_trajectory"], 1, name)
                self.assertFalse(r["success"], name)
            # forged success members are ignored; only the rows count
            np.savez(tmp / "forged.npz", actions=actions[:30], hand=np.array("sharpa"), success=np.array(True),
                     reward=np.array(1.0))
            r = cli(tmp / "forged.npz")
            self.assertFalse(r["success"])
            self.assertEqual(r["bad_trajectory"], 0)
            self.assertEqual(cli(tmp / "forged.npz", "--hand", "wuji")["bad_trajectory"], 1)

    def test_oracle_succeeds_with_slack_and_float32(self):
        actions, hand = oracle_rows()
        s = Session(hand=hand)
        st = s.replay(actions)
        self.assertTrue(st["success"])
        self.assertEqual(st["stage_steps"][-1], st["steps"])
        self.assertGreaterEqual(len(actions) - st["steps"], 50)
        st32 = s.replay(actions.astype(np.float32).astype(np.float64))
        self.assertTrue(st32["success"])

    def test_partial_and_drop_fail(self):
        actions, hand = oracle_rows()
        s = Session(hand=hand)
        st = s.replay(actions)
        stages = st["stage_steps"]
        self.assertFalse(s.replay(actions[: stages[1] - 5])["success"])
        self.assertFalse(s.replay(actions[: stages[2] - 5])["success"])
        self.assertFalse(s.replay(actions[: stages[3] - 1])["success"])
        drop = actions.copy()
        lo, hi = s.model.actuator_ctrlrange[6:19].T
        drop[1000:, 6:19] = np.clip(0.0, lo, hi)  # open thumb/index/middle while carrying page 1 in the air
        st = s.replay(drop)
        self.assertEqual(st["reason"], "page_dropped")
        self.assertEqual(st["failure_detail"]["control"], 1002)  # first free-fall substep after the release
        self.assertFalse(st["success"])
        knock = actions[:2980].copy()
        for k in range(120):  # sweep the hand sideways through the binder while it closes the rings
            knock[2860 + k] = actions[2860]
            knock[2860 + k, 1] = actions[2860, 1] + 0.25 * min(1.0, (k + 1) / 80)
        st = s.replay(knock)
        self.assertEqual(st["reason"], "binder_displaced")

    def test_pages_start_loose_on_the_desk(self):
        """Source start: both pages flat on the desk (no stands); resting on the desk is not a failure."""
        s = Session()
        self.assertFalse(any((s.model.geom(g).name or "").startswith("page_stand") for g in range(s.model.ngeom)))
        for k, (x, y) in enumerate(s.config["page_xy"]):
            b = s.data.body(f"page_{k}")
            np.testing.assert_allclose(b.xpos, [x, y, 0.7004], atol=1e-6)
            self.assertAlmostEqual(float(b.xmat[8]), 1.0, places=9)  # flat, printed face up
        st = s.replay(np.tile(s.hold_action(), (100, 1)))
        self.assertIsNone(st["failure"])
        for k in range(2):
            self.assertTrue(any(s.checker.page_geom[c.geom[0]] or s.checker.page_geom[c.geom[1]]
                                for c in s.data.contact[: s.data.ncon]))

    def test_page_holes_are_open(self):
        """A ray through a hole centre passes the page; a ray through the sheet hits it."""
        s = Session()
        m, d = s.model, s.data
        page = d.body("page_1")
        R = page.xmat.reshape(3, 3)
        geomid = np.zeros(1, np.int32)
        for offset, expect_hit in ((np.zeros(3), False), (R[:, 0] * 0.03, True), (R[:, 1] * 0.035, True)):
            for station in (-0.06985, 0.0, 0.06985):
                start = page.xpos + R[:, 1] * station + offset + R[:, 2] * 0.01
                dist = mujoco.mj_ray(m, d, start, -R[:, 2], None, 1, -1, geomid)
                hit = 0 <= dist < 0.02 and s.checker.page_index[int(geomid[0])] == 1
                self.assertEqual(bool(hit), expect_hit, (offset, station))


if __name__ == "__main__":
    unittest.main()
