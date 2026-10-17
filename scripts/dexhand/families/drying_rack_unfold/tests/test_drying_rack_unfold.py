"""Authoring tests: physical predicate, fail-fast, trust boundary and hand selection for drying_rack_unfold.

Run from anywhere: `python -m unittest scripts/dexhand/families/drying_rack_unfold/tests/test_drying_rack_unfold.py`
(needs DEXHAND_ASSET_DIR / WUJI_ASSET_DIR outside the image). The positive test replays the 2,415-row oracle (~10 s).
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

import mujoco
import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

from replay import load_actions, load_trajectory, replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import LEG_JOINTS, hands  # noqa: E402

ORACLE = FAMILY / "solution" / "trajectory.npz"


def oracle_rows():
    return load_trajectory(ORACLE)[0]


def save(session, rows, folder, name):
    path = Path(folder) / name
    session.save_trajectory(np.asarray(rows, dtype=np.float64), path)
    return path


class RackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = oracle_rows()
        s = Session()
        cls.stages = []
        for row in cls.rows:
            s.step(row)
            if not cls.stages or s.checker.stage != cls.stages[-1][1]:
                cls.stages.append((s.steps, int(s.checker.stage)))
            if s.done:
                break
        cls.final = s.status()
        cls.final_sha = s.state_sha()

    # ------------------------------------------------------------------ model
    def test_only_robot_is_actuated_and_rack_is_free(self):
        s = Session()
        self.assertEqual(s.hand, "sharpa")
        self.assertEqual(s.model.nu, 28)
        self.assertEqual(s.model.nmocap, 0)
        self.assertEqual(s.model.neq, 0)
        joints = [s.model.joint(int(j)).name for j in s.model.actuator_trnid[:, 0]]
        self.assertTrue(all(name.startswith(("wrist_", "right_")) for name in joints))
        self.assertEqual(s.model.joint("rack_free").type, mujoco.mjtJoint.mjJNT_FREE)
        for name in ("fold_hinge",) + LEG_JOINTS:
            jid = s.model.joint(name).id
            self.assertEqual(s.model.jnt_type[jid], mujoco.mjtJoint.mjJNT_HINGE)
            self.assertTrue(s.model.jnt_limited[jid])
            self.assertEqual(s.model.jnt_stiffness[jid], 0.0)  # passive: no springs, no actuators
        self.assertAlmostEqual(sum(s.model.body_mass[b] for b in s.checker.rack_bodies), 0.51, places=6)

    def test_reset_is_the_folded_storage_pose(self):
        s = Session()
        f = s.features()
        self.assertAlmostEqual(f["fold_angle_rad"], np.pi, places=3)
        self.assertTrue(all(abs(a) < 1e-3 for a in f["leg_angles_rad"]))
        self.assertGreater(f["tilt_deg"], 170)  # underside up
        self.assertEqual(f["stage"], 0)

    # ------------------------------------------------------------------ positive
    def test_oracle_succeeds_with_ordered_stages_and_slack(self):
        self.assertTrue(self.final["success"])
        self.assertEqual(self.final["reason"], "success")
        self.assertEqual([g for _, g in self.stages], [0, 1, 2, 3])
        success_step = self.stages[-1][0]
        self.assertGreaterEqual(len(self.rows) - success_step, 50)
        self.assertTrue(all(a >= np.pi / 2 for a in self.final["leg_angles_rad"]))
        self.assertLessEqual(self.final["tilt_deg"], 10)
        self.assertTrue(all(self.final["feet_on_counter"]))
        self.assertEqual(self.final["hand_rack_contacts"], 0)

    def test_oracle_rows_are_float32_exact_and_replay_identically(self):
        self.assertTrue(np.array_equal(self.rows.astype(np.float32).astype(np.float64), self.rows))
        with tempfile.TemporaryDirectory() as tmp:
            path = save(Session(), self.rows.astype(np.float32), tmp, "f32.npz")
            result = replay(path)
        self.assertTrue(result["success"])
        self.assertEqual(result["state_sha"], self.final_sha)

    def test_rows_after_success_are_not_executed(self):
        s = Session()
        noise = np.tile(s.initial_targets, (200, 1))
        st = s.replay(np.vstack([self.rows, noise]))
        self.assertTrue(st["success"])
        self.assertEqual(st["steps"], self.stages[-1][0])

    # ------------------------------------------------------------------ partial / negative
    def test_noop_fails_and_replays_exactly(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "noop.npz"
            np.savez_compressed(path, actions=np.tile(s.hold_action(), (150, 1)), success=np.array(True))
            first, second = replay(path), replay(path)
        self.assertFalse(first["success"])
        self.assertEqual(first["stage"], 0)
        self.assertEqual(first["state_sha"], second["state_sha"])

    def test_truncated_before_standing_and_before_hold_end_fail(self):
        standing = next(step for step, g in self.stages if g == 2)
        success = self.stages[-1][0]
        for cut, stage in ((standing - 60, 1), (success - 1, 2)):
            st = Session().replay(self.rows[:cut])
            self.assertFalse(st["success"], cut)
            self.assertEqual(st["stage"], stage)
            self.assertEqual(st["reason"], "")

    def test_unfolded_but_not_standing_is_not_success(self):
        unfolded = next(step for step, g in self.stages if g == 1)
        s = Session()
        hold = s.replay(self.rows[: unfolded + 30])
        self.assertTrue(hold["unfolded"])
        tail = np.tile(self.rows[unfolded + 29], (120, 1))
        for row in tail:
            s.step(row)
        self.assertFalse(s.status()["success"])
        self.assertLess(s.status()["stage"], 2)

    def test_release_mid_flip_fails_fast_as_a_drop(self):
        s = Session()
        cut = None
        for i, row in enumerate(self.rows):
            s.step(row)
            if s.status()["tilt_deg"] < 100 and s.status()["hand_rack_contacts"] > 0:
                cut = i
                break
        self.assertIsNotNone(cut)
        last = self.rows[cut].copy()
        opened = last.copy(); opened[6:] = s.initial_targets[6:]
        away = opened.copy(); away[0] -= 0.25; away[2] += 0.10
        rows = list(self.rows[: cut + 1]) + [last + (opened - last) * t / 10 for t in range(1, 11)]
        rows += [opened + (away - opened) * t / 40 for t in range(1, 41)] + [away] * 300
        st = Session().replay(np.array(rows))
        self.assertFalse(st["success"])
        self.assertEqual(st["reason"], "rack_dropped")
        self.assertLess(st["steps"], len(rows))  # the episode ended at the drop; later rows were not executed

    def test_knock_off_push_fails_fast(self):
        unfolded = next(step for step, g in self.stages if g == 1)
        s = Session()
        lo, hi = s.model.actuator_ctrlrange.T
        rows = list(self.rows[: unfolded + 20])
        k0 = rows[-1].copy(); k0[6:] = s.initial_targets[6:]
        p0 = k0.copy(); p0[:6] = [-0.37, 0.50, 0.20, 0.0, 1.3, 0.0]
        ph = p0.copy(); ph[2] = 0.40
        p1 = p0.copy(); p1[1] = -0.6
        rows += [k0 + (ph - k0) * t / 60 for t in range(1, 61)] + [ph + (p0 - ph) * t / 40 for t in range(1, 41)]
        rows += [p0 + (p1 - p0) * t / 150 for t in range(1, 151)] + [p1] * 100
        st = s.replay(np.clip(np.array(rows), lo, hi))
        self.assertFalse(st["success"])
        self.assertEqual(st["reason"], "rack_off_counter")

    def test_invariants_fail_on_below_table_and_floor_states(self):
        s = Session()
        adr = s.model.joint("rack_free").qposadr[0]
        s.data.qpos[adr + 2] = s.config["table_z"] - 0.05
        mujoco.mj_forward(s.model, s.data)
        self.assertEqual(s.checker.invariant(s.data)[0], "rack_below_table")
        s.reset()
        s.data.qpos[adr] = 2.0
        mujoco.mj_forward(s.model, s.data)
        self.assertEqual(s.checker.invariant(s.data)[0], "rack_off_counter")

    # ------------------------------------------------------------------ trust boundary
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
                config=np.array(json.dumps({"predicate": {"leg_open_min_rad": 0}})),
            )
            result = replay(path)
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], 0)
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
            path.write_bytes(b"PK\x03\x04 truncated")
            with self.assertRaises(ValueError):
                replay(path)

    def test_nonfinite_out_of_range_and_wrong_width_are_rejected(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.npz"
            array = np.tile(s.hold_action(), (2, 1))
            array[0, 3] = np.nan
            np.savez(path, actions=array)
            with self.assertRaises(ValueError):
                load_actions(path)
            array = np.tile(s.hold_action(), (2, 1))
            array[1, 0] = 5.0  # wrist_x beyond its range
            np.savez(path, actions=array)
            with self.assertRaises(ValueError):
                replay(path)
            for width in (26, 27, 29):
                np.savez_compressed(path, actions=np.zeros((5, width)))
                with self.assertRaises(ValueError):
                    load_actions(path)
            data = io.BytesIO()
            np.lib.format.write_array_header_1_0(data, {"descr": "<f8", "fortran_order": False, "shape": (10**9, 28)})
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("actions.npy", data.getvalue())
            with self.assertRaises(ValueError):
                load_actions(path)

    def test_hand_label_and_width_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.npz"
            for hand, width in (("wuji", 28), ("sharpa", 26)):
                np.savez_compressed(path, actions=np.zeros((5, width)), hand=np.array(hand))
                with self.assertRaises(ValueError):
                    load_trajectory(path)
            np.savez_compressed(path, actions=np.zeros((5, 28)), hand=np.array("shadow"))
            with self.assertRaises(ValueError):
                load_trajectory(path)
            np.savez_compressed(path, actions=np.zeros((5, 28)), task=np.array("assemble_hamburger"))
            with self.assertRaises(ValueError):
                load_trajectory(path)

    def test_state_sha_ignores_text_but_not_physics(self):
        a, b = Session(), Session()
        b.config = dict(b.config, instruction="edited prose", description="edited")
        self.assertEqual(a.state_sha(), b.state_sha())
        b.config = dict(b.config, predicate=dict(b.config["predicate"], leg_open_min_rad=1.0))
        self.assertNotEqual(a.state_sha(), b.state_sha())

    # ------------------------------------------------------------------ Wuji
    def test_wuji_uses_the_same_wrist_stage_and_only_robot_actuators(self):
        s, w = Session(), Session(hand="wuji")
        self.assertEqual(w.model.nu, 26)
        self.assertEqual(w.actuator_names[:6], s.actuator_names[:6])
        self.assertTrue(np.allclose(w.model.actuator_ctrlrange[:6], s.model.actuator_ctrlrange[:6]))
        self.assertTrue(all(n.startswith("r_wuji_") for n in w.actuator_names[6:]))
        self.assertEqual(w.model.nmocap, 0)
        self.assertEqual(w.model.neq, 0)

    def test_wuji_noop_fails_and_replays_exactly(self):
        w = Session(hand="wuji")
        with tempfile.TemporaryDirectory() as tmp:
            path = save(w, np.tile(w.initial_targets, (150, 1)), tmp, "wuji_noop.npz")
            first, second = replay(path), replay(path)
        self.assertEqual(first["hand"], "wuji")
        self.assertFalse(first["success"])
        self.assertEqual(first["state_sha"], second["state_sha"])

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

    def test_hands_module_is_the_shared_one(self):
        self.assertTrue(hasattr(hands, "replace_wave_hands"))


if __name__ == "__main__":
    unittest.main()
