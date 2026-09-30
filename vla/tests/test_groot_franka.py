"""Franka flange forward kinematics used for GR00T's eef_9d (DROID cartesian_position convention)."""
import numpy as np
from scipy.spatial.transform import Rotation

from vla.models.groot.franka import droid_cartesian, flange_pose


def test_zero_configuration_puts_the_flange_above_the_base_pointing_down():
    pose = flange_pose(np.zeros(7))
    np.testing.assert_allclose(pose[:3, 3], [0.088, 0.0, 0.926], atol=1e-12)
    np.testing.assert_allclose(pose[:3, :3], np.diag([1.0, -1.0, -1.0]), atol=1e-12)


def test_first_joint_turns_the_arm_about_the_base_z_axis():
    np.testing.assert_allclose(flange_pose(np.r_[np.pi / 2, np.zeros(6)])[:3, 3], [0.0, 0.088, 0.926], atol=1e-12)


def test_droid_cartesian_is_position_and_extrinsic_xyz_euler():
    q = np.array([0.1, -0.5, 0.2, -2.0, 0.3, 1.8, 0.4])
    pose, cartesian = flange_pose(q), droid_cartesian(q)
    np.testing.assert_allclose(cartesian[:3], pose[:3, 3])
    np.testing.assert_allclose(Rotation.from_euler("xyz", cartesian[3:]).as_matrix(), pose[:3, :3], atol=1e-12)
