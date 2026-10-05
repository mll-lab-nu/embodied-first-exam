"""Franka flange forward kinematics and GR00T's eef_9d built from the flange rotation itself."""
import numpy as np

from vla.models.groot.franka import eef_9d, flange_pose


def test_zero_configuration_puts_the_flange_above_the_base_pointing_down():
    pose = flange_pose(np.zeros(7))
    np.testing.assert_allclose(pose[:3, 3], [0.088, 0.0, 0.926], atol=1e-12)
    np.testing.assert_allclose(pose[:3, :3], np.diag([1.0, -1.0, -1.0]), atol=1e-12)


def test_first_joint_turns_the_arm_about_the_base_z_axis():
    np.testing.assert_allclose(flange_pose(np.r_[np.pi / 2, np.zeros(6)])[:3, 3], [0.0, 0.088, 0.926], atol=1e-12)


def test_eef_9d_is_the_flange_position_and_the_corrected_rotation_rows():
    # flange rotation diag(1, -1, -1) times GR00T's DROID correction [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]
    np.testing.assert_allclose(eef_9d(np.zeros(7)), [0.088, 0.0, 0.926, 0, 0, -1, 1, 0, 0], atol=1e-12)
