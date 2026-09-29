from __future__ import annotations

"""A supported spatial steady-hand toy and a constructive tool-path witness.

Lengths are metres. Coordinates are relative to the bottom centre of the base.
Collision solids and clearance covers are generated from the same capsules.
"""


from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation, Slerp
import trimesh
from topogym.utils.geometry.rigid_geometry import cylinder_between, primitive, vector_text
import yaml
from scipy.spatial.transform import Rotation
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals
from topogym.assets.surfaces import wood_visual
from topogym.assets.library import resource_path




@dataclass(frozen=True)
class BuzzWireLayout:
    template_id: str = "spatial_maze_v2"
    authored_controls_m: tuple = ()
    authored_section_ends: tuple = ()
    orientation_knots_wxyz: tuple = ()
    center_offset_knots_m: tuple = ()
    base_size_m: tuple = (1.18, 0.82, 0.045)
    spiral_exit_roll_deg: float = 90.0
    spiral_exit_roll_start: float = 0.90
    spiral_exit_roll_end: float = 0.94
    spiral_normal_tilt_deg: float = 0.0
    normal_tilt_knots: tuple = ()
    clearance_cover_m: float = 0.0015
    middle_handle_roll_deg: float = 0.0
    upright_handle_pitch_deg: float = 0.0
    horizontal_scale: float = 1.0
    depth_scale: float = 1.0
    height_scale: float = 1.0
    vertical_valley_lift_m: float = 0.0
    wire_radius_m: float = 0.0035
    loop_radius_m: float = 0.026
    loop_tube_radius_m: float = 0.003
    loop_segments: int = 64
    stem_length_m: float = 0.038
    grip_length_m: float = 0.070
    grip_radius_m: float = 0.009
    grip_shape: str = "capsule"
    grip_half_thickness_m: float = 0.005
    grip_flat_roll_deg: float = 0.0
    end_stop_radius_m: float = 0.033
    end_stop_shape: str = "sphere"
    end_stop_thickness_m: float = 0.004
    rail_segment_m: float = 0.008
    witness_step_m: float = 0.002
    end_reserve_m: float = 0.10
    finish: str = "legacy"
    post_radius_m: float = 0.0
    post_height_m: float = 0.0
    mount_size_m: tuple = (0.030, 0.030, 0.014)
    # Raise the deck on wooden feet, independently of the authored maze bends.
    base_elevation_m: float = 0.0
    route_elevation_m: float = 0.0
    supported_endpoints: bool = False
    endpoint_support_part: str = "handle"
    rest_handle_pitch_deg: float = 0.0
    rest_finish_yaw_deg: float = 0.0
    rest_finish_quaternion_wxyz: tuple = ()
    finish_cradle_mount_clearance_m: float = 0.0
    finish_cradle_neck_pair: bool = True

    def validate(self):
        if self.endpoint_support_part not in {"handle", "stem", "deck"}:
            raise ValueError("Endpoint support part must be handle or stem")
        if not np.isfinite(self.route_elevation_m):
            raise ValueError("route_elevation_m must be finite")
        if (
            not np.isfinite(self.finish_cradle_mount_clearance_m)
            or not 0 <= self.finish_cradle_mount_clearance_m <= 0.005
        ):
            raise ValueError(
                "Finish cradle mount clearance must be between zero and 5 mm"
            )
        if self.rest_finish_quaternion_wxyz:
            q = np.asarray(self.rest_finish_quaternion_wxyz, dtype=float)
            if (
                q.shape != (4,)
                or not np.isfinite(q).all()
                or abs(np.linalg.norm(q) - 1) > 1e-6
            ):
                raise ValueError("Finish cradle requires a unit wxyz quaternion")
        if (
            not np.isfinite(self.rest_finish_yaw_deg)
            or abs(self.rest_finish_yaw_deg) > 180
        ):
            raise ValueError("Finish rest yaw must be within 180 degrees")
        if (
            not np.isfinite(self.rest_handle_pitch_deg)
            or not 0 <= self.rest_handle_pitch_deg <= 30
        ):
            raise ValueError("Resting handle pitch must be between zero and 30 degrees")
        if (
            not np.isfinite(self.base_elevation_m)
            or not 0 <= self.base_elevation_m <= 0.15
        ):
            raise ValueError("Deck elevation must be between zero and 150 mm")
        if self.supported_endpoints and (
            self.finish != "toy_wood_copper" or self.end_stop_shape != "block_mount"
        ):
            raise ValueError(
                "Supported endpoints require the wooden toy and block mounts"
            )
        if self.finish not in {"legacy", "wood_metal", "toy_wood_copper"}:
            raise ValueError("Unknown buzz-wire finish")
        if not np.isfinite([self.post_radius_m, self.post_height_m]).all() or (
            self.post_radius_m < 0
            or self.post_height_m < 0
            or (self.post_radius_m > 0) != (self.post_height_m > 0)
            or (self.post_radius_m > 0 and self.post_height_m < 2 * self.post_radius_m)
        ):
            raise ValueError("Wood posts need a positive radius and height >= diameter")
        if self.end_stop_shape not in {"sphere", "flat_finish", "block_mount"}:
            raise ValueError("Unknown end stop shape")
        if self.end_stop_shape == "block_mount":
            size = np.asarray(self.mount_size_m, dtype=float)
            if (
                size.shape != (3,)
                or not np.isfinite(size).all()
                or min(size) <= 0
                or np.linalg.norm(size / 2) > self.end_stop_radius_m
                or self.post_radius_m != 0
            ):
                raise ValueError(
                    "Block mounts must be covered and replace round posts"
                )
            inner = self.loop_radius_m - self.loop_tube_radius_m
            if self.endpoint_support_part == "deck":
                if np.linalg.norm(size[:2] / 2) + .001 >= inner:
                    raise ValueError("Deck-rest connectors must pass through the ring with clearance")
                if self.grip_shape != "box" or self.grip_flat_roll_deg != 0:
                    raise ValueError("Deck rest requires the rectangular grip's broad face downward")
            elif min(size[:2]) / 2 <= inner:
                raise ValueError("Raised saddle mounts must remain captive")
        if self.end_stop_shape == "flat_finish":
            radius = self.end_stop_radius_m - 0.0005
            if (
                not np.isfinite(self.end_stop_thickness_m)
                or self.end_stop_thickness_m <= 0
                or np.hypot(radius, self.end_stop_thickness_m / 2)
                > self.end_stop_radius_m
                or radius <= self.loop_radius_m - self.loop_tube_radius_m
            ):
                raise ValueError(
                    "Flat finish must remain captive and inside the conservative stop sphere"
                )
        if self.center_offset_knots_m:
            offsets = np.asarray(self.center_offset_knots_m, dtype=float)
            if (
                offsets.ndim != 2
                or offsets.shape[1] != 4
                or len(offsets) < 2
                or not np.isfinite(offsets).all()
                or offsets[0, 0] != 0
                or offsets[-1, 0] != 1
                or np.any(np.diff(offsets[:, 0]) <= 0)
                or np.any(np.linalg.norm(offsets[:, 1:], axis=1) > 0.015)
            ):
                raise ValueError(
                    "Center offsets require ordered progress and finite offsets within 15 mm"
                )
        if self.template_id == "authored_multistage_v1":
            points = np.asarray(self.authored_controls_m, dtype=float)
            if (
                points.ndim != 2
                or points.shape[1] != 3
                or len(points) < 4
                or not np.isfinite(points).all()
                or np.any(np.linalg.norm(np.diff(points, axis=0), axis=1) < 1e-8)
            ):
                raise ValueError("Authored controls must be finite distinct 3D points")
            if any(
                len(row) != 2
                or not isinstance(row[0], str)
                or not row[0]
                or not isinstance(row[1], (int, np.integer))
                for row in self.authored_section_ends
            ):
                raise ValueError("Authored stages need names and integer indices")
            names = [row[0] for row in self.authored_section_ends]
            if len(set(names)) != len(names):
                raise ValueError("Authored stage names must be unique")
            indices = [int(row[1]) for row in self.authored_section_ends]
            if (
                not indices
                or indices != sorted(set(indices))
                or indices[0] < 1
                or indices[-1] >= len(points)
            ):
                raise ValueError(
                    "Authored stage ends must be ordered valid control indices"
                )
        if self.orientation_knots_wxyz:
            knots = np.asarray(self.orientation_knots_wxyz, dtype=float)
            if (
                knots.ndim != 2
                or knots.shape[1] != 5
                or len(knots) < 2
                or not np.isfinite(knots).all()
                or knots[0, 0] != 0
                or knots[-1, 0] != 1
                or np.any(np.diff(knots[:, 0]) <= 0)
                or not np.allclose(np.linalg.norm(knots[:, 1:], axis=1), 1, atol=1e-6)
            ):
                raise ValueError(
                    "Orientation knots must contain ordered progress and unit wxyz quaternions"
                )
        if self.grip_shape not in {"capsule", "box"} or not np.isfinite(
            self.grip_flat_roll_deg
        ):
            raise ValueError("Grip must be a capsule or an oriented box")
        if (
            not np.isfinite(self.upright_handle_pitch_deg)
            or not 0 <= self.upright_handle_pitch_deg <= 60
        ):
            raise ValueError("Upright handle pitch must be in [0, 60] degrees")
        if (
            not np.isfinite(self.middle_handle_roll_deg)
            or abs(self.middle_handle_roll_deg) > 60
        ):
            raise ValueError("Middle handle roll must be finite and within 60 degrees")
        if (
            not np.isfinite(self.clearance_cover_m)
            or not 0 < self.clearance_cover_m <= 0.0015
        ):
            raise ValueError("Clearance cover must be positive and at most 1.5 mm")
        if self.normal_tilt_knots:
            knots = np.asarray(self.normal_tilt_knots, dtype=float)
            if (
                knots.ndim != 2
                or knots.shape[1] != 2
                or len(knots) < 2
                or not np.isfinite(knots).all()
                or knots[0, 0] != 0
                or knots[-1, 0] != 1
                or np.any(np.diff(knots[:, 0]) <= 0)
                or np.max(abs(knots[:, 1])) > 75
            ):
                raise ValueError(
                    "Normal tilt knots must span [0, 1] in order, within 75 degrees"
                )
        if not 0 <= self.spiral_exit_roll_start < self.spiral_exit_roll_end <= 1:
            raise ValueError("Exit roll interval must lie in [0, 1]")
        if (
            not np.isfinite(self.spiral_normal_tilt_deg)
            or abs(self.spiral_normal_tilt_deg) > 60
        ):
            raise ValueError("Spiral ring tilt must be finite and within 60 degrees")
        if (
            not np.isfinite(self.vertical_valley_lift_m)
            or self.height_scale <= 0
            or not 0 <= self.vertical_valley_lift_m / self.height_scale <= 0.22
        ):
            raise ValueError(
                "Valley lift must preserve the order of the vertical folds"
            )
        if self.template_id not in {
            "spatial_slalom_v1",
            "spatial_maze_v2",
            "spatial_maze_robot_v3",
            "authored_multistage_v1",
        }:
            raise ValueError("Unknown spatial wire template")
        if (
            not np.isfinite(self.spiral_exit_roll_deg)
            or abs(self.spiral_exit_roll_deg) > 180
        ):
            raise ValueError("Spiral exit roll must be finite and within 180 degrees")
        values = [
            *self.base_size_m,
            self.horizontal_scale,
            self.depth_scale,
            self.height_scale,
            self.wire_radius_m,
            self.loop_radius_m,
            self.loop_tube_radius_m,
            self.stem_length_m,
            self.grip_length_m,
            self.grip_radius_m,
            self.grip_half_thickness_m,
            self.end_stop_radius_m,
            self.rail_segment_m,
            self.witness_step_m,
            self.end_reserve_m,
        ]
        if (
            len(self.base_size_m) != 3
            or not np.isfinite(values).all()
            or min(values) <= 0
        ):
            raise ValueError("Dimensions must be finite and positive")
        if not isinstance(self.loop_segments, int) or self.loop_segments < 32:
            raise ValueError("At least 32 loop segments required")
        aperture = (
            self.loop_radius_m * np.cos(np.pi / self.loop_segments)
            - self.loop_tube_radius_m
        )
        if self.wire_radius_m >= aperture:
            raise ValueError("Wire does not fit inside the polygonal loop aperture")
        if (self.endpoint_support_part != "deck"
                and self.end_stop_radius_m <= self.loop_radius_m - self.loop_tube_radius_m):
            raise ValueError("End stops must be larger than the loop aperture")
        if self.rail_segment_m > 0.012 or self.witness_step_m > 0.004:
            raise ValueError(
                "Discretization too coarse for the baseline clearance check"
            )

    def control_points(self):
        if self.template_id == "authored_multistage_v1":
            return np.asarray(self.authored_controls_m, dtype=float)+[0, 0, self.route_elevation_m]
        if self.template_id in {"spatial_maze_v2", "spatial_maze_robot_v3"}:
            pass  # Definitions share this geometry module.

            points, _ = reference_maze_controls(
                self.vertical_valley_lift_m / self.height_scale,
                self.template_id == "spatial_maze_robot_v3",
            )
            nominal_base_height = 0.045
        else:
            points = self._slalom_controls()
            nominal_base_height = 0.05
        points[:, 0] *= self.horizontal_scale
        points[:, 1] *= self.depth_scale
        points[:, 2] = (
            self.base_size_m[2]
            + (points[:, 2] - nominal_base_height) * self.height_scale
        )
        return points+[0, 0, self.route_elevation_m]

    @staticmethod
    def _slalom_controls():
        points = np.array(
            [
                [-0.34, -0.14, 0.06],
                [-0.34, -0.14, 0.17],
                [-0.29, -0.12, 0.29],
                [-0.20, 0.035, 0.38],
                [-0.10, 0.16, 0.30],
                [0, 0.09, 0.20],
                [0.09, -0.12, 0.26],
                [0.18, -0.16, 0.41],
                [0.28, 0.06, 0.39],
                [0.34, 0.14, 0.25],
                [0.34, 0.14, 0.06],
            ],
            dtype=float,
        )
        return points

    def tool_capsules(self):
        a = np.arange(self.loop_segments) * 2 * np.pi / self.loop_segments
        points = np.c_[
            self.loop_radius_m * np.cos(a),
            self.loop_radius_m * np.sin(a),
            np.zeros_like(a),
        ]
        segments = [
            (p, q, self.loop_tube_radius_m, "loop")
            for p, q in zip(points, np.roll(points, -1, axis=0))
        ]
        r = self.loop_radius_m
        segments += [
            (
                np.array([r, 0, 0]),
                np.array([r + self.stem_length_m, 0, 0]),
                self.loop_tube_radius_m,
                "stem",
            ),
            (
                np.array([r + self.stem_length_m, 0, 0]),
                np.array([r + self.stem_length_m + self.grip_length_m, 0, 0]),
                self.grip_radius_m
                if self.grip_shape == "capsule"
                else np.hypot(self.grip_radius_m, self.grip_half_thickness_m),
                "grip",
            ),
        ]
        return segments


