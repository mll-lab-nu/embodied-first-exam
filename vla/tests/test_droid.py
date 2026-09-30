"""DROID joint convention on the TopoGym Panda: the Robotiq mount differs by 45 deg of joint 7."""
from importlib.util import find_spec
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from topogym.assets.robot import build_robotiq_panda
from vla.models.droid import WRIST_OFFSET_RAD, from_droid_joints, to_droid_joints


def test_topogym_mounts_the_robotiq_on_the_hand_frame_45_degrees_from_the_flange():
    source = Path(find_spec("genesis").origin).parent / "assets/xml/franka_emika_panda/panda.xml"
    model = ET.parse(build_robotiq_panda(source)).getroot()
    w, x, y, z = map(float, model.find(".//body[@name='tool_mount']").get("quat").split())
    assert Rotation.from_quat([x, y, z, w]).as_euler("xyz") == pytest.approx([0.0, 0.0, -WRIST_OFFSET_RAD])
    assert model.find(".//body[@name='r85_base']").get("quat") == "1 0 0 0"


def test_joint_7_shifts_by_the_mount_offset_and_back():
    q = np.array([0.1, 0.2, 0.3, -2.0, 0.5, 1.8, -np.pi / 4], np.float32)
    droid = to_droid_joints(q)
    np.testing.assert_allclose(droid, np.r_[q[:6], -np.pi / 2], atol=1e-6)
    chunk = np.stack([droid, droid])
    np.testing.assert_allclose(from_droid_joints(chunk), np.stack([q, q]), atol=1e-6)
    assert droid.dtype == np.float32 and from_droid_joints(chunk).dtype == np.float32
