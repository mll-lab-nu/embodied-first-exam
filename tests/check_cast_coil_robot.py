"""Prevent false demo qualification and float32 inverse-kinematics regressions."""

import copy
import unittest
from pathlib import Path

from hydra import compose, initialize_config_dir
import numpy as np

from topogym.tasks.cast_coil.robot_archive import (
    CAMERAS,
    REQUIRED_PHASES,
    qualify_report,
)
from topogym.tasks.cast_coil.robot_plan import Kinematics
from topogym.tasks.cast_coil.robot_grasp import release_grasps


def completed_recording():
    return dict(
        success=True,
        complete=True,
        physics_steps=1000,
        bilateral_grasp_contact_step=20,
        grasp_assistance_active_at_end=False,
        grasp_constraints_remaining=[],
        release_evidence=dict(after=[]),
        released_body_displacement_during_retreat_m=[0.0, 0.0],
        final_finger_contact_links={"0": [], "1": []},
        live_object_pose_writes=False,
        live_robot_pose_writes=False,
        geometry_modified=False,
        camera_names=list(CAMERAS),
        video_frames=100,
        phases=[dict(name=name) for name in REQUIRED_PHASES],
        final_separation_m=0.078,
        minimum_sampled_sat_gap_m=0.0002,
        maximum_interpiece_penetration_m=0.0,
        maximum_forbidden_robot_penetration_m=0.0,
        maximum_cross_arm_penetration_m=0.0,
        final_speed_m_s=[0.0, 0.0],
        final_angular_speed_rad_s=[0.0, 0.0],
    )


class CastCoilRobotChecks(unittest.TestCase):
    def test_multiple_weld_release_avoids_non_tail_delete_kernel_bug(self):
        class Solver:
            def __init__(self):
                self.pairs = [(10, 100), (20, 200)]

            def get_weld_constraints(self, **kwargs):
                return dict(
                    link_a=np.array([[a for a, _ in self.pairs]]),
                    link_b=np.array([[b for _, b in self.pairs]]),
                )

            def delete_weld_constraint(self, a, b):
                # Reproduce the installed kernel: decrement count, without
                # copying the last record's object IDs into a removed slot.
                if (a, b) in self.pairs:
                    self.pairs.pop()

        solver = Solver()
        evidence = release_grasps(solver, [(10, 100), (20, 200)])
        self.assertEqual(evidence["deletion_order"], [[20, 200], [10, 100]])
        self.assertEqual(solver.pairs, [])

    def test_controller_release_flag_is_not_solver_release_evidence(self):
        bad = completed_recording()
        bad.pop("grasp_constraints_remaining")
        with self.assertRaises(ValueError):
            qualify_report(bad)

    def test_float32_simulator_state_remains_solvable_with_finite_differences(self):
        root = Path(__file__).resolve().parents[1]
        with initialize_config_dir(config_dir=str(root / "configs"), version_base=None):
            cfg = compose(config_name="cast_coil_aloha")
        kinematics = Kinematics(cfg.robot_control)
        kinematics.q = kinematics.q.astype(np.float32)
        start, rotation = kinematics.pose("left")
        error = kinematics.solve("left", start + [0.002, 0.003, 0.003], rotation)
        self.assertLess(error[0], 1e-6)
        self.assertLess(error[1], 1e-5)

    def test_complete_recording_requires_release_and_physical_execution(self):
        good = completed_recording()
        qualify_report(good)
        for overrides in (
            dict(physics_steps=0),
            dict(complete=False),
            dict(grasp_assistance_active_at_end=True),
            dict(live_object_pose_writes=True),
            dict(final_speed_m_s=[0.0, 0.1]),
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                qualify_report(dict(good, **overrides))

    def test_partial_cameras_or_skipped_task_phases_cannot_be_archived(self):
        for change in (
            dict(camera_names=["front_oblique"]),
            dict(video_frames=0),
            dict(phases=[dict(name="prototype_extract")]),
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                qualify_report(dict(completed_recording(), **change))

    def test_separation_does_not_excuse_earlier_collision(self):
        bad = copy.deepcopy(completed_recording())
        bad["minimum_sampled_sat_gap_m"] = -0.0001
        with self.assertRaises(ValueError):
            qualify_report(bad)


if __name__ == "__main__":
    unittest.main()
