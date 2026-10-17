"""Authoring tests: trust boundary, negative controls, fail-fast and the physical predicate (about 2 minutes).

Run from the family folder:  python -m unittest tests/test_ram_module_install.py
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from replay import load_actions, load_trajectory, replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

SOLUTION = FAMILY / "solution/trajectory.npz"
SUCCESS_STEP = 1379
DROP_ROW = 395  # a row of the carry phase (module pinched in mid-air)


def oracle_rows():
    return hands.read_trajectory(SOLUTION, widths={"sharpa": 28, "wuji": 26}, max_rows=3000)[0]


def write(path, actions, hand="sharpa"):
    hands.write_trajectory(path, actions, hand=hand, task="ram_module_install")
    return path


def place_module(s, pos, quat):
    adr = s.model.jnt_qposadr[s.model.joint("dimm_free").id]
    s.data.qpos[adr : adr + 3] = pos
    s.data.qpos[adr + 3 : adr + 7] = quat
    dof = s.model.jnt_dofadr[s.model.joint("dimm_free").id]
    s.data.qvel[dof : dof + 6] = 0
    mujoco.mj_forward(s.model, s.data)


def seated_pose(s, height=0.002, yaw_flip=False):
    sock = s.model.body("socket_3").id
    pos = s.data.xpos[sock] + s.data.xmat[sock].reshape(3, 3) @ np.array([0, 0, height])
    quat = s.model.body_quat[sock].copy()
    if yaw_flip:  # rotate 180 deg about the vertical: the key notch on the wrong side
        flipped = np.empty(4)
        mujoco.mju_mulQuat(flipped, quat, np.array([0.0, 0.0, 0.0, 1.0]))
        quat = flipped
    return pos, quat


class RobotAndModelTests(unittest.TestCase):
    def test_only_robot_is_actuated_and_mechanisms_are_passive(self):
        s = Session()
        m = s.model
        names = [m.joint(j).name for j in m.actuator_trnid[:, 0]]
        self.assertEqual((s.hand, m.nu), ("sharpa", 28))
        self.assertEqual((m.nmocap, m.neq), (0, 0))
        self.assertTrue(all(n.startswith(("wrist_", "right_")) for n in names))
        self.assertEqual(m.joint("dimm_free").type, mujoco.mjtJoint.mjJNT_FREE)
        self.assertNotIn("latch_hinge", names)
        spring = m.tendon("latch_toggle_spring").id
        self.assertGreater(m.tendon_stiffness[spring], 0)
        # copper sliders and catches are visuals; only one passive hinge besides the module's free joint
        self.assertEqual(sorted(m.joint(j).name for j in range(m.njnt) if m.jnt_bodyid[j] not in
                                {b for b, o in s.checker.owner.items() if o == "hand"} and
                                not m.joint(j).name.startswith("wrist_")), ["dimm_free", "latch_hinge"])

    def test_assets_match_their_manifest(self):
        from scene import verify_assets

        verify_assets()

    def test_latch_is_bistable_and_does_not_creep(self):
        s = Session()
        q = s.model.jnt_qposadr[s.model.joint("latch_hinge").id]
        for _ in range(250):  # 5 s with the hand parked
            s.step(s.hold_action())
        self.assertGreater(s.data.qpos[q], 0.5)
        s.reset()
        s.data.qpos[q] = 0.0
        mujoco.mj_forward(s.model, s.data)
        for _ in range(100):
            s.step(s.hold_action())
        self.assertLess(s.data.qpos[q], 0.02)


class ReplayTests(unittest.TestCase):
    def test_reference_solution_succeeds_twice_identically(self):
        first, second = replay(SOLUTION), replay(SOLUTION)
        self.assertTrue(first["success"], first["reason"])
        self.assertEqual((first["steps"], first["stage"], first["hand"]), (SUCCESS_STEP, 3, "sharpa"))
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertGreaterEqual(first["n_actions"] - first["steps"], 50)  # slack after success

    def test_float32_rows_replay_identically(self):
        rows = oracle_rows()
        self.assertTrue(np.array_equal(rows.astype(np.float32).astype(np.float64), rows))
        with tempfile.TemporaryDirectory() as tmp:
            result = replay(write(Path(tmp) / "f32.npz", rows.astype(np.float32).astype(np.float64)))
        self.assertEqual((result["success"], result["state_sha"]), (True, replay(SOLUTION)["state_sha"]))

    def test_noop_fails_and_replays_exactly(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "noop.npz"
            np.savez_compressed(path, actions=np.tile(s.hold_action(), (200, 1)))
            first, second = replay(path), replay(path)
        self.assertFalse(first["success"])
        self.assertEqual((first["stage"], first["reason"]), (0, ""))
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["initial_sha"], s.initial_sha)

    def test_truncations_fail(self):
        rows = oracle_rows()
        with tempfile.TemporaryDirectory() as tmp:
            before_latch = replay(write(Path(tmp) / "a.npz", rows[:1088]))
            hold_short = replay(write(Path(tmp) / "b.npz", rows[: SUCCESS_STEP - 1]))
        self.assertFalse(before_latch["success"])
        self.assertEqual(before_latch["stage"], 1)
        self.assertFalse(hold_short["success"])
        self.assertEqual(hold_short["stage"], 3)

    def test_drop_fails_at_once_and_resuming_cannot_undo_it(self):
        rows = oracle_rows()
        open_hand = Session().initial_targets[6:]
        dropped = rows.copy()
        dropped[DROP_ROW:, 6:] = open_hand
        resumed = np.vstack([rows[:DROP_ROW], np.tile(np.r_[rows[DROP_ROW, :6], open_hand], (6, 1)), rows[DROP_ROW:]])
        with tempfile.TemporaryDirectory() as tmp:
            a = replay(write(Path(tmp) / "drop.npz", dropped))
            b = replay(write(Path(tmp) / "resume.npz", resumed))
        for result in (a, b):
            self.assertFalse(result["success"])
            self.assertEqual(result["reason"], "module_dropped")
            self.assertLessEqual(result["failure_detail"]["control"], DROP_ROW + 3)
            self.assertLess(result["steps"], DROP_ROW + 5)

    def test_rows_after_success_are_not_executed(self):
        rows = oracle_rows()
        ram = np.tile(rows[-1], (100, 1))
        ram[:, 2] = Session().model.actuator_ctrlrange[2, 0]  # would drive the hand into the board
        with tempfile.TemporaryDirectory() as tmp:
            result = replay(write(Path(tmp) / "post.npz", np.vstack([rows, ram])))
        self.assertTrue(result["success"])
        self.assertEqual(result["state_sha"], replay(SOLUTION)["state_sha"])


class PredicateTests(unittest.TestCase):
    """Manually initialised module poses test the predicate and fail-fast checks, not robot solvability."""

    def park(self, s, rows=1):
        for _ in range(rows):
            s.step(s.hold_action())
            if s.done:
                break

    def test_seated_latched_module_needs_the_pick_stage(self):
        s = Session()
        place_module(s, *seated_pose(s))
        s.data.qpos[s.latch_q] = 0.0
        mujoco.mj_forward(s.model, s.data)
        self.park(s, 120)
        self.assertTrue(s.features()["seated"] and s.features()["latched"], s.features())
        self.assertFalse(s.success)  # stages are ordered: never picked
        self.assertEqual(s.checker.stage, 0)

    def test_seated_and_latched_after_pick_succeeds_after_a_one_second_hold(self):
        s = Session()
        place_module(s, *seated_pose(s))
        s.data.qpos[s.latch_q] = 0.0
        mujoco.mj_forward(s.model, s.data)
        s.checker.stage = 1  # as if picked
        self.park(s, 120)
        self.assertTrue(s.success, s.features())
        self.assertEqual(s.steps, s.config["checker"]["hold_steps"])

    def test_open_latch_or_reversed_module_never_counts(self):
        s = Session()
        place_module(s, *seated_pose(s))
        s.checker.stage = 1
        self.park(s, 120)
        self.assertFalse(s.success)  # latch still open (no edge pressed it)
        r = Session()
        place_module(r, *seated_pose(r, height=0.0042, yaw_flip=True))  # rests on the key
        r.checker.stage = 1
        self.park(r, 120)
        self.assertFalse(r.features()["seated"])
        self.assertFalse(r.success)

    def test_unsupported_module_fails_fast(self):
        s = Session()
        place_module(s, [0.70, -0.10, 0.95], [1, 0, 0, 0])
        self.park(s, 3)
        self.assertEqual(s.failure, "module_dropped")
        self.assertLessEqual(s.failure_detail["control"], 1)  # 0.2 m/s is reached after 20 ms of free fall

    def test_module_on_bench_board_or_other_socket_fails_fast(self):
        for pos in ([0.70, -0.25, 0.8255], [0.48, -0.06, 0.8432]):
            s = Session()
            place_module(s, pos, [0.7071067811865476, 0, 0, 0.7071067811865476])
            self.park(s, 3)
            # (a module resting on the bench is also below the workspace box floor z = 0.826 m)
            self.assertIn(s.failure, ("module_off_target_contact", "module_below_surface", "module_left_workspace"), pos)
            self.assertEqual(s.failure_detail["control"], 0)
        s = Session()
        sock = s.model.body("socket_1").id
        place_module(s, s.data.xpos[sock] + np.array([0, 0, 0.00095]), s.model.body_quat[s.model.body("socket_3").id])
        self.park(s, 3)
        self.assertEqual(s.failure, "module_off_target_contact")

    def test_module_outside_workspace_or_below_bench_fails(self):
        s = Session()
        place_module(s, [1.10, 0.0, 1.0], [1, 0, 0, 0])
        self.park(s)
        self.assertIn(s.failure, ("module_left_workspace", "module_dropped"))
        s = Session()
        place_module(s, [0.75, -0.17, 0.70], [1, 0, 0, 0])
        self.park(s)
        self.assertEqual(s.failure, "module_below_surface")


class ArchiveTests(unittest.TestCase):
    def test_forged_archive_fields_are_ignored(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forged.npz"
            np.savez_compressed(
                path,
                actions=np.tile(s.hold_action(), (40, 1)),
                success=np.array(True),
                state_sha=np.array("0" * 64),
                verdict=np.array(json.dumps({"stage": 3, "success": True})),
                config=np.array(json.dumps({"checker": {"hold_steps": 0}})),
            )
            result = replay(path)
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], 0)
        self.assertNotEqual(result["state_sha"], "0" * 64)

    def test_malformed_nonfinite_and_ambiguous_archives_are_rejected(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.npz"
            array = np.zeros((1, 28))
            array[0, 0] = np.nan
            np.savez(path, actions=array)
            with self.assertRaises(ValueError):
                load_actions(path)
            header = io.BytesIO()
            np.lib.format.write_array_header_1_0(header, {"descr": "<f8", "fortran_order": False,
                                                          "shape": (1000000000, 28)})
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("actions.npy", header.getvalue())
            with self.assertRaises(ValueError):
                load_actions(path)
            good, other = io.BytesIO(), io.BytesIO()
            np.save(good, np.tile(s.hold_action(), (3, 1)))
            np.save(other, np.tile(s.hold_action(), (9, 1)))
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("actions.npy", good.getvalue())
                archive.writestr("actions", other.getvalue())
            with self.assertRaises(ValueError):
                replay(path)
            path.write_bytes(b"PK\x03\x04 truncated")
            with self.assertRaises(ValueError):
                replay(path)

    def test_wrong_width_and_hand_label_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.npz"
            for width in (26, 27, 29):
                np.savez_compressed(path, actions=np.zeros((5, width)))
                with self.assertRaises(ValueError):
                    load_actions(path)
            for hand, width in (("wuji", 28), ("sharpa", 26)):
                np.savez_compressed(path, actions=np.zeros((5, width)), hand=np.array(hand))
                with self.assertRaises(ValueError):
                    load_trajectory(path)
            np.savez_compressed(path, actions=np.zeros((5, 28)), task=np.array("assemble_hamburger"))
            with self.assertRaises(ValueError):
                load_trajectory(path)

    def test_out_of_range_targets_are_rejected(self):
        s = Session()
        rows = np.tile(s.hold_action(), (3, 1))
        rows[1, 2] = 5.0
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                replay(write(Path(tmp) / "range.npz", rows))

    def test_empty_trusted_episode_fails_deterministically(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.npz"
            np.savez_compressed(path, actions=np.empty((0, 28)))
            with self.assertRaises(ValueError):
                load_actions(path)
            result = replay(path, trusted_service=True)
        self.assertFalse(result["success"])
        self.assertEqual(result["state_sha"], s.initial_sha)


class WujiTests(unittest.TestCase):
    def test_wuji_uses_the_same_wrist_stage_and_only_robot_actuators(self):
        sharpa, wuji = Session(hand="sharpa"), Session(hand="wuji")
        self.assertEqual((sharpa.action_dim, wuji.action_dim), (28, 26))
        self.assertEqual(sharpa.actuator_names[:6], wuji.actuator_names[:6])
        self.assertTrue(np.array_equal(sharpa.model.actuator_ctrlrange[:6], wuji.model.actuator_ctrlrange[:6]))
        self.assertTrue(np.array_equal(sharpa.model.actuator_gainprm[:6], wuji.model.actuator_gainprm[:6]))
        self.assertTrue(np.array_equal(sharpa.initial_targets[:6], wuji.initial_targets[:6]))
        self.assertTrue(all(name.startswith("r_wuji_") for name in wuji.actuator_names[6:]))
        self.assertEqual((wuji.model.nmocap, wuji.model.neq), (0, 0))

    def test_wuji_faces_like_the_wave_it_replaces(self):
        def flex(session, joint, point, is_site):
            mujoco.mj_resetData(session.model, session.data)
            session.data.qpos[session.qadr[:6]] = session.initial_targets[:6]
            mujoco.mj_forward(session.model, session.data)
            frame = session.data.body("right_hand_C_MC").xmat.reshape(3, 3)
            get = session.data.site if is_site else session.data.body
            before = get(point).xpos.copy()
            session.data.qpos[session.model.joint(joint).qposadr[0]] += 0.8
            mujoco.mj_forward(session.model, session.data)
            return frame.T @ (get(point).xpos - before)

        wave, wuji = Session(hand="sharpa"), Session(hand="wuji")
        a = flex(wave, "right_index_MCP_FE", "right_index_DP", False)
        b = flex(wuji, "r_wuji_r_index_finger_mcp_flex", "r_wuji_r_index_finger_tip", True)
        self.assertGreater(a @ b / np.linalg.norm(a) / np.linalg.norm(b), 0.5)

    def test_wuji_noop_fails_and_replays_exactly(self):
        s = Session(hand="wuji")
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "wuji.npz", np.tile(s.hold_action(), (150, 1)), hand="wuji")
            first, second = replay(path), replay(path)
        self.assertEqual(first["hand"], "wuji")
        self.assertFalse(first["success"])
        self.assertEqual(first["reason"], "")
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["initial_sha"], s.initial_sha)

    def test_environment_selects_session_hand_but_never_the_graded_hand(self):
        previous = os.environ.get("DEXHAND_HAND")
        os.environ["DEXHAND_HAND"] = "wuji"
        try:
            self.assertEqual(Session().hand, "wuji")
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sharpa.npz"
                np.savez_compressed(path, actions=np.tile(Session(hand="sharpa").hold_action(), (3, 1)))
                self.assertEqual(load_trajectory(path)[1], "sharpa")
                self.assertEqual(replay(path)["hand"], "sharpa")
        finally:
            if previous is None:
                os.environ.pop("DEXHAND_HAND", None)
            else:
                os.environ["DEXHAND_HAND"] = previous


if __name__ == "__main__":
    unittest.main()
