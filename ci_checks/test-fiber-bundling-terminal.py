#!/usr/bin/env python3
"""Synthetic history checks for the two new counts; not robot physics proof."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.config.registry import task_definition


def contacts(tick, events=()):
    return dict(schema_version=1, physics_step=tick, substeps_complete=True,
        geometry_roles_complete=True, robot_geometry_complete=True,
        expected_substeps=4 if tick else 0, sampled_substeps=4 if tick else 0,
        sampling_scope="substeps" if tick else "initial_pose", events=list(events))


def fixture(variant):
    task = task_definition("fiber_bundling", variant)(seed=0)
    layout = task.layout_class(**task.config["geometry"], seed=0)
    task.layout, task.table_height_m = layout, .9196429
    z = task.table_height_m + .24
    links = {}
    for i in range(layout.fiber_count):
        a = i * 2 * np.pi / layout.fiber_count
        for j in range(layout.fiber_segments):
            links[f"fiber_{i:02d}_{j:02d}"] = dict(
                position_m=[-.1 + j * .008, .008 * np.cos(a), z + .008 * np.sin(a)],
                quaternion_wxyz=[1., 0., 0., 0.])
    links["trunk_05"] = dict(position_m=[-.14, 0., z], quaternion_wxyz=[1., 0., 0., 0.])
    world = dict(physics_step=0, articulations={"fiber_bundle": {"links": links}},
        bodies={"bundling_ring": dict(position_m=[0., 0., z],
            quaternion_wxyz=Rotation.from_euler("y", 90, degrees=True).as_quat()[[3, 0, 1, 2]].tolist())},
        contact_events=contacts(0))
    return task, world


def advance(world, distance=0., *, omitted=None):
    for name, link in world["articulations"]["fiber_bundle"]["links"].items():
        if omitted is None or not name.startswith(omitted):
            link["position_m"][0] += distance
    world["physics_step"] += 1
    world["contact_events"] = contacts(world["physics_step"])


class FiberTerminalChecks(unittest.TestCase):
    def test_full_passage_needs_stability_and_can_restore_birth(self):
        for variant in ("very_easy", "easier"):
            task, world = fixture(variant)
            task.initialize(world)
            birth = task.get_state()
            initial = deepcopy(world)
            self.assertFalse(task.result.task_success)
            for tick in range(1, 7):
                advance(world, .2 if tick == 1 else 0.)
                result = task.update(world, .1)
                self.assertEqual(result.task_success, tick == 6)
            self.assertEqual(result.metrics["strands_complete"], [True] * task.layout.fiber_count)
            task.set_state(birth)
            self.assertFalse(task.result.terminated)
            self.assertFalse(task.evaluate_state(initial)[0])

    def test_incomplete_bypass_reverse_and_missing_contact_evidence(self):
        for variant in ("very_easy", "easier"):
            for case in ("missing_strand", "tips_only", "bypass", "reverse", "missing_coverage", "bend"):
                with self.subTest(variant=variant, case=case):
                    task, world = fixture(variant)
                    if case == "bypass":
                        for link in world["articulations"]["fiber_bundle"]["links"].values():
                            link["position_m"][1] += .1
                    if case == "reverse":
                        advance(world, .2)
                        world["physics_step"], world["contact_events"] = 0, contacts(0)
                    task.initialize(world)
                    for tick in range(8):
                        distance = (-.2 if case == "reverse" else .04 if case == "tips_only" else .2) if tick == 0 else 0.
                        advance(world, distance, omitted="fiber_01_" if case == "missing_strand" else None)
                        if case == "missing_coverage" and tick == 0:
                            world["contact_events"]["substeps_complete"] = False
                        if case == "bend":
                            world["articulations"]["fiber_bundle"]["links"]["fiber_00_09"]["quaternion_wxyz"] = (
                                Rotation.from_euler("y", 100, degrees=True).as_quat()[[3, 0, 1, 2]].tolist())
                        self.assertFalse(task.update(world, .1).task_success)

    def test_zero_force_gripper_touch_fails_but_sheath_touch_does_not(self):
        for variant in ("very_easy", "easier"):
            for role in ("fiber_strand", "fiber_sheath"):
                task, world = fixture(variant)
                task.initialize(world)
                advance(world)
                world["contact_events"] = contacts(1, [dict(touching=True, role_a="robot", role_b=role,
                    robot_part_a="gripper", robot_part_b=None, force_n=0.)])
                result = task.update(world, .1)
                self.assertEqual(result.terminated, role == "fiber_strand")
                if role == "fiber_strand":
                    self.assertEqual(result.reason, "fiber_gripper_contact")
                    advance(world)
                    self.assertTrue(task.update(world, .1).terminated)


if __name__ == "__main__":
    unittest.main()
