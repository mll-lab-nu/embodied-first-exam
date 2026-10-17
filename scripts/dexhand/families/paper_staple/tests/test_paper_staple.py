"""Authoring tests for paper_staple: oracle, negatives, fail-fast, trust boundary, both hands.

Run from the family folder (one process; about two minutes on one core):

    cd scripts/dexhand/families/paper_staple
    DEXHAND_ASSET_DIR=<images/dexhand/assets/hand> MUJOCO_GL=egl python -m pytest -q tests/test_paper_staple.py
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
sys.path.append(str(HERE.parents[1] / "shared"))

import arm_ik  # noqa: E402  (authoring-only IK helper, used to build negative paths)
import arm_rig  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"


def rows(path=ORACLE):
    return hands.read_trajectory(path, widths={"sharpa": 58, "wuji": 54}, max_rows=6000, task="paper_staple")[0]


def ik_path(session, points, R, n=80):
    """Right-arm joint rows moving the hand mount through ``points`` with rotation ``R`` (left arm parked)."""
    ik = arm_ik.ArmIK(session.model, "right")
    arm = arm_rig.layout(session.model)["arm"]["right"]
    q0 = session.hold_action()
    qa = q0[arm].copy()
    out = []
    for a, b in zip(points[:-1], points[1:]):
        for r in np.linspace(0, 1, n)[1:]:
            qa, _, _ = ik.solve(np.asarray(a) + (np.asarray(b) - np.asarray(a)) * r, R, q0=qa, iters=60)
            q = q0.copy()
            q[arm] = qa
            out.append(q)
    return np.asarray(out)


def cli(path, *extra):
    """Run replay.py in a fresh process and return its JSON result."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "r.json"
        done = subprocess.run([sys.executable, "replay.py", "--task", "paper_staple", "--traj", str(path), "--out",
                               str(out), *extra], cwd=HERE, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-2000:]
        return json.loads(out.read_text())


class Model(unittest.TestCase):
    def test_only_the_robot_is_actuated(self):
        s = Session()
        self.assertEqual(s.action_dim, 58)
        self.assertEqual(s.robot, "marvin-bimanual-sharpa-wave")
        self.assertEqual(s.model.nmocap, 0)
        self.assertEqual(s.model.neq, 0)
        self.assertEqual(s.actuator_names[:14], list(arm_rig.ARM_ACTUATORS))
        joints = [s.model.joint(int(j)).name for j in s.model.actuator_trnid[:, 0]]
        self.assertTrue(all(n in arm_rig.ARM_JOINTS["left"] + arm_rig.ARM_JOINTS["right"]
                            or n.startswith(("left_", "right_")) for n in joints))
        for i in range(3):
            self.assertEqual(s.model.joint(f"sheet_{i}_free").type, mujoco.mjtJoint.mjJNT_FREE)
        self.assertEqual(s.model.joint("stapler_free").type, mujoco.mjtJoint.mjJNT_FREE)
        self.assertNotIn("paper_stop", [s.model.actuator(i).name for i in range(s.model.nu)])
        hinge = s.model.joint("head_hinge")
        self.assertAlmostEqual(float(s.model.jnt_stiffness[hinge.id]), 7.0)  # passive spring return, no actuator
        self.assertAlmostEqual(float(s.model.jnt_range[hinge.id][1]), 0.1701, places=3)
        # spring torque: about 0.8 N m at the open stop, 2.0 N m at the bottom stop (10 N / 25 N at 8 cm)
        k, ref = float(s.model.jnt_stiffness[hinge.id]), float(s.model.qpos_spring[s.model.jnt_qposadr[hinge.id]])
        self.assertAlmostEqual(-k * ref, 0.805, places=2)
        self.assertAlmostEqual(k * (0.1701 - ref), 1.996, places=2)

    def test_reset_is_at_rest_and_deterministic(self):
        a, b = Session(), Session()
        self.assertEqual(a.initial_sha, b.initial_sha)
        hold = a.hold_action()
        for _ in range(100):
            a.step(hold)
        f = a.features()
        self.assertIsNone(f["failure"])
        self.assertLess(f["max_sheet_speed_m_s"], 1e-3)
        self.assertEqual(f["stage"], 0)  # the staircase is misaligned: 4 mm and 8 mm corner offsets
        self.assertGreater(min(f["corner_offsets_m"]), 0.003)

    def test_state_sha_ignores_prose(self):
        s = Session()
        config = json.loads((HERE / "task.json").read_text())
        config["instruction"] = "changed prose"
        config["description"] = "changed"
        self.assertEqual(Session(config=config).initial_sha, s.initial_sha)
        config["align_tolerance_m"] = 0.003
        self.assertNotEqual(Session(config=config).initial_sha, s.initial_sha)


