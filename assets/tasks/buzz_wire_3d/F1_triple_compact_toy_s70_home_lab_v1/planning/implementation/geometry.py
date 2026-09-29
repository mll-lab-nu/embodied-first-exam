"""A supported spatial steady-hand toy and a constructive tool-path witness.

Lengths are metres. Coordinates are relative to the bottom centre of the base.
Collision solids and clearance covers are generated from the same capsules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation, Slerp
import trimesh

from topogym.tasks._rigid_geometry import cylinder_between, primitive, vector_text


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
    supported_endpoints: bool = False
    rest_handle_pitch_deg: float = 0.0
    rest_finish_yaw_deg: float = 0.0
    rest_finish_quaternion_wxyz: tuple = ()
    finish_cradle_mount_clearance_m: float = 0.0
    finish_cradle_neck_pair: bool = True

    def validate(self):
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
                or min(size[:2]) / 2 <= self.loop_radius_m - self.loop_tube_radius_m
                or self.post_radius_m != 0
            ):
                raise ValueError(
                    "Block mounts must be captive, covered, and replace round posts"
                )
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
        if self.end_stop_radius_m <= self.loop_radius_m - self.loop_tube_radius_m:
            raise ValueError("End stops must be larger than the loop aperture")
        if self.rail_segment_m > 0.012 or self.witness_step_m > 0.004:
            raise ValueError(
                "Discretization too coarse for the baseline clearance check"
            )

    def control_points(self):
        if self.template_id == "authored_multistage_v1":
            return np.asarray(self.authored_controls_m, dtype=float).copy()
        if self.template_id in {"spatial_maze_v2", "spatial_maze_robot_v3"}:
            from .templates import reference_maze_controls

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
        return points

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
            from .templates import reference_maze_controls

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


def generate_assets(folder, layout=BuzzWireLayout()):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    wire = SpatialWire(layout)
    root = ET.Element("robot", name="spatial_buzz_wire")
    link = ET.SubElement(root, "link", name="wire")
    stop_colors = iter([(0.15, 0.59, 0.48, 1), (0.87, 0.42, 0.21, 1)])
    stop_index = 0
    for a, b, r, part in wire.fixed_capsules():
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
                continue
        _add_capsule(
            link,
            a,
            b,
            r,
            color,
        )
    _write_xml(root, folder / "wire.urdf")
    root = ET.Element("robot", name="loop_wand")
    link = ET.SubElement(root, "link", name="wand")
    for a, b, r, part in layout.tool_capsules():
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
            continue
        _add_capsule(
            link,
            a,
            b,
            r,
            (0.12, 0.37, 0.60, 1) if part == "grip" else (0.85, 0.62, 0.22, 1),
        )
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
        from .appearance import finish_assets

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
