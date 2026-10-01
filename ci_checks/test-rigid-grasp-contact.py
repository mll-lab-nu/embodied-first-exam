#!/usr/bin/env python3
"""Synthetic contact and terminal regressions; no physical grasp qualification."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topogym.config.registry import task_definition
from topogym.config.scene import load_scene_config
from topogym.robot.description import describe_robot
from topogym.simulator.config import SimulatorConfig
from topogym.tasks.base import RigidTaskDefinition
from topogym.utils.grasp import GraspAssistConfig


class ContactTask(RigidTaskDefinition):
    task_id = "contact_regression"

    def evaluate_state(self, state):
        _, _, _, failure = self.rigid_measurements(state)
        return False, failure, {}


def fixture(robot_id="aloha"):
    description = describe_robot(load_scene_config(SimulatorConfig(
        task_id="horseshoe_ring", robot_id=robot_id, enable_rgb=False)).robot_control)
    names = {name for group in description.groups for name in (*group.grasp.finger_links, group.hand_link)}
    links = {name: SimpleNamespace(idx=i, name=name, is_fixed=False)
             for i, name in enumerate(sorted(names), 10)}
    robot = SimpleNamespace(links=list(links.values()), get_link=links.__getitem__)
    task = ContactTask()
    task.local_vertices = {name: np.zeros((1, 3)) for name in ("piece", "other", "fixed")}
    entities = {name: SimpleNamespace(links=[SimpleNamespace(idx=i, is_fixed=name == "fixed")])
                for name, i in (("piece", 1), ("other", 2), ("fixed", 3))}
    task.bind(dict(entities, robot=robot))
    task.bind_robot(description)
    return task, description, links


def state(rows=(), *, step=1, grasp=None, dtype=np.float64):
    result = dict(physics_step=step, bodies={name: dict(
        position_m=[0., 0., .1], quaternion_wxyz=[1., 0., 0., 0.],
        linear_velocity_m_s=[0., 0., 0.], angular_velocity_rad_s=[0., 0., 0.])
        for name in ("piece", "other", "fixed")}, contacts=dict(
            link_a=np.array([r[0] for r in rows], dtype=int),
            link_b=np.array([r[1] for r in rows], dtype=int),
            penetration=np.array([r[2] for r in rows], dtype=dtype),
            force=np.zeros((len(rows), 3))))
    if grasp is not None:
        result["grasp"] = grasp
    return result


class RigidGraspContactTests(unittest.TestCase):
    def setUp(self):
        self.task, self.description, self.links = fixture()
        self.hand = self.description.groups[0]
        self.f1, self.f2 = self.task._finger_links_by_hand[self.hand.name]
        self.housing = self.links[self.hand.hand_link].idx

    def failure(self, rows, **kwargs):
        return self.task.rigid_measurements(state(rows, **kwargs))[-1]

    def binding(self, *, phase="holding", target=1):
        return dict(hands={self.hand.name: dict(phase=phase, binding=dict(
            hand=self.hand.name, links=(self.housing, target)))})

    def test_native_bilateral_grasp_includes_exact_two_mm_for_both_robots(self):
        for robot_id in ("aloha", "panda_robotiq"):
            task, description, _ = fixture(robot_id)
            for group in description.groups:
                a, b = task._finger_links_by_hand[group.name]
                for depth in (.000979, .0015, .002):
                    for dtype in (np.float32, np.float64):
                        with self.subTest(robot=robot_id, hand=group.name, depth=depth, dtype=dtype):
                            # Reverse contact ordering and zero reaction forces are valid.
                            measured = state([(a, 1, depth), (1, b, 0.)], dtype=dtype)
                            self.assertIsNone(task.rigid_measurements(measured)[-1])

    def test_above_two_mm_terminates_and_latches_failure(self):
        result = self.task.update(state([(self.f1, 1, .002001), (self.f2, 1, .0001)]), .01)
        self.assertTrue(result.terminated)
        self.assertFalse(result.task_success)
        self.assertEqual(result.reason, "Held finger contact penetration exceeded 2 mm")
        self.assertEqual(self.task.update(state(step=2), .01), result)

    def test_one_to_two_mm_grasp_does_not_end_episode(self):
        result = self.task.update(state([(self.f1, 1, .0015), (self.f2, 1, .0001)]), .01)
        self.assertFalse(result.terminated)
        self.assertIsNone(result.reason)

    def test_other_contacts_keep_one_mm_even_while_holding(self):
        held = [(self.f1, 1, .0015), (self.f2, 1, .0001)]
        for other in (2, 3, self.housing, 999):  # piece, fixed fixture, housing, table/arm
            for a, b in ((1, other), (other, 1)):
                for dtype in (np.float32, np.float64):
                    with self.subTest(pair=(a, b), dtype=dtype):
                        self.assertIsNone(self.failure([*held, (a, b, .001)], dtype=dtype))
                        self.assertEqual(self.failure([*held, (a, b, .001001)], dtype=dtype),
                                         "Task contact penetration exceeded 1 mm")

    def test_no_grasp_from_one_finger_different_pieces_or_different_hands(self):
        other_hand = self.description.groups[1]
        other_finger = self.task._finger_links_by_hand[other_hand.name][1]
        cases = [
            [(self.f1, 1, .0015)],
            [(self.f1, 1, .0015), (self.f1, 1, .0001)],
            [(self.f1, 1, .0015), (self.f2, 2, .0001)],
            [(self.f1, 1, .0015), (other_finger, 1, .0001)],
            [(self.f1, 1, .0015), (self.f2, 1, -.0001)],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertEqual(self.failure(rows), "Task contact penetration exceeded 1 mm")

    def test_fixed_task_parts_never_get_grasp_allowance(self):
        self.assertEqual(self.failure([(self.f1, 3, .0015), (self.f2, 3, 0.)]),
                         "Task contact penetration exceeded 1 mm")
        self.assertEqual(self.failure([(self.f1, 3, .0015)], grasp=self.binding(target=3)),
                         "Task contact penetration exceeded 1 mm")

    def test_live_assist_binding_only_relaxes_its_own_hand_and_target(self):
        for phase in ("registered", "holding"):
            grasp = self.binding(phase=phase)
            self.assertIsNone(self.failure([(self.f1, 1, .002)], grasp=grasp))
            self.assertEqual(self.failure([(self.f1, 1, .002001)], grasp=grasp),
                             "Held finger contact penetration exceeded 2 mm")
            self.assertEqual(self.failure([(self.f1, 2, .0015)], grasp=grasp),
                             "Task contact penetration exceeded 1 mm")
            other_finger = self.task._finger_links_by_hand[self.description.groups[1].name][0]
            self.assertEqual(self.failure([(other_finger, 1, .0015)], grasp=grasp),
                             "Task contact penetration exceeded 1 mm")

    def test_released_or_lost_assist_cannot_relax_contact(self):
        for phase in ("idle", "qualifying", "lost"):
            self.assertEqual(self.failure([(self.f1, 1, .0015)], grasp=self.binding(phase=phase)),
                             "Task contact penetration exceeded 1 mm")
        self.assertEqual(self.failure([(self.f1, 1, .0015)], grasp=dict(active=True)),
                         "Task contact penetration exceeded 1 mm")

    def test_holding_is_recomputed_without_accumulating_contacts(self):
        first = state([(self.f1, 1, .0015), (self.f2, 1, .0001)])
        self.assertFalse(self.task.update(first, .01).terminated)
        saved = self.task.get_state()
        result = self.task.update(state([(self.f1, 1, .0015)], step=2), .01)
        self.assertTrue(result.terminated)
        self.task.set_state(saved)
        self.assertFalse(self.task.update(state(step=2), .01).terminated)

    def test_empty_unrelated_and_unbound_contacts(self):
        self.assertIsNone(self.failure([]))
        self.assertIsNone(self.failure([(self.f1, self.f2, .003)]))
        self.task.bind_robot(SimpleNamespace(groups=()))
        self.assertEqual(self.failure([(self.f1, 1, .0015), (self.f2, 1, .0001)]),
                         "Task contact penetration exceeded 1 mm")

    def test_contact_checks_do_not_mutate_the_grasp_state(self):
        grasp = self.binding()
        original = deepcopy(grasp)
        self.failure([(self.f1, 1, .0015)], grasp=grasp)
        self.assertEqual(grasp, original)

    def test_revisions_metadata_and_assist_default_are_consistent(self):
        old = dict(horseshoe_ring="placement_region_v2_default_success",
                   interlocked_claws="placement_region_v2_default_success",
                   hedgehog_in_cage="hedgehog_placement_v3_default_success",
                   cast_keyhole="cast_keyhole_placement_v3_default_success", cast_coil="release_settling_v1")
        for name, revision in old.items():
            for tier in ("easy", "medium", "hard"):
                with self.subTest(task=name, tier=tier):
                    cls = task_definition(name, tier)
                    task = cls()
                    # Placement metadata normally gets these during scene declaration.
                    task.placement_targets, task.placement_remainder = ("piece",), ("other",)
                    limits = task.terminal_metadata()["contact_penetration"]
                    self.assertEqual(limits["held_finger_contacts_m"], GraspAssistConfig().max_penetration_m)
                    self.assertEqual(limits["other_contacts_m"], .001)
                    text = task.public_instruction()
                    self.assertIn("at most 2 mm", text)
                    self.assertIn("at most 1 mm", text)
                    self.assertIn("both fingers of the same hand", text)
                    with patch.object(cls, "terminal_revision", revision):
                        saved = cls().get_state()
                    with self.assertRaisesRegex(ValueError, "different task, instance or schema"):
                        task.set_state(saved)


if __name__ == "__main__":
    unittest.main()