class SpatialWire:
    def __init__(self, layout=BuzzWireLayout()):
        layout.validate()
        self.layout = layout
        controls = layout.control_points()
        t = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(controls, axis=0), axis=1))]
        self.spline = CubicSpline(
            t, controls, bc_type=((1, [0, 0, 1]), (1, [0, 0, -1]))
        )
        dense_t = np.linspace(
            t[0], t[-1], 20001 if layout.template_id == "spatial_slalom_v1" else 40001
        )
        dense = self.spline(dense_t)
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))]
        self.length = float(arc[-1])
        if 2 * layout.end_reserve_m >= self.length:
            raise ValueError("Endpoint reserves leave no playable track")
        rail_s = np.linspace(
            0.0, self.length, int(np.ceil(self.length / layout.rail_segment_m)) + 1
        )
        self.rail = self.spline(np.interp(rail_s, arc, dense_t))
        xy_limit = np.asarray(layout.base_size_m[:2]) / 2 - layout.end_stop_radius_m
        if layout.end_stop_shape == "block_mount":
            # Mount width applies only to the two endpoints, not every bend.
            xy_limit = np.asarray(layout.base_size_m[:2]) / 2 - layout.wire_radius_m
            endpoint_bounds = (
                abs(self.rail[[0, -1], :2]) + np.asarray(layout.mount_size_m[:2]) / 2
            )
            if np.any(endpoint_bounds > np.asarray(layout.base_size_m[:2]) / 2):
                raise ValueError("Block mounts must fit over the base footprint")
        if np.any(np.abs(self.rail[:, :2]) > xy_limit):
            raise ValueError(
                "Wire and endpoint mounts must fit over the base footprint"
            )
        self.progress = np.linspace(
            0.0,
            1.0,
            int(
                np.ceil(
                    (self.length - 2 * layout.end_reserve_m) / layout.witness_step_m
                )
            )
            + 1,
        )
        witness_t = np.interp(
            layout.end_reserve_m
            + self.progress * (self.length - 2 * layout.end_reserve_m),
            arc,
            dense_t,
        )
        self.positions = self.spline(witness_t)
        tangents = self.spline(witness_t, 1)
        tangents /= np.linalg.norm(tangents, axis=1)[:, None]
        self.sections = {}
        if layout.template_id == "authored_multistage_v1":
            previous = 0.0
            for name, index in layout.authored_section_ends:
                end = float(
                    np.clip(
                        (np.interp(t[int(index)], dense_t, arc) - layout.end_reserve_m)
                        / (self.length - 2 * layout.end_reserve_m),
                        0,
                        1,
                    )
                )
                self.sections[str(name)] = dict(
                    start_progress=previous, end_progress=end
                )
                previous = end
            self.rotations = transported_frames(tangents)
        elif layout.template_id in {"spatial_maze_v2", "spatial_maze_robot_v3"}:
            pass  # Definitions share this geometry module.

            _, ends = reference_maze_controls(
                layout.vertical_valley_lift_m / layout.height_scale,
                layout.template_id == "spatial_maze_robot_v3",
            )
            previous = 0.0
            for name, index in ends.items():
                end = float(
                    np.clip(
                        (np.interp(t[index], dense_t, arc) - layout.end_reserve_m)
                        / (self.length - 2 * layout.end_reserve_m),
                        0,
                        1,
                    )
                )
                self.sections[name] = dict(start_progress=previous, end_progress=end)
                previous = end
            self.rotations = transported_frames(tangents)
            if layout.template_id == "spatial_maze_robot_v3":
                axes = self.rotations.apply([1.0, 0.0, 0.0])
                previous = axes[0]
                for i, tangent in enumerate(tangents):
                    up = np.array([0.0, 0.0, 1.0]) - tangent[2] * tangent
                    if np.linalg.norm(up) > 0.02:
                        previous = up / np.linalg.norm(up)
                    else:
                        previous = previous - (previous @ tangent) * tangent
                        previous /= np.linalg.norm(previous)
                    axes[i] = previous
                self.rotations = Rotation.from_matrix(
                    np.stack((axes, np.cross(tangents, axes), tangents), axis=2)
                )
            # Turn the grip away from the neighbouring spiral turn before the
            # inner lead-out bends down. This roll participates in clearance checks.
            u = np.clip(
                (self.progress - layout.spiral_exit_roll_start)
                / (layout.spiral_exit_roll_end - layout.spiral_exit_roll_start),
                0,
                1,
            )
            angle = np.deg2rad(layout.spiral_exit_roll_deg) * u * u * (3 - 2 * u)
            section = self.sections["vertical_switchbacks"]
            middle = (self.progress - section["start_progress"]) / (
                section["end_progress"] - section["start_progress"]
            )
            ramp = np.minimum(
                np.clip(middle / 0.20, 0, 1), np.clip((1 - middle) / 0.20, 0, 1)
            )
            angle += (
                np.deg2rad(layout.middle_handle_roll_deg) * ramp * ramp * (3 - 2 * ramp)
            )
            self.rotations = self.rotations * Rotation.from_rotvec(
                np.c_[np.zeros_like(u), np.zeros_like(u), angle]
            )
            if layout.upright_handle_pitch_deg:
                xz = self.rotations.apply([1.0, 0.0, 0.0])[:, 2]
                zz = self.rotations.apply([0.0, 0.0, 1.0])[:, 2]
                cap = np.deg2rad(layout.upright_handle_pitch_deg)
                pitch = np.clip(np.arctan2(-zz, xz), -cap, cap)
                self.rotations = self.rotations * Rotation.from_rotvec(
                    np.c_[np.zeros_like(pitch), pitch, np.zeros_like(pitch)]
                )
            u = np.clip((self.progress - 0.70) / 0.24, 0, 1)
            tilt = np.deg2rad(layout.spiral_normal_tilt_deg) * u * u * (3 - 2 * u)
            if layout.normal_tilt_knots:
                knots = np.asarray(layout.normal_tilt_knots)
                tilt = np.deg2rad(np.interp(self.progress, knots[:, 0], knots[:, 1]))
            self.rotations = self.rotations * Rotation.from_rotvec(
                np.c_[tilt, np.zeros_like(u), np.zeros_like(u)]
            )
        else:
            self.rotations = front_facing_frames(tangents)
        if layout.orientation_knots_wxyz:
            knots = np.asarray(layout.orientation_knots_wxyz, dtype=float)
            self.rotations = Slerp(
                knots[:, 0], Rotation.from_quat(knots[:, [2, 3, 4, 1]])
            )(self.progress)
        self.slerp = Slerp(self.progress, self.rotations)
        if layout.center_offset_knots_m:
            offsets = np.asarray(layout.center_offset_knots_m, dtype=float)
            self.positions += np.column_stack(
                [
                    np.interp(self.progress, offsets[:, 0], offsets[:, j])
                    for j in range(1, 4)
                ]
            )
        d, dd = self.spline(dense_t, 1), self.spline(dense_t, 2)
        self.minimum_curvature_radius = float(
            np.min(
                np.linalg.norm(d, axis=1) ** 3
                / np.maximum(np.linalg.norm(np.cross(d, dd), axis=1), 1e-15)
            )
        )

    def pose(self, progress):
        if not np.isfinite(progress) or not 0 <= progress <= 1:
            raise ValueError("Progress must be finite and in [0, 1]")
        p = np.array(
            [np.interp(progress, self.progress, self.positions[:, i]) for i in range(3)]
        )
        return p, self.slerp(progress).as_quat()[[3, 0, 1, 2]]

    def fixed_capsules(self):
        # Flat finish collars are contained in the same conservative stop sphere.
        r = self.layout.wire_radius_m
        segments = [(a, b, r, "wire") for a, b in zip(self.rail[:-1], self.rail[1:])]
        for endpoint in (self.rail[0], self.rail[-1]):
            p = endpoint.copy()
            if self.layout.end_stop_shape == "block_mount":
                p[2] = (
                    self.layout.base_elevation_m
                    + self.layout.base_size_m[2]
                    + self.layout.mount_size_m[2] / 2
                )
            segments.append((p, p, self.layout.end_stop_radius_m, "stop"))
        if self.layout.post_radius_m:
            r = self.layout.post_radius_m
            bottom = self.layout.base_size_m[2]
            for p in (self.rail[0], self.rail[-1]):
                segments.append(
                    (
                        np.array([*p[:2], bottom + r]),
                        np.array([*p[:2], bottom + self.layout.post_height_m - r]),
                        r,
                        "post",
                    )
                )
        return segments


