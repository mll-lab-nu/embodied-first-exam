"""Physical wooden supports and supported endpoint poses, in toy coordinates."""

import numpy as np
from scipy.spatial.transform import Rotation


def endpoint_pose(route, end):
    """Ring on its captive mount, handle gently inclined on a wooden saddle."""
    layout = route.layout
    _, q = route.pose(float(end))
    old = Rotation.from_quat(q[[1, 2, 3, 0]])
    x = old.apply([1, 0, 0])
    x[2] = 0
    x /= np.linalg.norm(x)
    if end:
        x = Rotation.from_euler("z", layout.rest_finish_yaw_deg, degrees=True).apply(x)
    pitch = np.deg2rad(layout.rest_handle_pitch_deg)
    horizontal = x.copy()
    x = horizontal * np.cos(pitch) + [0, 0, np.sin(pitch)]
    z = (-horizontal * np.sin(pitch) + [0, 0, np.cos(pitch)]) * (1 if end == 0 else -1)
    r = Rotation.from_matrix(np.column_stack([x, np.cross(z, x), z]))
    custom = bool(end and layout.rest_finish_quaternion_wxyz)
    if custom:
        r = Rotation.from_quat(
            np.array(layout.rest_finish_quaternion_wxyz)[[1, 2, 3, 0]]
        )
    p = route.rail[0 if end == 0 else -1].copy()
    p[2] = (
        layout.base_elevation_m
        + layout.base_size_m[2]
        + layout.mount_size_m[2]
        + layout.loop_tube_radius_m
        + layout.loop_radius_m * np.sin(pitch)
    )
    if custom:
        vertices = np.array(
            [a for a, _, _, role in layout.tool_capsules() if role == "loop"]
        )
        p[2] = (
            layout.base_elevation_m
            + layout.base_size_m[2]
            + layout.mount_size_m[2]
            + layout.loop_tube_radius_m
            - r.apply(vertices)[:, 2].min()
            + layout.finish_cradle_mount_clearance_m
        )
    return p, r


def support_spheres(route):
    """Rounded V seats support the oblique finish ring and neck against rolling."""
    layout = route.layout
    if not layout.supported_endpoints or not layout.rest_finish_quaternion_wxyz:
        return []
    p, r = endpoint_pose(route, 1)
    vertices = np.array(
        [a for a, _, _, role in layout.tool_capsules() if role == "loop"]
    )
    lowest = int(np.argmin(r.apply(vertices)[:, 2]))
    spheres = []

    def cradle(point, tangent, role, radius=0.003):
        normal = np.array([0.0, 0.0, 1.0]) - tangent * tangent[2]
        normal /= np.linalg.norm(normal)
        side = np.cross(tangent, normal)
        # Paired rounded jaws form a concave V instead of a balancing point.
        # Both contact normals face up, so the robot can lower into the seat.
        for sign in (-1, 1):
            direction = (normal + sign * side) / np.sqrt(2)
            centre = point - direction * (layout.loop_tube_radius_m + radius)
            spheres.append((centre, radius, role))

    for offset in (-10, 10):
        i = (lowest + offset) % len(vertices)
        a, b = r.apply(vertices[[i, (i + 1) % len(vertices)]]) + p
        tangent = (b - a) / np.linalg.norm(b - a)
        cradle((a + b) / 2, tangent, "ring_cradle")
    # The steep terminal orientation needs a neck rest outside the finger pads.
    # A rest beneath the handle itself lies in the descending jaw's swept volume.
    tangent = r.apply([1.0, 0.0, 0.0])
    if layout.finish_cradle_neck_pair:
        centre = p + tangent * (layout.loop_radius_m + 0.010)
        cradle(centre, tangent, "neck_cradle", radius=0.002)
    else:
        # The two ring V seats locate the ring sideways; one neck contact
        # supports its handle without an additional redundant V constraint.
        normal = np.array([0.0, 0.0, 1.0]) - tangent * tangent[2]
        normal /= np.linalg.norm(normal)
        centre = p + tangent * (layout.loop_radius_m + 0.008)
        spheres.append(
            (
                centre - normal * (layout.loop_tube_radius_m + 0.003),
                0.003,
                "neck_cradle",
            )
        )
    return spheres


