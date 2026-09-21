"""Physical wooden supports and supported endpoint poses, in toy coordinates."""

import numpy as np
from scipy.spatial.transform import Rotation


def endpoint_pose(route, end):
    """Horizontal ring on its captive mount, handle on a narrow wooden saddle."""
    layout = route.layout
    _, q = route.pose(float(end))
    old = Rotation.from_quat(q[[1, 2, 3, 0]])
    x = old.apply([1, 0, 0])
    x[2] = 0
    x /= np.linalg.norm(x)
    z = np.array([0., 0., 1. if end == 0 else -1.])
    r = Rotation.from_matrix(np.column_stack([x, np.cross(z, x), z]))
    p = route.rail[0 if end == 0 else -1].copy()
    p[2] = (layout.base_elevation_m + layout.base_size_m[2]
            + layout.mount_size_m[2] + layout.loop_tube_radius_m)
    return p, r


def support_boxes(route):
    """Return exact box (centre, size, rotation, role) shared by assets and audits."""
    layout = route.layout
    elevation = layout.base_elevation_m
    x, y, _ = layout.base_size_m
    boxes = []
    if elevation:
        for sx in (-1, 1):
            for sy in (-1, 1):
                boxes.append((np.array([sx * (x / 2 - .044), sy * (y / 2 - .044),
                                        elevation / 2]),
                              np.array([.045, .045, elevation]), Rotation.identity(), "foot"))
    if layout.supported_endpoints:
        # Support the proximal end of the handle, leaving the grasp pads clear.
        roll = np.deg2rad(layout.grip_flat_roll_deg)
        half_width = .0015
        half_z = layout.grip_half_thickness_m / abs(np.cos(roll)) + half_width * abs(np.tan(roll))
        deck = elevation + layout.base_size_m[2]
        for end in (0, 1):
            p, r = endpoint_pose(route, end)
            height = p[2] - half_z - deck
            centre = p + r.apply([layout.loop_radius_m + layout.stem_length_m + .003, 0, 0])
            centre[2] = deck + height / 2
            boxes.append((centre, np.array([.006, 2 * half_width, height]), r, "handle_saddle"))
    return boxes


def fixture_boxes(route):
    layout = route.layout
    boxes = [(np.array([0., 0., layout.base_elevation_m + layout.base_size_m[2] / 2]),
              np.array(layout.base_size_m), Rotation.identity(), "deck")]
    boxes.extend(support_boxes(route))
    if layout.end_stop_shape == "block_mount":
        for a, _, _, role in route.fixed_capsules():
            if role == "stop":
                boxes.append((a, np.array(layout.mount_size_m), Rotation.identity(), "mount"))
    return boxes