def transported_frames(tangents):
    """Minimum-turn frames, including vertical and front/back-facing tangents."""
    x = np.array([0.0, -1.0, 0.0])
    x -= (x @ tangents[0]) * tangents[0]
    if np.linalg.norm(x) < 1e-8:
        x = np.eye(3)[np.argmin(np.abs(tangents[0]))]
        x -= (x @ tangents[0]) * tangents[0]
    x /= np.linalg.norm(x)
    axes = []
    for i, z in enumerate(tangents):
        if i:
            axis = np.cross(tangents[i - 1], z)
            sine = np.linalg.norm(axis)
            cosine = tangents[i - 1] @ z
            if cosine < -0.99:
                raise ValueError("Reference tangent reverses within one sample")
            if sine > 1e-12:
                x = Rotation.from_rotvec(axis * np.arctan2(sine, cosine) / sine).apply(
                    x
                )
        x -= (x @ z) * z
        x /= np.linalg.norm(x)
        axes.append(x.copy())
    axes = np.asarray(axes)
    return Rotation.from_matrix(
        np.stack((axes, np.cross(tangents, axes), tangents), axis=2)
    )


def front_facing_frames(tangents):
    # Point the handle toward the front, projected onto the loop plane.
    front = np.tile([0.0, -1.0, 0.0], (len(tangents), 1))
    x = front - (front * tangents).sum(axis=1)[:, None] * tangents
    if np.min(np.linalg.norm(x, axis=1)) < 0.12:
        raise ValueError("Reference handle frame approaches a singularity")
    x /= np.linalg.norm(x, axis=1)[:, None]
    matrices = np.stack((x, np.cross(tangents, x), tangents), axis=2)
    return Rotation.from_matrix(matrices)


