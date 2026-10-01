#!/usr/bin/env python3
"""Bore contact and finite-shaft terminal regressions; no new dynamics."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import sys
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.assets.geometry.lock_picking import LockGeometry
from topogym.config.registry import task_definition


def fixture(tier="easy", *, offset=0., tilt=0.):
    task = task_definition("lock_picking", tier)(seed=0)
    task.table_height_m = .7
    task.layout = g = LockGeometry(**{**task.config["geometry"], "axis_z": .885})
    rotation = Rotation.from_euler("y", tilt, degrees=True)
    axis = rotation.apply([1., 0., 0.])
    # Centre the tilted axis in the stack. All tabs sit between/past plates.
    x = g.disc_x(3)+.012
    mid = (g.disc_x(0)+g.disc_x(3))/2
    p = np.array([x, g.center_y+offset, g.axis_z])
    p[2] += axis[2]*(x-mid)/axis[0]
    state = dict(physics_step=0, bodies={"lock_key": dict(position_m=p,
        quaternion_wxyz=rotation.as_quat()[[3, 0, 1, 2]])}, articulations={
        f"lock_disc_{i}": dict(joints={"disc_hinge": dict(position=[0.])}) for i in range(3)})
    return task, state


class LockTerminalChecks(unittest.TestCase):
    def test_recorded_released_poses_in_all_tiers(self):
        records = json.loads((ROOT/'tests/fixtures/lock_contact_recorded_poses.json').read_text())
        self.assertEqual({item["tier"] for item in records}, {"easy", "medium", "hard"})
        for item in records:
            with self.subTest(tier=item["tier"]):
                task = task_definition("lock_picking", item["tier"])(seed=0)
                task.table_height_m = item["table_height_m"]
                task.layout = LockGeometry(**item["geometry"])
                reached, failure, metrics = task.evaluate_state(item["world"])
                self.assertTrue(reached, metrics)
                self.assertIsNone(failure)
                self.assertGreater(metrics["shaft_bore_excess_m"], 0.)
                # The old strict positive-gap rule rejects these actual poses.
                self.assertGreater(metrics["shaft_bore_excess_m"]+.0001, 0.)

    def test_centered_and_wall_contact_in_all_tiers(self):
        for tier in ("easy", "medium", "hard"):
            for offset in (0., .001, -.001, .001006):
                with self.subTest(tier=tier, offset=offset):
                    task, state = fixture(tier, offset=offset)
                    reached, failure, metrics = task.evaluate_state(state)
                    self.assertTrue(reached, metrics)
                    self.assertIsNone(failure)
                    self.assertTrue(metrics["shaft_through_all_plates"])

    def test_contact_budget_has_a_boundary(self):
        for offset, expected in ((.001009, True), (.001011, False), (.0011, False)):
            task, state = fixture(offset=offset)
            self.assertEqual(task.evaluate_state(state)[0], expected)

    def test_small_tilt_passes_but_tilt_through_wall_does_not(self):
        for tilt, expected in ((.1, True), (.5, False), (90., False), (180., False)):
            task, state = fixture(tilt=tilt)
            self.assertEqual(task.evaluate_state(state)[0], expected)

    def test_bore_geometry_not_an_independent_one_degree_gate(self):
        task, state = fixture(tilt=1.1)
        # Wider bores can legally accommodate this tilt (current tight tiers cannot).
        task.layout = replace(task.layout, bore_radius=.014)
        self.assertTrue(task.evaluate_state(state)[0])

    def test_final_plate_alone_is_insufficient(self):
        task, state = fixture()
        # Shaft tail has passed plate zero, but still spans END.
        state["bodies"]["lock_key"]["position_m"][0] = task.layout.disc_x(0)+task.layout.grip_offset+.03
        reached, _, metrics = task.evaluate_state(state)
        self.assertTrue(metrics["shaft_in_goal"])
        self.assertFalse(metrics["shaft_through_all_plates"])
        self.assertFalse(reached)

    def test_leading_tab_and_slot_interference_still_rejected(self):
        task, state = fixture()
        state["bodies"]["lock_key"]["position_m"][0] = task.layout.disc_x(3)
        self.assertFalse(task.evaluate_state(state)[0])
        state["bodies"]["lock_key"]["quaternion_wxyz"] = Rotation.from_euler(
            "x", 90., degrees=True).as_quat()[[3, 0, 1, 2]]
        self.assertTrue(task.evaluate_state(state)[2]["clearance_issues"])

    def test_rotor_failure_overrides_contact_success(self):
        task, state = fixture(offset=.001)
        state["articulations"]["lock_disc_0"]["joints"]["disc_hinge"]["position"] = [np.radians(16.)]
        reached, failure, _ = task.evaluate_state(state)
        self.assertFalse(reached)
        self.assertEqual(failure, "rotor_limit_exceeded")

    def test_stability_interruption_and_rewind(self):
        task, state = fixture(offset=.001)
        self.assertTrue(task.goal_complete)  # Use the shipped default without overriding it.
        task.initialize(state)
        for step in range(1, 5):
            state["physics_step"] = step
            self.assertFalse(task.update(state, .1).task_success)
        saved = deepcopy(task.get_state())
        state["physics_step"] = 5
        state["bodies"]["lock_key"]["position_m"][1] += .001
        self.assertFalse(task.update(state, .1).task_success)
        self.assertEqual(task.stable_time_s, 0.)
        task.set_state(saved)
        state["bodies"]["lock_key"]["position_m"][1] -= .001
        for step in (5, 6):
            state["physics_step"] = step
            result = task.update(state, .1)
        self.assertTrue(result.task_success)
        self.assertTrue(result.terminated)
        self.assertEqual(result.reward, 1.)
        self.assertTrue(result.metrics["goal_evaluation_complete"])

    def test_old_air_gap_config_is_not_silently_reinterpreted(self):
        with self.assertRaisesRegex(ValueError, "terminal parameter"):
            task_definition("lock_picking", "easy")({"terminal": {"shaft_clearance_m": .0001}})


if __name__ == "__main__":
    unittest.main()
