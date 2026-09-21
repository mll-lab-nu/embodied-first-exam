"""Real F3 failures must find a checked release path without relaxing IK."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from omegaconf import OmegaConf
import pytest
from scipy.spatial.transform import Rotation

from topogym.tasks.horseshoe_ring.physical_place import plan_release


def recorded_motion(name, *, adaptive=True):
    cases = json.loads((Path(__file__).parent/"fixtures/horseshoe_ring_release_v2.json").read_text())["cases"]
    item = cases[name]
    row = item["frame"]
    return SimpleNamespace(instance={} if adaptive else None,
        cfg=SimpleNamespace(robot_control=OmegaConf.create(item["robot_control"]), task=SimpleNamespace(scale=item["scale"])),
        mount=np.asarray(item["mount"]),
        robot=SimpleNamespace(get_qpos=lambda: np.asarray(row["qpos"])),
        task=SimpleNamespace(assembly=SimpleNamespace(template=item["template"]), bodies=row["bodies"],
            tabletop=SimpleNamespace(frames=SimpleNamespace(table_surface_origin=np.asarray(item["table_surface"])))),
        body_pose=lambda name: (np.asarray(row["bodies"][name]["pos"]),
            Rotation.from_quat(np.asarray(row["bodies"][name]["quat_wxyz"])[[1, 2, 3, 0]])))


@pytest.mark.parametrize("name", ["f3_first", "f3_retry"])
def test_recorded_failed_release_has_checked_alternative(name):
    with pytest.raises(RuntimeError, match="No checked horizontal ring release pose"):
        plan_release(recorded_motion(name, adaptive=False))
    plan = plan_release(recorded_motion(name))
    assert plan["release_destination_index"] == 1
    np.testing.assert_allclose(plan["release_center_world_m"][:2], [0., .1], atol=1e-12)
    assert np.isfinite(plan["arm_waypoints"]).all()
    assert len(plan["arm_waypoints"]) >= 2


def test_already_reachable_original_release_point_stays_first():
    old = plan_release(recorded_motion("f1_reference", adaptive=False))
    new = plan_release(recorded_motion("f1_reference"))
    assert new["release_destination_index"] == 0
    np.testing.assert_allclose(old["release_center_world_m"], new["release_center_world_m"], atol=1e-12)
    np.testing.assert_allclose(old["arm_waypoints"], new["arm_waypoints"], atol=1e-12)