def support_boxes(route):
    """Return exact box (centre, size, rotation, role) shared by assets and audits."""
    layout = route.layout
    elevation = layout.base_elevation_m
    x, y, _ = layout.base_size_m
    boxes = []
    if elevation:
        for sx in (-1, 1):
            for sy in (-1, 1):
                boxes.append(
                    (
                        np.array(
                            [sx * (x / 2 - 0.044), sy * (y / 2 - 0.044), elevation / 2]
                        ),
                        np.array([0.045, 0.045, elevation]),
                        Rotation.identity(),
                        "foot",
                    )
                )
    if layout.supported_endpoints:
        # Support the proximal end of the handle, leaving the grasp pads clear.
        deck = elevation + layout.base_size_m[2]
        for end in (0, 1):
            if end and layout.rest_finish_quaternion_wxyz:
                continue
            p, r = endpoint_pose(route, end)
            if layout.rest_handle_pitch_deg == 0 and not (
                end and layout.rest_finish_quaternion_wxyz
            ):
                # Keep existing horizontal-support assets reproducible.
                roll = np.deg2rad(layout.grip_flat_roll_deg)
                half_z = layout.grip_half_thickness_m / abs(
                    np.cos(roll)
                ) + 0.0015 * abs(np.tan(roll))
                height = p[2] - half_z - deck
                centre = p + r.apply(
                    [layout.loop_radius_m + layout.stem_length_m + 0.003, 0, 0]
                )
                centre[2] = deck + height / 2
                boxes.append(
                    (centre, np.array([0.006, 0.003, height]), r, "handle_saddle")
                )
            else:
                grip = r * Rotation.from_euler(
                    "x", layout.grip_flat_roll_deg, degrees=True
                )
                sign = -np.sign(grip.apply([0, 0, 1])[2])
                size = np.array([0.006, 0.003, 0.003])
                centre = p + grip.apply(
                    [
                        layout.loop_radius_m + layout.stem_length_m + 0.003,
                        0,
                        sign * (layout.grip_half_thickness_m + size[2] / 2),
                    ]
                )
                boxes.append((centre, size, grip, "handle_saddle"))
                height = (
                    centre[2]
                    - np.dot(abs(grip.as_matrix()[2]), size / 2)
                    - deck
                    + 0.001
                )
                yaw = Rotation.from_euler(
                    "z", np.arctan2(r.apply([1, 0, 0])[1], r.apply([1, 0, 0])[0])
                )
                root_xy = centre[:2].copy()
                root_z = deck
                reach = abs(root_xy) + abs(yaw.as_matrix()[:2, :2]) @ np.array(
                    [0.003, 0.0015]
                )
                # Near the chamfered edge, anchor the post into the lower tier;
                # otherwise a post whose bottom is at deck height would float.
                if np.any(reach > np.array(layout.base_size_m[:2]) / 2 - 0.012):
                    limit = np.array(layout.base_size_m[:2]) / 2 - 0.008
                    root_xy = np.clip(root_xy, -limit, limit)
                    root_z = elevation + 0.002
                    height += deck - root_z
                boxes.append(
                    (
                        np.r_[root_xy, root_z + height / 2],
                        np.array([0.006, 0.003, height]),
                        yaw,
                        "saddle_post",
                    )
                )
    for centre, radius, role in support_spheres(route):
        deck = elevation + layout.base_size_m[2]
        height = centre[2] - deck
        boxes.append(
            (
                np.r_[centre[:2], deck + height / 2],
                np.array([0.002, 0.002, height]),
                Rotation.identity(),
                role + "_post",
            )
        )
    return boxes


def fixture_boxes(route):
    layout = route.layout
    boxes = [
        (
            np.array([0.0, 0.0, layout.base_elevation_m + layout.base_size_m[2] / 2]),
            np.array(layout.base_size_m),
            Rotation.identity(),
            "deck",
        )
    ]
    boxes.extend(support_boxes(route))
    if layout.end_stop_shape == "block_mount":
        for a, _, _, role in route.fixed_capsules():
            if role == "stop":
                boxes.append(
                    (a, np.array(layout.mount_size_m), Rotation.identity(), "mount")
                )
    return boxes