class Oracle(unittest.TestCase):
    def test_oracle_succeeds_twice_with_identical_hash_and_slack(self):
        first, second = cli(ORACLE), cli(ORACLE)
        self.assertTrue(first["success"], first.get("reason"))
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["stage"], 4)
        self.assertLessEqual(first["steps"] + 50, first["n_actions"])  # success well before the last row

    def test_float32_rows_succeed(self):
        s = Session()
        self.assertTrue(s.replay(rows().astype(np.float32).astype(np.float64))["success"])

    def test_no_arm_link_touches_the_task_during_the_oracle(self):
        s = Session()
        arm = s.checker.is_arm
        touched = 0
        for row in rows():
            s.step(row)
            g = s.data.contact.geom[: s.data.ncon]
            touched += int(np.any(arm[g[:, 0]] | arm[g[:, 1]]))
            if s.done:
                break
        self.assertTrue(s.success)
        self.assertEqual(touched, 0)


class Negatives(unittest.TestCase):
    def test_nop_fails(self):
        s = Session()
        st = s.replay(np.tile(s.hold_action(), (400, 1)))
        self.assertFalse(st["success"])
        self.assertEqual(st["stage"], 0)

    def test_truncations_fail(self):
        oracle = rows()
        s = Session()
        for cut, stage in ((260, 0), (640, 2), (700, 3)):
            st = s.replay(oracle[:cut])
            self.assertFalse(st["success"])
            self.assertEqual(st["stage"], stage)
        full = s.replay(oracle)
        one_short = s.replay(oracle[: full["steps"] - 1])
        self.assertFalse(one_short["success"])
        self.assertEqual(one_short["stage"], 3)

    def test_success_ends_the_episode(self):
        s = Session()
        st = s.replay(rows())
        self.assertTrue(st["done"])
        before = s.state_sha()
        s.step(s.hold_action())
        self.assertEqual(before, s.state_sha())

    def test_stapler_knock_fails_fast(self):
        """Sweep the hand through the stapler at desk height: the first broken control ends the episode."""
        s = Session()
        R = np.c_[[-1, 0, 0], [0, 1, 0], [0, 0, -1]]  # fingers down: the hand sweeps +y through the stapler
        p0 = s.data.xpos[s.model.body("wrist_stage").id].copy()
        path = ik_path(s, [p0, [0.58, -0.22, 1.0], [0.58, -0.22, 0.90], [0.58, 0.05, 0.90]], R)
        st = s.replay(path)
        self.assertTrue(st["failed"])
        self.assertIn(st["reason"], ("stapler_tipped", "stapler_displaced"))
        self.assertLess(st["steps"], len(path))  # later rows were not executed
        detail = st["failure_detail"]
        again = Session()
        again.replay(path[: detail["control"]])
        self.assertFalse(again.failure)  # one row earlier the episode was still alive

    def test_arm_link_on_the_desk_fails_fast(self):
        s = Session()
        R = np.c_[[1, 0, 0], [0, -1, 0], [0, 0, 1]]  # palm +x, fingers up: the wrist links reach the desk first
        p0 = s.data.xpos[s.model.body("wrist_stage").id].copy()
        st = s.replay(ik_path(s, [p0, [0.45, -0.25, 0.98], [0.45, -0.25, 0.70]], R))
        self.assertEqual(st["reason"], "arm_collision")
        self.assertIn("desk_top", st["failure_detail"]["what"])

    def test_mid_air_drop_fails_without_catch_window(self):
        s = Session()
        b = s.checker.sheet_ids[2]
        adr = s.model.jnt_qposadr[s.model.joint("sheet_2_free").id]
        s.data.qpos[adr + 2] += 0.05  # test fixture: lift the top sheet 5 cm (not reachable by an agent)
        mujoco.mj_forward(s.model, s.data)
        hold = s.hold_action()
        for _ in range(10):
            s.step(hold)
            if s.done:
                break
        self.assertEqual(s.failure, "object_dropped")
        self.assertIn("sheet_2", s.failure_detail["what"])
        self.assertGreater(s.data.xpos[b][2], s.config["table_z"] + 0.001)  # failed while still in the air


