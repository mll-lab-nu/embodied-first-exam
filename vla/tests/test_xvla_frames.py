"""X-VLA RoboTwin2 <-> standard ee vectors: quaternion misread, per-arm base mapping, TCP offset, gripper."""
import numpy as np
from scipy.spatial.transform import Rotation

from vla.models.xvla.frames import base_transform, from_xvla, to_xvla

TOPOGYM = {"left": [-0.6, -0.02, 0.94, 0.0], "right": [0.33, -0.02, 0.94, 180.0]}
ROBOTWIN = {"left": [-0.297, -0.4195, 0.782, 91.146], "right": [0.3063, -0.4185, 0.781, 90.573]}
TRANSFORMS = [base_transform(TOPOGYM[arm], ROBOTWIN[arm]) for arm in ("left", "right")]
OFFSET = 0.12


def standard_arm(position, rotation, opening):
    matrix = rotation.as_matrix()
    return np.r_[position, matrix[:, 0], matrix[:, 1], opening]


def test_robotwin_home_rotation_gives_the_published_xvla_rot6d():
    # RoboTwin home: link6 = Rz(91.146 deg); X-VLA sees [1, 0, 0, 0.02, 0, 0.9998] (misread quaternion).
    home = Rotation.from_euler("z", 91.146, degrees=True)
    tcp = np.array([-0.2979, -0.3138, 0.942]) + OFFSET * home.as_matrix()[:, 0]
    arm = standard_arm(TRANSFORMS[0][0].T @ (tcp - TRANSFORMS[0][1]), Rotation.identity(), 1.0)
    proprio = to_xvla(np.r_[arm, arm], TRANSFORMS, OFFSET)
    np.testing.assert_allclose(proprio[:3], [-0.2979, -0.3138, 0.942], atol=1e-6)
    np.testing.assert_allclose(proprio[3:9], [1, 0, 0, 0.02, 0, 0.9998], atol=2e-4)
    assert proprio[9] == 0.0  # g = 1 - opening


def test_pose_relative_to_the_arm_base_is_kept():
    offset_in_base = np.array([0.3, 0.05, 0.1])
    left = standard_arm(np.array(TOPOGYM["left"][:3]) + offset_in_base, Rotation.identity(), 0.0)
    right_rotation = Rotation.from_euler("z", 180, degrees=True)
    right = standard_arm(np.array(TOPOGYM["right"][:3]) + right_rotation.apply(offset_in_base), right_rotation, 1.0)
    proprio = to_xvla(np.r_[left, right], TRANSFORMS, OFFSET)
    for arm, xvla in zip(("left", "right"), np.split(proprio, 2)):
        base = Rotation.from_euler("z", ROBOTWIN[arm][3], degrees=True)
        expected = np.array(ROBOTWIN[arm][:3]) + base.apply(offset_in_base - [OFFSET, 0, 0])
        np.testing.assert_allclose(xvla[:3], expected, atol=1e-9)
    assert (proprio[9], proprio[19]) == (1.0, 0.0)


def test_actions_invert_the_proprio_mapping():
    rng = np.random.default_rng(0)
    for rotations in Rotation.random(10, random_state=1).as_quat().reshape(5, 2, 4):
        ee = np.concatenate([standard_arm(rng.uniform(-0.5, 0.5, 3) + [0, 0, 1], Rotation.from_quat(q), opening)
                             for q, opening in zip(rotations, (0.0, 1.0))])
        back = from_xvla(to_xvla(ee, TRANSFORMS, OFFSET)[None], TRANSFORMS, OFFSET)
        assert back.shape == (1, 20) and back.dtype == np.float32
        np.testing.assert_allclose(back[0], ee, atol=1e-5)


def test_gripper_closes_above_the_official_threshold():
    proprio = to_xvla(np.tile(standard_arm(np.zeros(3), Rotation.identity(), 1.0), 2), TRANSFORMS, OFFSET)
    actions = np.stack([proprio, proprio])
    actions[:, [9, 19]] = [[0.69, 0.71], [0.71, 0.69]]
    openings = from_xvla(actions, TRANSFORMS, OFFSET)[:, [9, 19]]
    np.testing.assert_array_equal(openings, [[1.0, 0.0], [0.0, 1.0]])