def capsule_mesh(a, b, radius):
    """A visual capsule; collision uses an exact cylinder plus end spheres."""
    length = np.linalg.norm(b - a)
    if length < 1e-12:
        mesh = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        mesh.apply_translation(a)
        return mesh
    mesh = trimesh.creation.capsule(radius=radius, height=length, count=[12, 16])
    transform = trimesh.geometry.align_vectors([0, 0, 1], (b - a) / length)
    transform[:3, 3] = (a + b) / 2
    mesh.apply_transform(transform)
    return mesh


def _add_capsule(link, a, b, radius, color):
    if np.linalg.norm(b - a) > 1e-12:
        cylinder_between(link, a, b, radius, color)
    for p in (a, b) if np.linalg.norm(b - a) > 1e-12 else (a,):
        primitive(link, "sphere", {"radius": radius}, p, color=color)


def _write_xml(root, path):
    # URDF material names are shared references. Reusing "surface" for
    # different colors makes parsers paint the grip and stops like the rail.
    for material in root.findall(".//visual/material"):
        rgba = material.find("color").get("rgba")
        material.set(
            "name", "surface_" + hashlib.sha256(rgba.encode()).hexdigest()[:12]
        )
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)


def _contact_roles(link, role, start=0):
    for index, node in enumerate(link.findall("collision")):
        if index >= start:
            node.set("name", f"terminal__{role}__{index}")


def generate_assets(folder, layout=BuzzWireLayout()):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    wire = SpatialWire(layout)
    root = ET.Element("robot", name="spatial_buzz_wire")
    link = ET.SubElement(root, "link", name="wire")
    stop_colors = iter([(0.15, 0.59, 0.48, 1), (0.87, 0.42, 0.21, 1)])
    stop_index = 0
    for a, b, r, part in wire.fixed_capsules():
        collision_start = len(link.findall("collision"))
        contact_role = "wire_metal" if part == "wire" else "wood_stop"
        color = (
            (0.72, 0.39, 0.18, 1)
            if part == "wire"
            else (0.27, 0.13, 0.06, 1)
            if part == "post"
            else next(stop_colors)
        )
        if part == "stop":
            stop_index += 1
            if layout.end_stop_shape == "block_mount":
                primitive(
                    link,
                    "box",
                    {"size": vector_text(layout.mount_size_m)},
                    a,
                    color=color,
                )
                _contact_roles(link, contact_role, collision_start)
                continue
            if stop_index == 2 and layout.end_stop_shape == "flat_finish":
                primitive(
                    link,
                    "cylinder",
                    {
                        "radius": r - 0.0005,
                        "length": layout.end_stop_thickness_m,
                    },
                    a,
                    color=color,
                )
                _contact_roles(link, contact_role, collision_start)
                continue
        _add_capsule(
            link,
            a,
            b,
            r,
            color,
        )
        _contact_roles(link, contact_role, collision_start)
    _write_xml(root, folder / "wire.urdf")
    root = ET.Element("robot", name="loop_wand")
    link = ET.SubElement(root, "link", name="wand")
    for a, b, r, part in layout.tool_capsules():
        collision_start = len(link.findall("collision"))
        contact_role = "wand_handle" if part == "grip" else "wand_metal"
        if part == "grip" and layout.grip_shape == "box":
            primitive(
                link,
                "box",
                {
                    "size": vector_text(
                        (
                            layout.grip_length_m,
                            2 * layout.grip_radius_m,
                            2 * layout.grip_half_thickness_m,
                        )
                    )
                },
                (a + b) / 2,
                rpy=(np.deg2rad(layout.grip_flat_roll_deg), 0, 0),
                color=(0.12, 0.37, 0.60, 1),
            )
            _contact_roles(link, contact_role, collision_start)
            continue
        _add_capsule(
            link,
            a,
            b,
            r,
            (0.12, 0.37, 0.60, 1) if part == "grip" else (0.85, 0.62, 0.22, 1),
        )
        _contact_roles(link, contact_role, collision_start)
    # Explicit positive approximate compound inertia, with the link at loop centre.
    # A capsule mesh union is not needed for dynamics: mass sums over components,
    # and the small overlaps at joints are disclosed in the report.
    mass, first, inertia_origin = 0.0, np.zeros(3), np.zeros((3, 3))
    for a, b, r, part in layout.tool_capsules():
        if part == "grip" and layout.grip_shape == "box":
            mesh = trimesh.creation.box(
                (
                    layout.grip_length_m,
                    2 * layout.grip_radius_m,
                    2 * layout.grip_half_thickness_m,
                )
            )
            transform = np.eye(4)
            transform[:3, :3] = Rotation.from_euler(
                "x", layout.grip_flat_roll_deg, degrees=True
            ).as_matrix()
            transform[:3, 3] = (a + b) / 2
            mesh.apply_transform(transform)
        else:
            mesh = capsule_mesh(a, b, r)
        mesh.density = (
            (650.0 if part == "grip" else 7800.0)
            if layout.finish == "toy_wood_copper"
            else (650.0 if part == "grip" else 8960.0)
            if layout.finish == "wood_metal"
            else (1100.0 if part == "grip" else 7800.0)
        )
        m, com = mesh.mass, mesh.center_mass
        mass += m
        first += m * com
        inertia_origin += mesh.moment_inertia + m * (
            (com @ com) * np.eye(3) - np.outer(com, com)
        )
    com = first / mass
    inertia = inertia_origin - mass * ((com @ com) * np.eye(3) - np.outer(com, com))
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz=vector_text(com))
    ET.SubElement(inertial, "mass", value=str(mass))
    ET.SubElement(
        inertial,
        "inertia",
        **{
            name: str(inertia[i, j])
            for name, i, j in [
                ("ixx", 0, 0),
                ("iyy", 1, 1),
                ("izz", 2, 2),
                ("ixy", 0, 1),
                ("ixz", 0, 2),
                ("iyz", 1, 2),
            ]
        },
    )
    _write_xml(root, folder / "wand.urdf")
    if layout.finish in {"wood_metal", "toy_wood_copper"}:

        finish_assets(folder, wire)
    np.savez_compressed(
        folder / "reference_path.npz",
        rail=wire.rail,
        progress=wire.progress,
        positions=wire.positions,
        quaternions_wxyz=wire.rotations.as_quat()[:, [3, 0, 1, 2]],
    )
    report = dict(
        schema_version=1,
        template=layout.template_id,
        sections=wire.sections,
        layout=asdict(layout),
        rail_length_m=wire.length,
        playable_length_m=wire.length - 2 * layout.end_reserve_m,
        rail_bounds_m=[wire.rail.min(0).tolist(), wire.rail.max(0).tolist()],
        minimum_sampled_curvature_radius_m=wire.minimum_curvature_radius,
        rail_segments=len(wire.rail) - 1,
        reference_poses=len(wire.progress),
        loop_inner_radius_m=layout.loop_radius_m - layout.loop_tube_radius_m,
        nominal_radial_clearance_m=layout.loop_radius_m
        - layout.loop_tube_radius_m
        - layout.wire_radius_m,
        wand_mass_kg=float(mass),
        wand_center_of_mass_m=com.tolist(),
        wand_inertia_kg_m2=inertia.tolist(),
        finish=layout.finish,
        component_density_kg_m3=(
            dict(grip=650.0, loop_and_stem=7800.0)
            if layout.finish == "toy_wood_copper"
            else dict(grip=650.0, loop_and_stem=8960.0)
            if layout.finish == "wood_metal"
            else dict(grip=1100.0, loop_and_stem=7800.0)
        ),
        mass_model="sum of overlapping capsule mesh components"
        if layout.grip_shape == "capsule"
        else "capsule mesh components plus exact rectangular grip",
        initial_pose=dict(
            position_m=wire.positions[0].tolist(),
            quaternion_wxyz=wire.pose(0)[1].tolist(),
        ),
        reference_motion="piecewise linear position + shortest quaternion SLERP; no physics claim",
    )
    (folder / "geometry_report.json").write_text(json.dumps(report, indent=2) + "\n")
    files = ["wire.urdf", "wand.urdf", "reference_path.npz", "geometry_report.json"]
    if layout.finish in {"wood_metal", "toy_wood_copper"}:
        files += [p.name for p in sorted(folder.glob("*.glb"))]
    if layout.finish == "toy_wood_copper":
        files += ["base.urdf", "base_collision_0.obj", "base_collision_1.obj"]
    (folder / "sha256.json").write_text(
        json.dumps(
            {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in files},
            indent=2,
        )
        + "\n"
    )
    return wire, report