class TrustBoundary(unittest.TestCase):
    def write(self, tmp, name, **members):
        path = Path(tmp) / name
        np.savez(path, **members)
        return path

    def test_forged_members_are_ignored_and_ambiguous_rejected(self):
        oracle = rows()
        with tempfile.TemporaryDirectory() as tmp:
            nop = np.tile(Session().hold_action(), (100, 1))
            forged = self.write(tmp, "forged.npz", actions=nop, hand=np.array("sharpa"), success=np.array(True),
                                stage=np.array(4), config=np.array('{"align_tolerance_m": 1}'))
            r = cli(forged)
            self.assertFalse(r["success"])
            self.assertEqual(r["bad_trajectory"], 0)
            shadow = Path(tmp) / "shadow.npz"
            np.savez(shadow, actions=nop)
            with zipfile.ZipFile(shadow, "a") as z:
                buf = Path(tmp) / "a.npy"
                np.save(buf, oracle)
                z.write(buf, "actions")  # raw member that could shadow actions.npy
            self.assertEqual(cli(shadow)["bad_trajectory"], 1)

    def test_width_nan_hand_and_task_are_rejected(self):
        oracle = rows()
        with tempfile.TemporaryDirectory() as tmp:
            cases = {
                "narrow.npz": dict(actions=oracle[:, :54], hand=np.array("sharpa")),
                "wuji_label.npz": dict(actions=oracle, hand=np.array("wuji")),
                "nan.npz": dict(actions=np.where(np.arange(oracle.size).reshape(oracle.shape) == 7, np.nan, oracle)),
                "hand.npz": dict(actions=oracle, hand=np.array("robotiq")),
                "task.npz": dict(actions=oracle, task=np.array("assemble_hamburger")),
                "empty.npz": dict(actions=np.zeros((0, 58))),
                "range.npz": dict(actions=oracle + np.r_[np.zeros(14), np.full(44, 10.0)]),
            }
            for name, members in cases.items():
                r = cli(self.write(tmp, name, **members))
                self.assertEqual(r["bad_trajectory"], 1, name)
                self.assertFalse(r["success"], name)
            r = cli(self.write(tmp, "mismatch.npz", actions=oracle, hand=np.array("sharpa")), "--hand", "wuji")
            self.assertEqual(r["bad_trajectory"], 1)


class Wuji(unittest.TestCase):
    def test_wuji_composes_on_the_same_arms_and_nop_fails(self):
        s, t = Session(hand="wuji"), Session(hand="wuji")
        self.assertEqual(s.action_dim, 54)
        self.assertEqual(s.actuator_names[:14], Session().actuator_names[:14])
        self.assertEqual(s.initial_sha, t.initial_sha)
        st = s.replay(np.tile(s.hold_action(), (200, 1)))
        self.assertFalse(st["success"])
        self.assertIsNone(st["failure"])
        t.replay(np.tile(t.hold_action(), (200, 1)))
        self.assertEqual(s.state_sha(), t.state_sha())


if __name__ == "__main__":
    unittest.main()
