#!/usr/bin/env python3
"""Variant registration, runtime assets and terminal counterexamples; no physics."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.config.registry import task_definition, variation_registration
from topogym.assets.geometry.cast_coil_simplified import SimplifiedCoilAssembly
from topogym.planning.cast_coil.policy import variant_reference
from topogym.planning.cast_coil.simplified_policy import SimplifiedCoilPolicy
from topogym.tasks.cast_coil.common import recommended_grasp_assist

spec = importlib.util.spec_from_file_location("coil_geometry_checks", ROOT/"ci_checks/test-cast-coil-simplifications.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def fixture(level, assembled=False):
    task = task_definition("cast_coil", level)(seed=0)
    with tempfile.TemporaryDirectory() as folder:
        spec = task.declare(Path(folder), .75)
    task._task_link_indices = {31, 32}
    task._robot_link_indices = {100}
    task._movable_task_link_indices = {31, 32}
    task._finger_links_by_hand = {}
    state = dict(physics_step=0, assist_active=False, bodies={},
        contacts=dict(link_a=[], link_b=[], penetration=[], force=np.zeros((0, 3))))
    for entity in spec.entities:
        state["bodies"][entity.name] = dict(position_m=np.array(entity.position_m),
            quaternion_wxyz=np.array(entity.quaternion_wxyz), linear_velocity_m_s=np.zeros(3),
            angular_velocity_rad_s=np.zeros(3))
    if assembled:
        gold, silver = (state["bodies"][name] for name in ("coil_gold", "coil_silver"))
        r = Rotation.from_quat(gold["quaternion_wxyz"][[1, 2, 3, 0]])
        silver["quaternion_wxyz"] = gold["quaternion_wxyz"].copy()
        silver["position_m"] = gold["position_m"]+r.apply(task.body_origins["coil_silver"]-task.body_origins["coil_gold"])
    refresh(task, state, 0)
    task.initialize(state)
    return task, state


def refresh(task, state, step):
    state["physics_step"] = step
    bounds = {}
    for name, body in state["bodies"].items():
        r = Rotation.from_quat(body["quaternion_wxyz"][[1, 2, 3, 0]])
        v = r.apply(task.local_vertices[name])+body["position_m"]
        bounds[name] = np.array([[v.min(0), v.max(0)]])
    state["release_geometry"] = dict(schema_version=1, physics_step=step, complete=True,
        robot_present=True, robot_bounds_m=[[[5., 5., 5.], [6., 6., 6.]]], target_bounds_m=bounds)


class CoilVariantTests(unittest.TestCase):
    def test_cube_clears_actual_aloha_fingertip_aperture(self):
        # Rail displacement includes the custom finger's inward overhang.
        # Derive the usable aperture from the shipped robot, not 2*0.037.
        root = ET.parse(ROOT/"assets/robots/aloha/aloha.xml").getroot()
        base = root.find(".//body[@name='left/gripper_base']")
        turn = Rotation.from_euler("XYZ", np.fromstring(base.get("euler"), sep=" "))
        sphere_radius = float(root.find(".//default[@class='sphere_collision']/geom").get("size"))
        pads = []
        for name in ("left_finger_link", "right_finger_link"):
            body = base.find(f"body[@name='left/{name}']")
            q = np.fromstring(body.get("quat"), sep=" ")
            r = Rotation.from_quat(q[[1, 2, 3, 0]])
            p = np.fromstring(body.get("pos"), sep=" ")
            pads.append([turn.apply(p+r.apply(np.fromstring(g.get("pos"), sep=" ")+[0., 0., -.037]))
                         for g in body.findall("geom[@class='sphere_collision']")])
        aperture = min(p[1] for p in pads[1])-max(p[1] for p in pads[0])-2*sphere_radius
        for level in ("very_easy", "easier"):
            edge = task_definition("cast_coil", level)().geometry()["parameters"]["edge_mm"]*.001
            self.assertGreater(aperture-edge, .004)

    def test_public_goal_describes_cube_without_oracle_moves(self):
        for level in ("very_easy", "easier"):
            task = task_definition("cast_coil", level)()
            text = task.public_instruction()
            self.assertIn("cube with flush outer faces", text)
            self.assertIn("0.5 s", text)
            self.assertNotIn("9 mm", text)

    def test_explicit_entries_keep_original_seed_pool(self):
        self.assertEqual(variation_registration("cast_coil")["variation_id"], "cast_coil_easy")
        for seed in range(9):
            self.assertEqual(variation_registration("cast_coil", "seeded", seed)["difficulty"],
                             ("easy", "medium", "hard")[seed % 3])
        for level in ("very_easy", "easier"):
            self.assertEqual(variation_registration("cast_coil", level)["pool"], "experimental")
            self.assertIs(task_definition("cast_coil", level), task_definition("cast_coil", "cast_coil_"+level))

    def test_resource_identity_and_uniform_scale(self):
        for level in ("very_easy", "easier"):
            task = task_definition("cast_coil", level)()
            self.assertEqual(task.instance_id, task_definition("cast_coil", level)().instance_id)
            self.assertNotEqual(task.instance_id, task_definition("cast_coil", level)(seed=1).instance_id)
            self.assertIn(task.geometry_resource, task.resource_hashes)
            actual, _ = variant_reference(level)
            for scaled, original in zip(actual.bodies, SimplifiedCoilAssembly(level).bodies):
                np.testing.assert_allclose(scaled.visual.bounds, original.visual.bounds*.5, atol=1e-12)

    def test_scaled_route_is_continuously_clear_and_uses_expected_moves(self):
        for level in ("very_easy", "easier"):
            assembly, route = variant_reference(level)
            self.assertEqual(len(route), 1 if level == "very_easy" else 2)
            gold, silver = (b.boxes for b in assembly.bodies)
            for motion in route:
                r0, t0 = motion.pose(0.)
                r1, t1 = motion.pose(1.)
                np.testing.assert_allclose(r0, r1)
                self.assertIsNone(checks.translation_collision(gold, silver, t0, t1, .00015))
            if level == "easier":
                self.assertAlmostEqual(route[0].pose(1.)[1][1], .009)
                self.assertIsNotNone(checks.translation_collision(gold, silver, [.04, 0., 0.], [0., 0., 0.]))

    def test_external_grasps_match_runtime_com_frames(self):
        for level in ("very_easy", "easier"):
            task, state = fixture(level)
            policy = SimplifiedCoilPolicy(body_origins=task.body_origins, variant=level)
            policy.obs = dict(privileged=dict(world=state))
            targets = policy.grasp_targets(policy.bodies())
            regions = {t.entity: t for t in recommended_grasp_assist(level).targets}
            for side, name in (("right", "coil_gold"), ("left", "coil_silver")):
                body = state["bodies"][name]
                r = Rotation.from_quat(body["quaternion_wxyz"][[1, 2, 3, 0]])
                expected = body["position_m"]+r.apply(regions[name].center_m)
                tcp, turn = targets[side]
                np.testing.assert_allclose(tcp-turn.apply([-.01381, 0., .00055]), expected, atol=1e-12)

    def test_initial_state_and_partial_assembly_do_not_succeed(self):
        for level in ("very_easy", "easier"):
            task, state = fixture(level)
            self.assertFalse(task.evaluate_state(state)[0])
            self.assertFalse(task.result.task_success)
            for offset in ([.004, 0., 0.], [0., .0108, 0.]):
                task, state = fixture(level, True)
                state["bodies"]["coil_silver"]["position_m"] += offset
                self.assertFalse(task.evaluate_state(state)[0])

    def test_success_requires_release_clearance_quiet_and_full_window(self):
        for level in ("very_easy", "easier"):
            for mode in ("valid", "held", "moving", "hovering", "hand_near"):
                with self.subTest(level=level, mode=mode):
                    task, state = fixture(level, True)
                    if mode == "held": state["assist_active"] = True
                    if mode == "moving": state["bodies"]["coil_silver"]["linear_velocity_m_s"][0] = .01
                    if mode == "hovering":
                        for body in state["bodies"].values(): body["position_m"][2] += .03
                    for step in range(1, 7):
                        refresh(task, state, step)
                        if mode == "hand_near":
                            state["release_geometry"]["robot_bounds_m"] = state["release_geometry"]["target_bounds_m"]["coil_gold"]
                        task.update(state, .1)
                        if step < 6: self.assertFalse(task.result.task_success)
                    self.assertEqual(task.result.task_success, mode == "valid")

    def test_original_three_routes_still_resolve(self):
        for level, count in (("easy", 3), ("medium", 3), ("hard", 5)):
            assembly, route = variant_reference(level)
            self.assertFalse(hasattr(assembly, "record"))
            self.assertEqual(len(route), count)


if __name__ == "__main__":
    unittest.main()
