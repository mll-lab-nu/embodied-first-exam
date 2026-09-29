"""Scene-tier regression: real assets, unchanged rope and usable supported holes."""

import numpy as np
import pytest
import trimesh

from topogym.config.registry import task_definition, variation_registration
from topogym.assets.geometry.rope_threading import ThreadingLayout
from topogym.tasks.rope_threading.common import RopeThreadingTask


@pytest.fixture(scope="module")
def scenes(tmp_path_factory):
    root = tmp_path_factory.mktemp("threading_scenes")
    result = {}
    for tier in ("easy", "medium", "hard"):
        task = task_definition("rope_threading", tier)(seed=2)
        spec = task.declare(root/tier, .9196429)
        result[tier] = task, spec
    return result


def test_tiers_preserve_medium_identity_and_initial_rope(scenes):
    medium, baseline = scenes["medium"]
    assert medium.config == RopeThreadingTask.defaults
    assert medium.model_revision == "simulator_v1_fem_soft50_fine_v1"
    assert task_definition("rope_threading") is type(medium)
    assert medium.layout.rings() == ThreadingLayout(**medium.config["geometry"]).rings()
    assert len({task.instance_id for task, _ in scenes.values()}) == 3
    reference = next(e for e in baseline.entities if e.name == "rope")
    with np.load(reference.volume_path) as original:
        for task, spec in scenes.values():
            rope = next(e for e in spec.entities if e.name == "rope")
            assert rope.material == reference.material
            assert rope.position_m == reference.position_m
            assert rope.asset_path.read_bytes() == reference.asset_path.read_bytes()
            assert not rope.fixed and not spec.attachments
            assert not task.goal_complete
            with np.load(rope.volume_path) as volume:
                for key in ("rest", "spawn", "elements", "material_s_m", "centerline"):
                    np.testing.assert_array_equal(volume[key], original[key])
                for key in ("rest", "spawn"):
                    corners = volume[key][volume["elements"]]
                    assert np.all(np.linalg.det(corners[:, 1:]-corners[:, :1]) > 0)


@pytest.mark.parametrize("tier,count,diameter", [("easy", 2, .138), ("medium", 3, .138), ("hard", 3, .100)])
def test_scenes_have_open_supported_rings_and_no_initial_threading(scenes, tier, count, diameter):
    task, spec = scenes[tier]
    report = spec.metadata["geometry_report"]
    assert not report["initial_crossings"]
    assert report["minimum_fixture_gap_lower_bound_m"] > 0
    assert report["minimum_nonlocal_rope_surface_gap_m"] > 0
    assert task.layout.required_crossings() == [("R1", -1), ("R2", 1), ("R3", 1)][:count]
    assert len(spec.entities) == 1+3*count
    if tier == "easy":
        assert not list(spec.entities[0].asset_path.parent.glob("R3*"))
    baseline = scenes["medium"][0].layout.rings()
    for ring, original in zip(task.layout.rings(), baseline):
        assert ring["center_m"] == original["center_m"]
        assert ring["normal"] == original["normal"]
        assert ring["tube_radius_m"] == original["tube_radius_m"]
        assert 2*(ring["radius_m"]-ring["tube_radius_m"]) == pytest.approx(diameter)
        stand_top = task.layout.transform(ring["stand"]["position"])
        stand_top[2] += ring["stand"]["size"][1]
        rim = np.asarray(ring["center_m"])+ring["radius_m"]*np.asarray(ring["basis_u"])
        np.testing.assert_allclose(stand_top, rim, atol=1e-9)
        entity = next(e for e in spec.entities if e.name == ring["name"])
        assert entity.fixed and entity.morph_options["convexify"] is False
        mesh = trimesh.load(entity.asset_path, force="mesh", process=False)
        assert mesh.is_watertight and mesh.euler_number == 0
        center, normal = np.asarray(ring["center_m"]), np.asarray(ring["normal"])
        # The exported collision mesh must transmit a ray through its hole,
        # while blocking the same ray through the rim.
        ray_hits = mesh.ray.intersects_any([center-.2*normal, rim-.2*normal], [normal, normal])
        np.testing.assert_array_equal(ray_hits, [False, True])


@pytest.mark.parametrize("tier", ["easy", "hard"])
@pytest.mark.parametrize("geometry", [{"ring_ids": ["R1"]}, {"ring_inner_radius_m": .06}])
def test_scene_defining_geometry_cannot_silently_change(tier, geometry):
    with pytest.raises(ValueError, match="defines this setting"):
        task_definition("rope_threading", tier)({"geometry": geometry})
    row = variation_registration("rope_threading", tier)
    assert row["status"] == "integrated"
    assert row["model_revision"] == task_definition("rope_threading", tier).model_revision