def tube_mesh(points, radius, closed=False, sides=12):
    points = np.asarray(points)
    tangent = (
        np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
        if closed
        else np.gradient(points, axis=0)
    )
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    frame = transported_frames(tangent)
    u, v = frame.apply([1, 0, 0]), frame.apply([0, 1, 0])
    theta = np.arange(sides) * 2 * np.pi / sides
    vertices = (
        points[:, None, :]
        + radius
        * (
            u[:, None, :] * np.cos(theta)[None, :, None]
            + v[:, None, :] * np.sin(theta)[None, :, None]
        )
    ).reshape(-1, 3)
    faces = []
    for i in range(len(points) if closed else len(points) - 1):
        j = (i + 1) % len(points)
        for a in range(sides):
            b = (a + 1) % sides
            faces.extend(
                [
                    [i * sides + a, j * sides + a, j * sides + b],
                    [i * sides + a, j * sides + b, i * sides + b],
                ]
            )
    return trimesh.Trimesh(
        vertices=vertices, faces=np.asarray(faces)[:, ::-1], process=False
    )


"""Deterministic family geometry, derived from the authored designs."""


COLORS = ["entry", "middle", "exit", "final"]


def clean(points):
    points = np.asarray(points, dtype=float)
    return points[np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-10]]


def line(a, b):
    return np.linspace(a, b, 60)


def vertical_wave_controls(spec):
    """Two or three authored arches with one smooth fore/aft excursion.

    The end posts are part of the same open wire. Depth is a smooth function
    of horizontal travel, so the vertical legs retain vertical tangents.
    """
    prototype = spec["prototypes"][spec["default_prototype"]]
    p = prototype["nominal"]
    count = prototype["fixed_structure"]["peak_count"]
    radius = p["turn_radius_m"]
    low, high = p["low_height_m"], p["high_height_m"]
    depth = p["depth_span_m"]
    if count not in (2, 3) or radius <= 0 or high - low < 2 * radius + 0.020:
        raise ValueError("Vertical wave needs distinct arches and connecting legs")
    left = -(2 * count - 1) * radius
    x = left
    controls = line([x, 0, 0.040], [x, 0, high - radius])
    ends = [["start_post", len(controls) - 1]]
    for index in range(2 * count - 1):
        peak = index % 2 == 0
        z = high - radius if peak else low + radius
        theta = np.linspace(np.pi, 0 if peak else 2 * np.pi, 120)
        arc = np.c_[
            x + radius + radius * np.cos(theta),
            np.zeros_like(theta),
            z + radius * np.sin(theta),
        ]
        controls = clean(np.vstack([controls, line(controls[-1], arc[0]), arc]))
        label = f"arch_{index // 2 + 1}" if peak else f"valley_{index // 2 + 1}"
        ends.append([label, len(controls) - 1])
        x += 2 * radius
    controls = clean(np.vstack([controls, line(controls[-1], [x, 0, 0.040])]))
    ends.append(["finish_post", len(controls) - 1])
    fraction = (controls[:, 0] - left) / (-2 * left)
    controls[:, 1] = -depth / 2 * np.cos(2 * np.pi * fraction)
    return controls, ends


def comb(stage):
    p, place = stage["nominal"], stage["sketch_placement"]
    r, x, lo = p["turn_radius_m"], place["start_x_m"], place["y_min_m"]
    hi, z = lo + p["straight_run_m"], p["height_m"]
    pieces = [line([x, lo, z], [x, hi, z])]
    for i in range(stage["return_count"]):
        y = hi if i % 2 == 0 else lo
        t = np.linspace(np.pi, 0 if i % 2 == 0 else 2 * np.pi, 90)
        pieces.append(
            np.c_[x + r + r * np.cos(t), y + r * np.sin(t), np.full_like(t, z)]
        )
        x += 2 * r
        end_y = lo if i % 2 == 0 else hi
        if i == stage["return_count"] - 1:
            end_y = lo + 0.55 * p["straight_run_m"]
        pieces.append(line(pieces[-1][-1], [x, end_y, z]))
    return clean(np.concatenate(pieces))


