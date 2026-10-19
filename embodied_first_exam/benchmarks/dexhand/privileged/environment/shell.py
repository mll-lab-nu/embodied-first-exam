"""Discrete triangular paper with edge constraints and bending memory.

MuJoCo owns all vertex dynamics and rigid/deformable contact. This module adds
dihedral bending forces and an elastic-perfectly-plastic rest angle per edge.
No paper vertices are driven by the robot controller.
"""

from __future__ import annotations

import numpy as np


def hinge_geometry(points):
    """Return signed angles and their four analytic position gradients."""
    a, b, c, d = np.moveaxis(points, 1, 0)
    edge = b - a
    length2 = np.einsum("ij,ij->i", edge, edge)
    length = np.sqrt(np.maximum(length2, 1e-20))
    normal1 = np.cross(edge, c - a)
    normal2 = np.cross(d - a, edge)
    norm12 = np.maximum(np.einsum("ij,ij->i", normal1, normal1), 1e-20)
    norm22 = np.maximum(np.einsum("ij,ij->i", normal2, normal2), 1e-20)
    angle = np.arctan2(
        np.einsum("ij,ij->i", np.cross(normal1, normal2), edge / length[:, None]),
        np.einsum("ij,ij->i", normal1, normal2),
    )
    gc = -normal1 * (length / norm12)[:, None]
    gd = -normal2 * (length / norm22)[:, None]
    tc = np.einsum("ij,ij->i", c - a, edge) / np.maximum(length2, 1e-20)
    td = np.einsum("ij,ij->i", d - a, edge) / np.maximum(length2, 1e-20)
    gb = -tc[:, None] * gc - td[:, None] * gd
    ga = -gb - gc - gd
    return angle, np.stack((ga, gb, gc, gd), axis=1)


def wrapped_angle(value):
    return np.arctan2(np.sin(value), np.cos(value))


class PaperShell:
    """A fixed-topology shell with soft edge constraints and effective thickness."""

    def __init__(self, model, data, config):
        self.model, self.data = model, data
        self.config = config
        import mujoco

        mujoco.mj_forward(model, data)
        self.reference_positions = data.flexvert_xpos.copy()
        self.vertex_bodies = model.flex_vertbodyid.copy()
        edges = model.flex_edge.copy()
        opposite = {}
        for triangle in model.flex_elem.reshape(-1, 3):
            for i in range(3):
                edge = tuple(sorted((int(triangle[i]), int(triangle[(i + 1) % 3]))))
                opposite.setdefault(edge, []).append(int(triangle[(i + 2) % 3]))
        self.hinges = np.asarray(
            [
                (*edge, *vertices)
                for edge, vertices in opposite.items()
                if len(vertices) == 2
            ],
            dtype=int,
        )
        self.edges = edges
        self.rest_length = model.flexedge_length0.copy()
        rest = self.reference_positions[self.hinges]
        edge_length = np.linalg.norm(rest[:, 1] - rest[:, 0], axis=1)
        area = (
            np.linalg.norm(
                np.cross(rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]), axis=1
            )
            + np.linalg.norm(
                np.cross(rest[:, 3] - rest[:, 0], rest[:, 1] - rest[:, 0]), axis=1
            )
        ) / 2
        self.stiffness = config["bending_rigidity_nm"] * edge_length**2 / area
        self.rest_angles = np.zeros(len(self.hinges))
        self.plastic_strain = np.zeros(len(self.hinges))
        self.plastic_work = np.zeros(len(self.hinges))
        self.force = np.zeros((model.nflexvert, 3))
        self.max_strain = 0.0
        # flexcomp nodes use three translational joints in the world frame.
        self.dofs = []
        for body in self.vertex_bodies:
            start = int(model.body_dofadr[body])
            count = int(model.body_dofnum[body])
            self.dofs.append(np.arange(start, start + count, dtype=int))

    def reset(self):
        self.rest_angles[:] = 0
        self.plastic_strain[:] = 0
        self.plastic_work[:] = 0
        self.max_strain = 0.0

    def apply(self):
        # mj_step integrates qpos after evaluating kinematics. Refresh it here
        # so custom forces use this substep's positions rather than cached
        # positions from the previous substep.
        import mujoco

        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_flex(self.model, self.data)
        positions = self.data.flexvert_xpos
        angles, gradient = hinge_geometry(positions[self.hinges])
        deviation = wrapped_angle(angles - self.rest_angles)
        yield_angle = self.config["yield_angle_rad"]
        increment = np.sign(deviation) * np.maximum(np.abs(deviation) - yield_angle, 0)
        damage = np.maximum(
            self.plastic_strain - self.config["weakening_onset_rad"], 0.0
        )
        ratio = np.maximum(
            np.exp(-self.config["plastic_weakening_rate"] * damage),
            self.config["minimum_bending_ratio"],
        )
        effective_stiffness = self.stiffness * ratio
        if self.config["plasticity"]:
            self.rest_angles = wrapped_angle(self.rest_angles + increment)
            self.plastic_work += effective_stiffness * yield_angle * np.abs(increment)
            # Paper fibers weaken when a crease is made. Accumulated plastic
            # rotation retains that weakening even if the sheet is unfolded.
            self.plastic_strain += np.abs(increment)
            deviation = wrapped_angle(angles - self.rest_angles)
        forces = (
            -effective_stiffness[:, None, None] * deviation[:, None, None] * gradient
        )
        self.force[:] = 0
        np.add.at(self.force, self.hinges.reshape(-1), forces.reshape(-1, 3))
        for vertex, dofs in enumerate(self.dofs):
            if len(dofs):
                self.data.qfrc_applied[dofs] = self.force[vertex]
        length = np.linalg.norm(
            positions[self.edges[:, 1]] - positions[self.edges[:, 0]], axis=1
        )
        strain = np.max(np.abs(length / self.rest_length - 1))
        self.max_strain = max(self.max_strain, float(strain))
