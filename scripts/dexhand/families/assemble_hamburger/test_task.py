"""Trust-boundary, negative-control and physical predicate checks."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import mujoco
import numpy as np

from replay import load_actions, load_trajectory, replay
from runtime import Session
from scene import LAYER_HALF_HEIGHT, hands


class TaskTests(unittest.TestCase):
    def test_only_robot_is_actuated(self):
        s = Session()
        names = [s.model.joint(jid).name for jid in s.model.actuator_trnid[:, 0]]
        self.assertEqual(s.hand, "sharpa")
        self.assertEqual(s.model.nu, 28)
        self.assertEqual(s.model.nmocap, 0)
        self.assertEqual(s.model.neq, 0)
        self.assertTrue(all(name.startswith(("wrist_", "right_")) for name in names))
        for name in s.names:
            self.assertEqual(s.model.joint(name + "_free").type, mujoco.mjtJoint.mjJNT_FREE)
        self.assertEqual(len(s.bend_jids), 4)
        self.assertTrue(np.all(s.model.jnt_stiffness[s.bend_jids] > 0))

    def test_noop_fails_and_replays_exactly(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "noop.npz"
            np.savez_compressed(
                path, actions=np.tile(s.hold_action(), (130, 1)), config=json.dumps({"recipe": [], "success": True})
            )
            first, second = replay(path), replay(path)
        self.assertFalse(first["success"])
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["initial_sha"], s.initial_sha)
        self.assertEqual(first["verdict"]["aligned_layers"], 1)

    def fixture(self, swapped=False):
        """A manually initialized stack tests the predicate, not robot solvability."""
        s = Session()
        order = s.names.copy()
        if swapped:
            order[2], order[3] = order[3], order[2]
        top = s.config["plate_z"]
        for name in order:
            h = LAYER_HALF_HEIGHT[name]
            adr = s.model.joint(name + "_free").qposadr[0]
            s.data.qpos[adr : adr + 3] = [*s.config["target_xy"], top + h]
            top += 2 * h
        mujoco.mj_forward(s.model, s.data)
        return s

    def test_released_stack_and_wrong_recipe(self):
        correct, wrong = self.fixture(), self.fixture(swapped=True)
        for _ in range(180):
            correct.step(correct.hold_action())
            wrong.step(wrong.hold_action())
        self.assertTrue(correct.success, correct.features())
        # Success ends the episode: the released hold completed and later rows were not executed.
        self.assertEqual(correct.status()["reason"], "success")
        self.assertEqual(correct.released_hold, correct.config["released_hold_steps"])
        self.assertLess(correct.steps, 180)
        self.assertFalse(wrong.success)
        self.assertFalse(wrong.features()["ordered"])
        self.assertEqual(correct.features()["adjacent_contacts"], 5)
        self.assertEqual(correct.features()["hand_contacts"], 0)

    def test_malformed_header_and_nonfinite_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.npz"
            array = np.zeros((1, 28))
            array[0, 0] = np.nan
            np.savez(path, actions=array)
            with self.assertRaises(ValueError):
                load_actions(path)
            data = io.BytesIO()
            np.lib.format.write_array_header_1_0(
                data, {"descr": "<f8", "fortran_order": False, "shape": (1000000000, 28)}
            )
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("actions.npy", data.getvalue())
            with self.assertRaises(ValueError):
                load_actions(path)

    def test_missing_layer_fails(self):
        s = Session()
        top = s.config["plate_z"]
        for name in s.names[:-1]:
            h = LAYER_HALF_HEIGHT[name]
            adr = s.model.joint(name + "_free").qposadr[0]
            s.data.qpos[adr : adr + 3] = [*s.config["target_xy"], top + h]
            top += 2 * h
        mujoco.mj_forward(s.model, s.data)
        for _ in range(180):
            s.step(s.hold_action())
        f = s.features()
        self.assertFalse(s.success)
        self.assertIsNone(s.failure)
        self.assertEqual(f["aligned_layers"], 5)
        self.assertEqual(f["adjacent_contacts"], 4)

    def place(self, s, name, position):
        adr = s.model.joint(name + "_free").qposadr[0]
        s.data.qpos[adr : adr + 3] = position
        mujoco.mj_forward(s.model, s.data)

    def test_dropped_ingredient_fails_fast(self):
        s = Session()
        self.place(s, "tomato", (0.30, 0.35, 0.33))
        for _ in range(60):
            s.step(s.hold_action())
            if s.failure:
                break
        self.assertEqual(s.failure, "ingredient_dropped")
        self.assertEqual(s.failure_detail["ingredient"], "tomato")
        status = s.status()
        self.assertTrue(status["done"])
        self.assertTrue(status["failed"])
        self.assertEqual(status["reason"], "ingredient_dropped")
        self.assertFalse(s.success)
        # The failure is permanent: later rows are not executed and cannot recover the episode.
        sha, steps = s.state_sha(), s.steps
        for _ in range(5):
            s.step(s.hold_action())
        self.assertEqual((s.state_sha(), s.steps, s.failure), (sha, steps, "ingredient_dropped"))

    def test_ingredient_outside_workspace_or_below_table_fails(self):
        s = Session()
        self.place(s, "patty", (0.70, 0.0, 0.50))
        s.step(s.hold_action())
        self.assertEqual(s.failure, "ingredient_left_workspace")
        self.assertEqual(s.failure_detail, {"ingredient": "patty", "control": 0, "substep": 0})
        s = Session()
        self.place(s, "lettuce", (0.70, 0.0, 0.25))
        s.step(s.hold_action())
        self.assertEqual(s.failure, "ingredient_below_table")
        self.assertEqual(s.failure_detail["ingredient"], "lettuce")

    def test_bend_limit_fails_fast(self):
        s = Session()
        s.data.qpos[s.model.joint("cheese_bend_1").qposadr[0]] = 0.68
        mujoco.mj_forward(s.model, s.data)
        s.step(s.hold_action())
        self.assertEqual(s.failure, "bend_limit_exceeded")
        self.assertEqual(s.failure_detail["ingredient"], "cheese")

    def sweep(self):
        """Actuator-only negative: lower the wrist and sweep it through the patty on its support."""
        s = Session()
        rows = [s.hold_action()]
        for t in np.linspace(0, 1, 60):
            row = rows[0].copy()
            row[2] = 0.54 + (0.40 - 0.54) * t
            rows.append(row)
        for t in np.linspace(0, 1, 120):
            row = rows[-1].copy()
            row[0] = 0.44 + (-0.05 - 0.44) * t
            rows.append(row)
        return np.asarray(rows + [rows[-1]] * 300)

    def test_knocked_off_ingredient_ends_replay_and_later_rows_are_ignored(self):
        rows = self.sweep()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sweep.npz"
            np.savez_compressed(path, actions=rows)
            first, second = replay(path), replay(path)
        self.assertFalse(first["success"])
        self.assertEqual(first["failure"], "ingredient_dropped")
        self.assertEqual(first["failure_detail"]["ingredient"], "patty")
        self.assertLess(first["steps"], len(rows))
        self.assertEqual(first["rows_submitted"], len(rows))
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["steps"], second["steps"])

    def test_forged_archive_fields_are_ignored(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forged.npz"
            np.savez_compressed(
                path,
                actions=np.tile(s.hold_action(), (40, 1)),
                success=np.array(True),
                failure=np.array(""),
                state_sha=np.array("0" * 64),
                verdict=np.array(json.dumps({"aligned_layers": 6, "success": True})),
                positions=np.zeros((6, 3)),
            )
            result = replay(path)
        self.assertFalse(result["success"])
        self.assertIsNone(result["failure"])
        self.assertEqual(result["stage"], 1)
        self.assertNotEqual(result["state_sha"], "0" * 64)

    def test_ambiguous_or_corrupt_members_are_clean_rejections(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambiguous.npz"
            good, other = io.BytesIO(), io.BytesIO()
            np.save(good, np.tile(s.hold_action(), (3, 1)))
            np.save(other, np.tile(s.hold_action(), (9, 1)))
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("actions.npy", good.getvalue())
                archive.writestr("actions", other.getvalue())
            with self.assertRaises(ValueError):
                replay(path)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("actions.npy", good.getvalue())
                archive.writestr("actions", b"not an array")
            with self.assertRaises(ValueError):
                replay(path)
            path.write_bytes(b"PK\x03\x04 truncated")
            with self.assertRaises(ValueError):
                replay(path)

    def test_wrong_action_width_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for width in (26, 27, 29):
                path = Path(tmp) / f"width{width}.npz"
                np.savez_compressed(path, actions=np.zeros((5, width)))
                with self.assertRaises(ValueError):
                    load_actions(path)

    def test_wuji_uses_the_same_wrist_stage_and_only_robot_actuators(self):
        sharpa, wuji = Session(hand="sharpa"), Session(hand="wuji")
        self.assertEqual((sharpa.action_dim, wuji.action_dim), (28, 26))
        self.assertEqual(sharpa.actuator_names[:6], wuji.actuator_names[:6])
        self.assertTrue(np.array_equal(sharpa.model.actuator_ctrlrange[:6], wuji.model.actuator_ctrlrange[:6]))
        self.assertTrue(np.array_equal(sharpa.model.actuator_gainprm[:6], wuji.model.actuator_gainprm[:6]))
        self.assertTrue(np.array_equal(sharpa.initial_targets[:6], wuji.initial_targets[:6]))
        self.assertTrue(all(name.startswith("r_wuji_") for name in wuji.actuator_names[6:]))
        self.assertEqual(wuji.model.nmocap, 0)
        self.assertEqual(wuji.model.neq, 0)
        self.assertNotEqual(sharpa.initial_sha, wuji.initial_sha)
        for name in wuji.names:
            self.assertEqual(wuji.model.joint(name + "_free").type, mujoco.mjtJoint.mjJNT_FREE)
        hand_bodies = [b for b, owner in wuji.owner.items() if owner == "hand"]
        self.assertTrue(any(wuji.model.body(b).name.startswith("r_wuji_") for b in hand_bodies))

    def test_wuji_faces_like_the_wave_it_replaces(self):
        """Index flexion moves the tip the same way for both hands, and the thumb sits on the Wave thumb's side."""

        def flex_direction(session, joint, site_or_body, is_site):
            mujoco.mj_resetData(session.model, session.data)
            session.data.qpos[session.qadr[:6]] = session.initial_targets[:6]  # same wrist pose, straight fingers
            mujoco.mj_forward(session.model, session.data)
            frame = session.data.body("right_hand_C_MC").xmat.reshape(3, 3)
            point = session.data.site(site_or_body) if is_site else session.data.body(site_or_body)
            before = point.xpos.copy()
            session.data.qpos[session.model.joint(joint).qposadr[0]] += 0.8
            mujoco.mj_forward(session.model, session.data)
            point = session.data.site(site_or_body) if is_site else session.data.body(site_or_body)
            return frame.T @ (point.xpos - before)

        wave, wuji = Session(hand="sharpa"), Session(hand="wuji")
        wave_move = flex_direction(wave, "right_index_MCP_FE", "right_index_DP", False)
        wuji_move = flex_direction(wuji, "r_wuji_r_index_finger_mcp_flex", "r_wuji_r_index_finger_tip", True)
        cosine = wave_move @ wuji_move / np.linalg.norm(wave_move) / np.linalg.norm(wuji_move)
        self.assertGreater(cosine, 0.5)
        for s, thumb, pinky, sites in (
            (wave, "right_thumb_DP", "right_pinky_DP", False),
            (wuji, "r_wuji_r_thumb_tip", "r_wuji_r_pinky_tip", True),
        ):
            mujoco.mj_forward(s.model, s.data)
            palm = s.data.body("right_hand_C_MC")
            side = palm.xmat.reshape(3, 3)[:, 1]
            get = s.data.site if sites else s.data.body
            self.assertGreater((get(thumb).xpos - palm.xpos) @ side, (get(pinky).xpos - palm.xpos) @ side)

    def test_wuji_noop_fails_and_replays_exactly(self):
        s = Session(hand="wuji")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wuji.npz"
            hands.write_trajectory(path, np.tile(s.hold_action(), (130, 1)), hand="wuji", task="assemble_hamburger")
            first, second = replay(path), replay(path)
        self.assertEqual(first["hand"], "wuji")
        self.assertFalse(first["success"])
        self.assertIsNone(first["failure"])
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["initial_sha"], s.initial_sha)

    def test_wuji_reference_solution_succeeds(self):
        """solution/wuji/trajectory.npz (tools/wuji_gen.py): the packaged Wuji Hand 2.2 oracle, about a minute."""
        result = replay(Path(__file__).resolve().parent / "solution/wuji/trajectory.npz")
        self.assertTrue(result["success"])
        self.assertEqual((result["hand"], result["steps"], result["n_actions"]), ("wuji", 5847, 5847))
        self.assertEqual(result["state_sha"], "7a907c6173c9138f8f7c6a188d8f76926c31a54a6ef0f75edd485a76500f4c80")

    def test_hand_label_and_width_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.npz"
            for hand, width in (("wuji", 28), ("sharpa", 26), ("wuji", 27)):
                np.savez_compressed(path, actions=np.zeros((5, width)), hand=np.array(hand))
                with self.assertRaises(ValueError):
                    load_trajectory(path)
            np.savez_compressed(path, actions=np.zeros((5, 26)))
            with self.assertRaises(ValueError):  # unlabeled archives are Sharpa archives
                load_trajectory(path)
            np.savez_compressed(path, actions=np.zeros((5, 28)), hand=np.array("shadow"))
            with self.assertRaises(ValueError):
                load_trajectory(path)
            np.savez_compressed(path, actions=np.zeros((5, 28)), task=np.array("essential_cube_layer"))
            with self.assertRaises(ValueError):
                load_trajectory(path)
            s = Session(hand="wuji")
            names = list(s.actuator_names)
            names[6], names[7] = names[7], names[6]
            hands.write_trajectory(path, np.tile(s.hold_action(), (5, 1)), hand="wuji", actuator_names=names)
            with self.assertRaises(ValueError):
                replay(path)

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


if __name__ == "__main__":
    unittest.main()