def eight(stage):
    p, place = stage["nominal"], stage["sketch_placement"]
    cut = np.deg2rad(p["end_cut_angle_deg"])
    t = np.linspace(1.5 * np.pi - cut, -0.5 * np.pi + cut, 800)
    return np.c_[
        place["center_x_m"] + p["right_lobe_extent_m"] * np.sin(t),
        place["center_y_m"] + p["depth_span_m"] / 2 * np.sin(2 * t),
        p["center_height_m"] + p["crossing_height_gap_m"] / 2 * np.cos(t),
    ]


def w_valleys(stage):
    p, place = stage["nominal"], stage["sketch_placement"]
    r, low, high = p["turn_radius_m"], p["low_height_m"], p["high_height_m"]
    x, y = place["start_x_m"], p["front_y_m"]
    pieces = [line([x, y, high - 0.010], [x, y, low + r])]
    for i in range(3):
        bottom = i % 2 == 0
        z = low + r if bottom else high - r
        t = np.linspace(np.pi, 2 * np.pi if bottom else 0, 90)
        start = np.array([x, y, z])
        pieces.append(line(pieces[-1][-1], start))
        pieces.append(
            np.c_[x + r + r * np.cos(t), np.full_like(t, y), z + r * np.sin(t)]
        )
        x += 2 * r
    pieces.append(line(pieces[-1][-1], [x, y, high - 0.010]))
    return clean(np.concatenate(pieces))


def omega(stage, sweep):
    p, place = stage["nominal"], stage["sketch_placement"]
    t = np.deg2rad(
        np.linspace(place["start_angle_deg"], place["start_angle_deg"] + sweep, 250)
    )
    return np.c_[
        np.full_like(t, place["plane_x_m"]),
        p["center_y_m"] + p["radius_m"] * np.cos(t),
        p["center_height_m"] + p["radius_m"] * np.sin(t),
    ]


def coil(stage, turns):
    p, place = stage["nominal"], stage["sketch_placement"]
    alpha = np.deg2rad(p["plane_tilt_deg"])
    axis = np.array([np.cos(alpha), 0, np.sin(alpha)])
    u = np.array([0, 1, 0])
    v = np.cross(axis, u)
    s = np.linspace(0, 1, 250)
    t = np.deg2rad(place["start_angle_deg"]) + turns * 2 * np.pi * s
    return (
        np.asarray(place["center_m"])
        + s[:, None] * p["axial_advance_m"] * axis
        + p["radius_m"] * (np.cos(t)[:, None] * u + np.sin(t)[:, None] * v)
    )


def join(a, b, handle):
    da, db = a[-1] - a[-2], b[1] - b[0]
    controls = [
        a[-1],
        a[-1] + handle * da / np.linalg.norm(da),
        b[0] - handle * db / np.linalg.norm(db),
        b[0],
    ]
    t = np.linspace(0, 1, 100)[:, None]
    return (
        (1 - t) ** 3 * controls[0]
        + 3 * (1 - t) ** 2 * t * controls[1]
        + 3 * (1 - t) * t**2 * controls[2]
        + t**3 * controls[3]
    )


def compose(path):
    spec = yaml.safe_load(Path(path).read_text())
    proto = spec["prototypes"][spec["default_prototype"]]
    curves = []
    for name in proto["stage_order"]:
        stage = proto["stages"][name]
        motif = stage["motif"]
        if motif == "horizontal_parallel_returns":
            points = comb(stage)
        elif motif == "open_over_under_figure_eight":
            points = eight(stage)
        elif motif == "two_valleys_and_one_crest":
            points = w_valleys(stage)
        elif motif == "open_omega_return":
            points = omega(stage, proto["fixed_structure"]["omega_sweep_deg"])
        elif motif == "inclined_open_helix":
            points = coil(stage, proto["fixed_structure"]["coil_turns"])
        else:
            raise ValueError(motif)
        curves.append((name, points))
    pieces = []
    for i, (name, points) in enumerate(curves):
        if i:
            connector = join(
                curves[i - 1][1], points, proto["nominal"]["connector_handle_m"]
            )
            pieces.append(("connector", connector, "#8b9298"))
        pieces.append((name, points, COLORS[i]))
    return spec, proto, pieces


"""Physical wooden supports and supported endpoint poses, in toy coordinates."""



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
    if layout.endpoint_support_part == "deck":
        # Preserve the original ring, neck and handle dimensions. Their unequal
        # thicknesses give a small natural resting pitch: the ring's far edge
        # and the grip's near bottom edge share the deck support plane.
        span = 2 * layout.loop_radius_m + layout.stem_length_m
        half = layout.grip_half_thickness_m
        pitch = np.arctan2(half, span) - np.arcsin(
            layout.loop_tube_radius_m / np.hypot(span, half))
        # Both handles point inward so their complete footprint rests on the
        # deck, including the old F2/F3 finish poses near its outer edge.
        horizontal = -route.rail[0 if end == 0 else -1].copy()
        horizontal[2] = 0.
        horizontal /= np.linalg.norm(horizontal)
        x = horizontal * np.cos(pitch) + [0, 0, np.sin(pitch)]
        z = -horizontal * np.sin(pitch) + [0, 0, np.cos(pitch)]
        r = Rotation.from_matrix(np.column_stack([x, np.cross(z, x), z]))
        p = route.rail[0 if end == 0 else -1].copy()
        p[2] = (layout.base_elevation_m + layout.base_size_m[2]
                + layout.loop_radius_m * np.sin(pitch) + layout.loop_tube_radius_m
                + .00005)
        return p, r
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
    if (not layout.supported_endpoints or layout.endpoint_support_part == "deck"
            or not layout.rest_finish_quaternion_wxyz):
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


def support_boxes(route, *, terminal_roles=False):
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
    if layout.supported_endpoints and layout.endpoint_support_part != "deck":
        # Support the proximal end of the handle, leaving the grasp pads clear.
        deck = elevation + layout.base_size_m[2]
        for end in (0, 1):
            if end and layout.rest_finish_quaternion_wxyz:
                continue
            p, r = endpoint_pose(route, end)
            if layout.endpoint_support_part == "stem":
                # Leave the entire wooden grip clear during finger closure.
                # The loop mount and this proximal metal-stem seat bracket the
                # tool's centre of mass without attaching or fixing the tool.
                axis = r.apply([1., 0., 0.])
                centre = p + r.apply(
                    [layout.loop_radius_m + layout.stem_length_m / 4, 0, 0]
                )
                bottom = centre[2] - layout.loop_tube_radius_m * np.hypot(axis[0], axis[1])
                height = bottom - deck
                if height <= 0:
                    raise ValueError("Stem support must sit above the deck")
                centre[2] = deck + height / 2
                yaw = Rotation.from_euler("z", np.arctan2(axis[1], axis[0]))
                boxes.append((centre, np.array([0.006, 0.003, height]), yaw, ("finish_support" if terminal_roles and end else "stem_saddle")))
                continue
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
                    (centre, np.array([0.006, 0.003, height]), r, ("finish_support" if terminal_roles and end else "handle_saddle"))
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
                boxes.append((centre, size, grip, ("finish_support" if terminal_roles and end else "handle_saddle")))
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
                        ("finish_support" if terminal_roles and end else "saddle_post"),
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


"""Photo-inspired continuous track: horizontal folds, vertical folds, spiral.

Nominal coordinates use a 45 mm base. These are authored dimensions, not
measurements inferred from the reference photo. All junctions share endpoints.
"""



