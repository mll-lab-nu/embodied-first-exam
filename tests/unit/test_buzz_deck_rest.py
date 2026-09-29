"""Actual endpoint clearance and direct-deck support for the new Buzz scenes."""
from dataclasses import replace

import numpy as np
import pytest
import trimesh

from topogym.config.registry import task_definition
from topogym.assets.geometry.buzz_wire_3d import (
    SpatialWire, endpoint_pose, support_boxes, support_spheres, capsule_mesh,
)


@pytest.mark.parametrize("tier", ("easy", "medium", "hard"))
def test_connectors_pass_through_ring_and_both_ends_rest_on_deck(tier):
    layout = task_definition("buzz_wire_3d", tier)(seed=0).build_layout()
    route = SpatialWire(layout)
    # Check real mesh distance, including the polygonal ring, while moving the
    # whole connector through its aperture. The old 30 mm mount fails this.
    ring = trimesh.util.concatenate([
        capsule_mesh(a, b, r) for a, b, r, part in layout.tool_capsules()
        if part == "loop"
    ])
    query = trimesh.collision.CollisionManager()
    query.add_object("ring", ring)
    for z in np.linspace(-.025, .025, 51):
        connector = trimesh.creation.box(layout.mount_size_m)
        connector.apply_translation([0., 0., z])
        assert not query.in_collision_single(connector)
        assert query.min_distance_single(connector) > .007
    assert [box[3] for box in support_boxes(route)] == ["foot"] * 4
    assert not support_spheres(route)
    grip = trimesh.creation.box([
        layout.grip_length_m, 2 * layout.grip_radius_m,
        2 * layout.grip_half_thickness_m,
    ])
    grip.apply_translation([
        layout.loop_radius_m + layout.stem_length_m + layout.grip_length_m / 2,
        0., 0.,
    ])
    deck = layout.base_elevation_m + layout.base_size_m[2]
    for end in (0, 1):
        p, r = endpoint_pose(route, end)
        ring_v = r.apply(ring.vertices) + p
        grip_v = r.apply(grip.vertices) + p
        assert 0 <= ring_v[:, 2].min() - deck < .0001
        assert 0 <= grip_v[:, 2].min() - deck < .0001
        assert np.degrees(np.arccos(r.apply([0, 0, 1])[2])) < 3
        vertices = np.vstack([ring_v, grip_v])
        assert np.all(abs(vertices[:, :2]) < np.asarray(layout.base_size_m[:2]) / 2 - .011)
        # The metal endpoint is embedded in the slim connection; no floating
        # metal line above a cosmetically shrunken block.
        assert deck < route.rail[0 if end == 0 else -1, 2] < deck + layout.mount_size_m[2]


def test_deck_mode_rejects_old_blocking_mount():
    layout = task_definition("buzz_wire_3d", "medium")(seed=0).build_layout()
    with pytest.raises(ValueError, match="pass through"):
        replace(layout, mount_size_m=(.030, .030, .012), end_stop_radius_m=.025).validate()
