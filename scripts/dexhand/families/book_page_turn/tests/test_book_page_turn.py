"""Authoring tests for book_page_turn: positive oracles, negative controls, trust boundary and hand selection.

Run from the repository root (about 1 minute on one core):

    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand OPENBLAS_NUM_THREADS=1 \
        python -m pytest -q scripts/dexhand/families/book_page_turn/tests
"""

from __future__ import annotations

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
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
if str(FAMILY) not in sys.path:
    sys.path.insert(0, str(FAMILY))

import mujoco  # noqa: E402

from replay import load_trajectory, replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = FAMILY / "solution/trajectory.npz"
WUJI_ORACLE = FAMILY / "solution/wuji/trajectory.npz"


def oracle_rows():
    return np.load(ORACLE)["actions"]


def shove_rows():
    """The oracle's approach, then the fingertip driven 16 cm toward the spine through the stack edge."""
    rows = list(oracle_rows()[:140])
    last = rows[-1].copy()
    for i in range(1, 76):
        row = last.copy()
        row[0] -= 0.16 * min(1, i / 50)
        row[2] -= 0.004 * min(1, i / 50)
        rows.append(row)
    return np.asarray(rows)


def run_replay_cli(path, *extra):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        proc = subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", "book_page_turn", "--traj",
                               str(path), "--out", str(out), *extra], cwd=FAMILY, capture_output=True, text=True,
                              timeout=600)
        assert proc.returncode == 0, proc.stderr[-2000:]
        return json.loads(out.read_text())


class PageTurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Session()

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    # ------------------------------------------------------------------ model / trust boundary
    def test_only_robot_is_actuated(self):
        m = self.s.model
        names = [m.joint(int(j)).name for j in m.actuator_trnid[:, 0]]
        self.assertEqual(m.nu, 28)
        self.assertEqual((m.nmocap, m.neq), (0, 0))
        self.assertTrue(all(n.startswith(("wrist_", "right_")) for n in names))
        self.assertEqual(m.joint("book_free").type, mujoco.mjtJoint.mjJNT_FREE)
        book = self.s.checker.book_body
        self.assertFalse(any(book[m.jnt_bodyid[int(j)]] for j in m.actuator_trnid[:, 0]))
        # Every book joint is passive: hinges/slides with limits; the springback stop of leaf 2 is 0.07 rad.
        self.assertAlmostEqual(float(m.joint("leaf_2_binding").range[0]), 0.07)
        self.assertEqual(float(np.abs(self.s.data.xfrc_applied).sum() + np.abs(self.s.data.qfrc_applied).sum()), 0.0)

    def test_reset_is_exact(self):
        self.s.reset()
        first = self.s.state_sha()
        for row in oracle_rows()[:200]:
            self.s.step(row)
        self.s.reset()
        self.assertEqual(first, self.s.state_sha())
        self.assertEqual(first, Session().state_sha())

    # ------------------------------------------------------------------ positive
    def test_oracle_succeeds_with_slack_and_is_deterministic(self):
        rows = oracle_rows()
        first = self.s.replay(rows)
        sha = self.s.state_sha()
        second = Session().replay(rows)
        self.assertTrue(first["success"] and second["success"])
        self.assertEqual(first["stage"], 4)
        self.assertLessEqual(first["steps"], len(rows) - 50)
        self.assertEqual(sha, self.s.state_sha())

    def test_float32_rounded_rows_succeed(self):
        rows = oracle_rows().astype(np.float32).astype(np.float64)
        self.assertTrue(self.s.replay(rows)["success"])

    def test_replay_cli_twice_identical(self):
        a, b = run_replay_cli(ORACLE), run_replay_cli(ORACLE)
        self.assertTrue(a["success"] and b["success"])
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertEqual((a["bad_trajectory"], a["hand"]), (0, "sharpa"))

    # ------------------------------------------------------------------ negative controls
    def test_nop_and_truncations_fail(self):
        rows = oracle_rows()
        nop = np.tile(self.s.initial_targets, (len(rows), 1))
        self.assertFalse(self.s.replay(nop)["success"])
        steps = self.s.replay(rows)["steps"]
        for cut in (150, 215, steps - 10, steps - 1):
            status = self.s.replay(rows[:cut])
            self.assertFalse(status["success"], cut)
            self.assertFalse(status["failed"], cut)

    def test_release_mid_turn_fails(self):
        rows = list(oracle_rows()[:215])
        last = rows[-1].copy()
        for i in range(1, 151):
            row = last.copy()
            row[0] += 0.10 * min(1, i / 30)
            row[2] += 0.10 * min(1, i / 30)
            rows.append(row)
        status = self.s.replay(np.asarray(rows))
        self.assertFalse(status["success"])
        self.assertLess(status["target_angle_deg"], 10.0)  # the board fell back onto the right-hand stack

    def test_shove_fails_fast_and_later_rows_do_not_execute(self):
        rows = shove_rows()
        status = self.s.replay(rows)
        self.assertEqual(status["reason"], "book_displaced")
        self.assertLess(status["steps"], len(rows))
        self.assertLess(status["failure_detail"]["substep"], self.s.substeps)
        resumed = np.vstack([rows[: status["steps"]], oracle_rows()[140:]])
        resumed_status = self.s.replay(resumed)
        self.assertFalse(resumed_status["success"])
        self.assertEqual(resumed_status["reason"], "book_displaced")

    def test_rows_after_success_are_not_executed(self):
        rows = oracle_rows()
        steps = self.s.replay(rows)["steps"]
        knock = np.vstack([rows[:steps], np.tile(rows[steps - 1] - np.r_[0.4, 0, 0.2, np.zeros(25)], (100, 1))])
        knock = np.clip(knock, self.s.lo, self.s.hi)
        status = self.s.replay(knock)
        self.assertTrue(status["success"])
        self.assertEqual(status["steps"], steps)

    def test_invariants_from_state(self):
        s = self.s
        cases = [("leaf_3_binding", 0.6, "second_leaf_turned"), ("leaf_1_binding", -0.6, "second_leaf_turned"),
                 ("right_cover_binding", 0.6, "book_closing"), ("left_cover_binding", -0.6, "book_closing"),
                 ("leaf_4_binding", 0.08, None)]
        for joint, delta, expected in cases:
            s.reset()
            s.data.qpos[s.model.jnt_qposadr[s.model.joint(joint).id]] += delta
            mujoco.mj_forward(s.model, s.data)
            got = s.checker.invariant(s.data)
            self.assertEqual(got[0] if got else None, expected, joint)
        free = s.model.jnt_qposadr[s.model.joint("book_free").id]
        for index, delta, expected in ((0, 0.035, "book_displaced"), (2, -0.01, "book_below_table")):
            s.reset()
            s.data.qpos[free + index] += delta
            mujoco.mj_forward(s.model, s.data)
            self.assertEqual(s.checker.invariant(s.data)[0], expected)
        s.reset()
        quat = s.data.qpos[free + 3:free + 7].copy()
        turn = np.zeros(4)
        mujoco.mju_axisAngle2Quat(turn, np.array([0.0, 0.0, 1.0]), np.radians(12))
        mujoco.mju_mulQuat(s.data.qpos[free + 3:free + 7], turn, quat)
        mujoco.mj_forward(s.model, s.data)
        self.assertEqual(s.checker.invariant(s.data)[0], "book_rotated")
        s.reset()

    # ------------------------------------------------------------------ archive rules
    def test_forged_members_are_ignored_or_rejected(self):
        rows = oracle_rows()
        with tempfile.TemporaryDirectory() as tmp:
            forged = Path(tmp) / "forged.npz"
            np.savez(forged, actions=rows[:100], hand=np.array("sharpa"), success=np.array(True), stage=np.array(4),
                     config=np.array(json.dumps({"hold_steps": 0, "stage_angles_deg": {"laid": 0}})))
            result = replay(forged)
            self.assertFalse(result["success"])
            self.assertEqual(result["bad_trajectory"], 0)
            shadow = Path(tmp) / "shadow.npz"
            with zipfile.ZipFile(shadow, "w") as archive:
                archive.writestr("actions", b"not an array")
                with archive.open("actions.npy", "w") as handle:
                    np.lib.format.write_array(handle, rows)
            self.assertEqual(run_replay_cli(shadow)["bad_trajectory"], 1)
            other_task = Path(tmp) / "task.npz"
            np.savez(other_task, actions=rows, hand=np.array("sharpa"), task=np.array("assemble_hamburger"))
            self.assertEqual(run_replay_cli(other_task)["bad_trajectory"], 1)
            pickled = Path(tmp) / "pickled.npz"
            np.savez(pickled, actions=np.array([{"row": 1}], dtype=object))
            self.assertEqual(run_replay_cli(pickled)["bad_trajectory"], 1)
            names = Path(tmp) / "names.npz"
            np.savez(names, actions=rows, hand=np.array("sharpa"), actuator_names=np.array(["x"] * 28))
            self.assertEqual(run_replay_cli(names)["bad_trajectory"], 1)

    def test_wrong_width_hand_label_nan_and_range_are_rejected(self):
        rows = oracle_rows()
        with tempfile.TemporaryDirectory() as tmp:
            cases = {
                "wuji_label": dict(actions=rows, hand=np.array("wuji")),
                "unknown_hand": dict(actions=rows, hand=np.array("shadow_hand")),
                "short_width": dict(actions=rows[:, :26]),
                "nan": dict(actions=np.where(np.arange(28) == 3, np.nan, rows)),
                "inf": dict(actions=np.where(np.arange(28) == 0, np.inf, rows)),
                "out_of_range": dict(actions=rows + np.r_[0, 0, 0, 0, 0, 0, 5.0, np.zeros(21)]),
                "too_many_rows": dict(actions=np.tile(rows[:1], (3001, 1))),
                "empty": dict(actions=np.zeros((0, 28))),
            }
            for name, members in cases.items():
                path = Path(tmp) / f"{name}.npz"
                np.savez(path, **members)
                result = run_replay_cli(path)
                self.assertEqual(result["bad_trajectory"], 1, name)
                self.assertFalse(result["success"], name)
            with self.assertRaises(Exception):
                load_trajectory(Path(tmp) / "wuji_label.npz")
            good = Path(tmp) / "good.npz"
            hands.write_trajectory(good, rows, hand="sharpa", task="book_page_turn")
            self.assertEqual(load_trajectory(good)[1], "sharpa")
            self.assertEqual(run_replay_cli(good, "--hand", "wuji")["bad_trajectory"], 1)

    # ------------------------------------------------------------------ Wuji
    def test_wuji_same_rig_and_nop_fails(self):
        w = Session(hand="wuji")
        try:
            self.assertEqual(w.action_dim, 26)
            self.assertEqual(w.actuator_names[:6], self.s.actuator_names[:6])
            for name in w.actuator_names[:6]:
                a, b = w.model.actuator(name), self.s.model.actuator(name)
                self.assertTrue(np.array_equal(a.ctrlrange, b.ctrlrange))
                self.assertTrue(np.array_equal(a.gainprm, b.gainprm))
            first = w.state_sha()
            w.reset()
            self.assertEqual(first, w.state_sha())
            status = w.replay(np.tile(w.initial_targets, (300, 1)))
            self.assertFalse(status["success"] or status["failed"])
            self.assertEqual(status["hand_book_contacts"], 0)
        finally:
            w.close()

    def test_wuji_oracle_succeeds_deterministically(self):
        rows, hand, _ = load_trajectory(WUJI_ORACLE)
        self.assertEqual(hand, "wuji")
        a, b = run_replay_cli(WUJI_ORACLE), run_replay_cli(WUJI_ORACLE)
        self.assertTrue(a["success"] and b["success"])
        self.assertLessEqual(a["steps"], len(rows) - 50)
        self.assertEqual(a["state_sha"], b["state_sha"])
        self.assertEqual(a["hand"], "wuji")


if __name__ == "__main__":
    unittest.main()