def reference_maze_controls(valley_lift=0.0, robot_friendly=False):
    p = []
    stages = {}

    def add(v):
        for q in v:
            if not p or np.linalg.norm(np.asarray(q) - p[-1]) > 1e-8:
                p.append(np.asarray(q, dtype=float))

    def line(q):
        if not p:
            add([q])
            return
        add(
            np.linspace(
                p[-1], q, max(2, int(np.linalg.norm(np.asarray(q) - p[-1]) / 0.025) + 1)
            )
        )

    def arc(c, u, v, r, a, b, n=16):
        ts = np.linspace(a, b, n)
        add(
            [
                np.asarray(c)
                + r * (np.cos(t) * np.asarray(u) + np.sin(t) * np.asarray(v))
                for t in ts
            ]
        )

    line([-0.49, -0.28, 0.055])
    line([-0.49, -0.28, 0.46])
    arc([-0.49, -0.215, 0.46], [0, -1, 0], [0, 0, 1], 0.065, 0, np.pi / 2)
    line([-0.49, 0.20, 0.525])
    arc([-0.43, 0.20, 0.525], [1, 0, 0], [0, 1, 0], 0.06, np.pi, 0)
    line([-0.37, -0.20, 0.525])
    arc([-0.31, -0.20, 0.525], [1, 0, 0], [0, 1, 0], 0.06, np.pi, 2 * np.pi)
    line([-0.25, 0.20, 0.525])
    arc([-0.19, 0.20, 0.525], [1, 0, 0], [0, 1, 0], 0.06, np.pi, 0)
    line([-0.13, -0.12, 0.525])
    stages["horizontal_switchbacks"] = len(p) - 1
    if robot_friendly:
        spiral_shift = 0.0
        # An inclined vertical fold retains the down/up height reversal and
        # fore/aft travel for a finite robot wrist at the bottoms of the folds.
        arc([-0.065, -0.12, 0.525], [1, 0, 0], [0, 1, 0], 0.065, np.pi, 1.5 * np.pi)
        u = np.linspace(0, 1, 101)
        blend = u * u * (3 - 2 * u)
        add(
            np.c_[
                -0.065 + 0.155 * u,
                -0.185 + (0.165 + spiral_shift) * blend,
                0.525 + 0.020 * blend - 0.12 * np.sin(np.pi * u) ** 2,
            ]
        )
        stages["vertical_switchbacks"] = len(p) - 1
        arc(
            [0.09, 0.045 + spiral_shift, 0.545],
            [0, -1, 0],
            [1, 0, 0],
            0.065,
            0,
            np.pi / 2,
        )
    else:
        spiral_shift = 0.0
        _vertical_controls(add, line, arc, stages, p, valley_lift)
    turns = 1.0 if robot_friendly else 1.35
    theta = np.linspace(np.pi, np.pi - 2 * np.pi * turns, 101)
    radius = np.linspace(0.185, 0.065, len(theta))
    xyz = np.c_[
        0.34 + radius * np.cos(theta),
        0.045 + spiral_shift + radius * np.sin(theta),
        np.linspace(0.545, 0.58, len(theta)),
    ]
    add(xyz)
    end = xyz[-1]
    t = xyz[-1] - xyz[-2]
    t[2] = 0
    t /= np.linalg.norm(t)
    # Quarter-turn the end into a downward support, keeping it below the spiral.
    arc(end + [0, 0, -0.055], [0, 0, 1], t, 0.055, 0, np.pi / 2)
    line([*p[-1][:2], 0.055])
    stages["spiral"] = len(p) - 1
    return np.array(p), stages


def _vertical_controls(add, line, arc, stages, p, valley_lift):
    arc([-0.13, -0.12, 0.46], [0, 0, 1], [0, -1, 0], 0.065, 0, np.pi / 2)
    line([-0.13, -0.185, 0.16 + valley_lift])
    arc(
        [-0.0825, -0.185, 0.16 + valley_lift],
        [1, 0, 0],
        [0, 0, 1],
        0.0475,
        np.pi,
        2 * np.pi,
    )
    line([-0.035, -0.185, 0.42])
    arc([0.0125, -0.185, 0.42], [1, 0, 0], [0, 0, 1], 0.0475, np.pi, 0)
    line([0.06, -0.185, 0.19 + valley_lift])
    arc(
        [0.1075, -0.185, 0.19 + valley_lift],
        [1, 0, 0],
        [0, 0, 1],
        0.0475,
        np.pi,
        2 * np.pi,
    )
    line([0.155, -0.185, 0.48])
    stages["vertical_switchbacks"] = len(p) - 1
    arc([0.155, -0.12, 0.48], [0, -1, 0], [0, 0, 1], 0.065, 0, np.pi / 2)
    line([0.155, 0.045, 0.545])


# Visual assets authored with this task geometry.





def wood(mesh, *, light=False, tile=0.20):
    return wood_visual(
        mesh,
        resource_path("hedgehog_in_cage/materials/" + ("light_wood.png" if light else "dark_wood.png")),
        roughness=0.48 if light else 0.55,
        tile_size=tile,
        grain_horizontal=light,
    )


def metal(mesh, *, copper=False):
    mesh.visual = TextureVisuals(
        uv=np.zeros((len(mesh.vertices), 2)),
        material=PBRMaterial(
            name="brushed_copper" if copper else "stainless_wire",
            baseColorFactor=(0.72, 0.33, 0.16, 1) if copper else (0.68, 0.73, 0.77, 1),
            metallicFactor=0.9,
            roughnessFactor=0.25 if copper else 0.28,
        ),
    )
    return mesh


def replace_visuals(path, filenames):
    tree = ET.parse(path)
    link = tree.find("link")
    for node in link.findall("visual"):
        link.remove(node)
    # Nyx's URDF subscene addresses visuals by link: use one visual per link.
    # Keep separate PBR primitives inside that GLB. Concatenating to a texture
    # atlas discards metallic/roughness channels and turns metal into plastic.
    if len(filenames) > 1:
        merged = trimesh.Scene()
        for name in filenames:
            mesh = trimesh.load(Path(path).parent / name, force="mesh", process=False)
            node_name = Path(path).stem+"_"+Path(name).stem
            mesh.visual.material.name = node_name
            merged.add_geometry(mesh, geom_name=node_name, node_name=node_name)
        filename = Path(path).stem + "_visual.glb"
        merged.export(Path(path).parent / filename)
    else:
        filename = filenames[0]
    node = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=filename)
    ET.indent(tree)
    tree.write(path, encoding="unicode", xml_declaration=True)




def finish_assets(folder, wire):
    # One smooth visual tube avoids the bead-like joints of collision capsules.
    # Collision primitives remain exact and are independently checked.

    layout = wire.layout
    if layout.finish == "toy_wood_copper":
        return finish_toy_assets(folder, wire)
    base = trimesh.creation.box(layout.base_size_m)
    wood(base, light=True, tile=0.26).export(folder / "base_wood.glb")
    metal(tube_mesh(wire.rail, layout.wire_radius_m, sides=20)).export(
        folder / "rail_metal.glb"
    )
    mounts = [
        capsule_mesh(a, b, r)
        for a, b, r, part in wire.fixed_capsules()
        if part != "wire"
    ]
    wood(trimesh.util.concatenate(mounts), tile=0.12).export(folder / "posts_wood.glb")
    replace_visuals(folder / "wire.urdf", ["rail_metal.glb", "posts_wood.glb"])

    segments = layout.tool_capsules()
    loop = tube_mesh(
        np.array([row[0] for row in segments[:-2]]), layout.loop_tube_radius_m, True, 20
    )
    metal(
        trimesh.util.concatenate([loop, capsule_mesh(*segments[-2][:3])]), copper=True
    ).export(folder / "ring_copper.glb")
    a, b, radius, _ = segments[-1]
    if layout.grip_shape == "box":
        grip = trimesh.creation.box(
            (
                layout.grip_length_m,
                2 * layout.grip_radius_m,
                2 * layout.grip_half_thickness_m,
            )
        )
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_euler(
            "x", layout.grip_flat_roll_deg, degrees=True
        ).as_matrix()
        transform[:3, 3] = (a + b) / 2
        grip.apply_transform(transform)
    else:
        grip = capsule_mesh(a, b, radius)
    wood(grip, light=True, tile=0.08).export(folder / "handle_wood.glb")
    replace_visuals(folder / "wand.urdf", ["ring_copper.glb", "handle_wood.glb"])


def toy_wood(mesh, tile=0.60):
    """Continuous pale wood grain, without repeated strips at UV wrap seams."""
    vertices = mesh.vertices[mesh.faces].reshape(-1, 3)
    normals = np.repeat(mesh.face_normals, 3, axis=0)
    dominant = np.repeat(np.argmax(abs(mesh.face_normals), axis=1), 3)
    u_axis = np.where(dominant == 0, 1, 0)
    v_axis = np.where(dominant == 2, 1, 2)
    rows = np.arange(len(vertices))
    uv = np.c_[vertices[rows, u_axis], vertices[rows, v_axis]] / tile + 0.5
    with Image.open(resource_path("hedgehog_in_cage/materials/light_wood.png")) as source:
        texture = source.convert("RGB")
    result = trimesh.Trimesh(
        vertices=vertices,
        faces=np.arange(len(vertices)).reshape(-1, 3),
        vertex_normals=normals,
        process=False,
    )
    result.visual = TextureVisuals(
        uv=uv,
        material=PBRMaterial(
            name="pale_toy_wood",
            baseColorTexture=texture,
            baseColorFactor=(0.90, 0.86, 0.77, 1),
            metallicFactor=0.0,
            roughnessFactor=0.62,
        ),
    )
    return result


def plinth_layers(size):
    """Two convex, cut-corner tiers contained by the original box envelope."""
    x, y, h = np.asarray(size) / 2
    corner = min(x, y) * 0.18

    def outline(inset):
        a, b = x - inset, y - inset
        return np.array(
            [
                [-a + corner, -b],
                [a - corner, -b],
                [a, -b + corner],
                [a, b - corner],
                [a - corner, b],
                [-a + corner, b],
                [-a, b - corner],
                [-a, -b + corner],
            ]
        )

    def tier(levels):
        vertices = np.vstack(
            [np.c_[outline(inset), np.full(8, z)] for z, inset in levels]
        )
        faces = [[0, i + 1, i] for i in range(1, 7)]
        top = (len(levels) - 1) * 8
        faces += [[top, top + i, top + i + 1] for i in range(1, 7)]
        for level in range(len(levels) - 1):
            for i in range(8):
                a, b = level * 8 + i, level * 8 + (i + 1) % 8
                faces += [[a, b, b + 8], [a, b + 8, a + 8]]
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        mesh.fix_normals()
        if not mesh.is_watertight or not mesh.is_convex:
            raise ValueError("Toy plinth tiers must be closed convex collision meshes")
        return mesh

    return [
        tier([(-h, 0.002), (-h + 0.002, 0), (-h + 0.006, 0.001)]),
        tier([(-h + 0.006, 0.008), (-h + 0.008, 0.005), (h, 0.011)]),
    ]


def finish_toy_assets(folder, wire):

    layout = wire.layout
    if layout.end_stop_shape != "block_mount":
        raise ValueError("Photo-style toy finish requires block mounts")
    layers = plinth_layers(layout.base_size_m)
    # The deck itself is the terminal support in the flat-rest revision.
    # Endpoint pose and full traversal still gate success; touching elsewhere
    # on this surface does not qualify the task.
    layer_roles = ["finish_support" if layout.endpoint_support_part == "deck"
                   else "wood_stop"] * len(layers)
    # URDF origin remains at the old deck centre; all physical supports share
    # the same generator as the IK and full-tool clearance checks.

    for layer in layers:
        layer.apply_translation([0, 0, layout.base_elevation_m])
    for centre, size, rotation, role in support_boxes(wire, terminal_roles=True):
        box = trimesh.creation.box(size)
        transform = np.eye(4)
        transform[:3, :3] = rotation.as_matrix()
        transform[:3, 3] = centre - [0, 0, layout.base_size_m[2] / 2]
        box.apply_transform(transform)
        layers.append(box)
        layer_roles.append("finish_support" if role == "finish_support" else "wood_stop")
    grain_tile = max(layout.base_size_m) * 1.04
    sphere_visuals = []
    for centre, radius, _ in support_spheres(wire):
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=radius)
        sphere.apply_translation(centre - [0, 0, layout.base_size_m[2] / 2])
        sphere_visuals.append(sphere)
    toy_wood(
        trimesh.util.concatenate([*layers, *sphere_visuals]), tile=grain_tile
    ).export(folder / "base_wood.glb")
    root = ET.Element("robot", name="toy_plinth")
    link = ET.SubElement(root, "link", name="base")
    visual = ET.SubElement(link, "visual")
    ET.SubElement(ET.SubElement(visual, "geometry"), "mesh", filename="base_wood.glb")
    for i, layer in enumerate(layers):
        filename = f"base_collision_{i}.obj"
        layer.export(folder / filename)
        node = ET.SubElement(link, "collision", name=f"terminal__{layer_roles[i]}__{i}")
        ET.SubElement(ET.SubElement(node, "geometry"), "mesh", filename=filename)
    for centre, radius, _ in support_spheres(wire):
        node = ET.SubElement(link, "collision", name=f"terminal__finish_support__{len(link.findall('collision'))}")
        ET.SubElement(
            node,
            "origin",
            xyz=" ".join(map(str, centre - [0, 0, layout.base_size_m[2] / 2])),
        )
        ET.SubElement(ET.SubElement(node, "geometry"), "sphere", radius=str(radius))
    ET.indent(root)
    ET.ElementTree(root).write(
        folder / "base.urdf", encoding="unicode", xml_declaration=True
    )
    rail = metal(tube_mesh(wire.rail, layout.wire_radius_m, sides=24), copper=True)
    rail.visual.material.roughnessFactor = 0.36
    rail.export(folder / "rail_metal.glb")
    mounts = []
    for a, _, _, part in wire.fixed_capsules():
        if part == "stop":
            block = trimesh.creation.box(layout.mount_size_m)
            block.apply_translation(a)
            mounts.append(block)
    toy_wood(trimesh.util.concatenate(mounts), tile=grain_tile).export(
        folder / "posts_wood.glb"
    )
    replace_visuals(folder / "wire.urdf", ["rail_metal.glb", "posts_wood.glb"])
    segments = layout.tool_capsules()
    loop = tube_mesh(
        np.array([row[0] for row in segments[:-2]]), layout.loop_tube_radius_m, True, 24
    )
    metal(trimesh.util.concatenate([loop, capsule_mesh(*segments[-2][:3])])).export(
        folder / "ring_steel.glb"
    )
    a, b, radius, _ = segments[-1]
    if layout.grip_shape == "box":
        grip = trimesh.creation.box(
            (
                layout.grip_length_m,
                2 * layout.grip_radius_m,
                2 * layout.grip_half_thickness_m,
            )
        )
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_euler(
            "x", layout.grip_flat_roll_deg, degrees=True
        ).as_matrix()
        transform[:3, 3] = (a + b) / 2
        grip.apply_transform(transform)
    else:
        grip = capsule_mesh(a, b, radius)
    toy_wood(grip, tile=0.16).export(folder / "handle_wood.glb")
    replace_visuals(folder / "wand.urdf", ["ring_steel.glb", "handle_wood.glb"])


def collision_roles(path):
    """Semantic collision identities for the World importer adapter."""
    return {node.get("name"): node.get("name").split("__")[1]
            for node in ET.parse(path).findall(".//collision")
            if node.get("name", "").startswith("terminal__")}
