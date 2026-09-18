"""Sampled bimanual plan for the certified three-motion Cast Coil prototype.

Robot poses are solved offline. This module does not execute physics or
establish grasp stability; robot_demo performs those checks independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fcl
from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import trimesh

from topogym.robot.assets import robot_asset
from .geometry import CoilAssembly, load_template
from .verification import geometric_audit, assembly_route
from .appearance import coordinate_scale

ROOT = Path(__file__).resolve().parents[3]
PAD_CENTER = np.array([0.14381, 0.0, -0.00355])


class Kinematics:
    def __init__(self, cfg):
        self.model = mujoco.MjModel.from_xml_path(robot_asset(cfg))
        self.data = mujoco.MjData(self.model)
        mujoco.mj_resetDataKeyframe(self.model, self.data, 0)
        self.q = self.data.qpos.copy()
        self.indices = {
            s: [
                int(self.model.joint(f"{s}/{n}").qposadr[0])
                for n in cfg.robot.arm_joint_names
            ]
            for s in ("left", "right")
        }
        self.limits = np.asarray(cfg.robot.arm_joint_limits)

    def pose(self, side):
        self.data.qpos[:] = self.q
        mujoco.mj_forward(self.model, self.data)
        body = self.model.body(f"{side}/gripper_link").id
        rotation = self.data.xmat[body].reshape(3, 3).copy()
        return self.data.xpos[
            body
        ].copy() + rotation @ PAD_CENTER, Rotation.from_matrix(rotation)

    def solve(self, side, position, rotation):
        # Genesis state arrays are float32. Preserve scipy finite differences.
        self.q = np.asarray(self.q, dtype=np.float64)
        indices = self.indices[side]
        target = rotation.as_matrix()

        def residual(q):
            self.q[indices] = q
            p, r = self.pose(side)
            return np.r_[
                10 * (p - position),
                Rotation.from_matrix(target @ r.as_matrix().T).as_rotvec(),
            ]

        solution = least_squares(
            residual,
            self.q[indices].copy(),
            bounds=(self.limits[:, 0] + 1e-6, self.limits[:, 1] - 1e-6),
            max_nfev=160,
            ftol=1e-11,
            xtol=1e-11,
            gtol=1e-11,
        )
        error = residual(solution.x)
        return float(np.linalg.norm(error[:3]) / 10), float(np.linalg.norm(error[3:]))


class RobotCollision:
    def __init__(self, kinematics, assembly):
        self.kinematics, self.assembly = kinematics, assembly
        self.geoms = []
        model = kinematics.model
        for i in range(model.ngeom):
            if not (model.geom_contype[i] or model.geom_conaffinity[i]):
                continue
            if model.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = model.mesh(model.geom_dataid[i])
                vertices = model.mesh_vert[
                    mesh.vertadr[0] : mesh.vertadr[0] + mesh.vertnum[0]
                ]
                hull = trimesh.convex.convex_hull(vertices)
                shape = fcl.Convex(
                    hull.vertices,
                    len(hull.faces),
                    np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel(),
                )
                vertices = hull.vertices
            elif model.geom_type[i] == mujoco.mjtGeom.mjGEOM_SPHERE:
                radius = model.geom_size[i, 0]
                shape = fcl.Sphere(radius)
                vertices = trimesh.bounds.corners([[-radius] * 3, [radius] * 3])
            else:
                raise ValueError("Unsupported robot collision primitive")
            self.geoms.append(
                (
                    i,
                    model.body(model.geom_bodyid[i]).name,
                    fcl.CollisionObject(shape),
                    vertices,
                )
            )
        self.boxes = [
            [fcl.CollisionObject(fcl.Box(*(hi - lo))) for lo, hi in body.boxes]
            for body in assembly.bodies
        ]
        self.request = fcl.CollisionRequest(num_max_contacts=8, enable_contact=True)

    def violations(self, poses):
        model, data = self.kinematics.model, self.kinematics.data
        data.qpos[:] = self.kinematics.q
        mujoco.mj_forward(model, data)
        bad = []
        for contact in data.contact:
            if contact.dist < -0.0001:
                bad.append(dict(kind="robot_self", depth_m=float(-contact.dist)))
        for i, body in enumerate(self.assembly.bodies):
            rotation, translation = poses[i]
            for j, obj in enumerate(self.boxes[i]):
                obj.setTransform(
                    fcl.Transform(
                        rotation.as_matrix(),
                        translation + rotation.apply(body.boxes[j].mean(axis=0)),
                    )
                )
        for i, name, obj, vertices in self.geoms:
            rotation, position = data.geom_xmat[i].reshape(3, 3), data.geom_xpos[i]
            obj.setTransform(fcl.Transform(rotation, position))
            z = float((vertices @ rotation.T + position)[:, 2].min())
            if z < -0.0002 and "base_link" not in name:
                bad.append(dict(kind="robot_table", depth_m=-z, robot=name))
            for part, boxes in enumerate(self.boxes):
                for box in boxes:
                    result = fcl.CollisionResult()
                    fcl.collide(obj, box, self.request, result)
                    depth = max(
                        (c.penetration_depth for c in result.contacts), default=0.0
                    )
                    if depth > 0.0003:
                        bad.append(
                            dict(
                                kind="robot_puzzle",
                                depth_m=float(depth),
                                robot=name,
                                part=part,
                            )
                        )
        return bad


def build(output, template=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Preserve previous plans; choose a new output filename")
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="cast_coil_aloha")
    kinematics = Kinematics(cfg.robot_control)
    assembly = CoilAssembly(load_template(template) if template else None)
    audit = geometric_audit(assembly)
    if not audit["prototype_route_certified"]:
        raise RuntimeError("Prototype route no longer certified")
    collision = RobotCollision(kinematics, assembly)
    yaw = Rotation.from_euler("z", 90, degrees=True)
    design_scale = coordinate_scale(assembly.template)
    root = np.array([0.0, 0.05, -min(b.visual.bounds[0, 2] for b in assembly.bodies)])
    lift = (0.08 if "inverse_design" in assembly.template else 0.07) * design_scale[2]
    rotations = {
        "left": Rotation.from_matrix(
            np.column_stack(([1, 0, 0], [0, 0, -1], [0, 1, 0]))
        ),
        "right": Rotation.from_matrix(
            np.column_stack(([-1, 0, 0], [0, 0, 1], [0, 1, 0]))
        ),
    }
    points = {
        "left": np.array([0.022, 0.032, 0.0405]) * design_scale,
        "right": np.array([-0.022, -0.032, 0.0405]) * design_scale,
    }
    frames, errors, phases = [], [], []
    checked = 0

    def segment(name, seconds, pose_at):
        nonlocal checked
        phases.append(dict(name=name, start_s=len(frames) / 50))
        for t in np.linspace(0, 1, round(seconds * 50) + 1)[1:]:
            u = t * t * t * (10 + t * (-15 + 6 * t))
            poses = pose_at(u)
            for side, part in (("right", 0), ("left", 1)):
                rb, pb = poses[part]
                error = kinematics.solve(
                    side, pb + rb.apply(points[side]), rb * yaw.inv() * rotations[side]
                )
                errors.append(error)
                if error[0] > 0.0003 or error[1] > 0.003:
                    raise RuntimeError(f"{name}: {side} IK failed at {u}: {error}")
            kinematics.q[[6, 7, 14, 15]] = 0.0203
            if len(frames) % 5 == 0:
                checked += 1
                bad = collision.violations(poses)
                if bad:
                    raise RuntimeError(f"{name}: robot collision at {u}: {bad[:3]}")
            frames.append(
                dict(
                    phase=name,
                    time_s=len(frames) / 50,
                    qpos=kinematics.q.tolist(),
                    bodies=[
                        dict(r=r.as_quat().tolist(), p=p.tolist()) for r, p in poses
                    ],
                )
            )
        print(name, len(frames), flush=True)

    segment("pregrasp", 0.5, lambda u: [(yaw, root)] * 2)
    segment("lift", 4, lambda u: [(yaw, root + [0, 0, lift * u])] * 2)
    raised = root + [0, 0, lift]
    route = assembly_route(assembly)
    for motion in route:

        def pose_at(u, motion=motion):
            r, t = motion.pose(u)
            return [
                (yaw, raised),
                (yaw * Rotation.from_matrix(r), raised + yaw.apply(t)),
            ]

        segment(motion.name, motion.duration_s * 2, pose_at)
    r, t = route[-1].pose(1)
    final_r, final_p = yaw * Rotation.from_matrix(r), raised + yaw.apply(t)
    bottom = float(
        (assembly.bodies[1].visual.vertices @ final_r.as_matrix().T + final_p)[
            :, 2
        ].min()
    )
    segment(
        "place_silver",
        2,
        lambda u: [(yaw, raised), (final_r, final_p - [0, 0, bottom * u])],
    )
    final_p = final_p - [0, 0, bottom]
    segment(
        "place_gold",
        3,
        lambda u: [(yaw, raised - [0, 0, lift * u]), (final_r, final_p)],
    )
    report = dict(
        lift=lift,
        root=root.tolist(),
        yaw_deg=90,
        scale=3.0,
        template_sha256=audit["template_sha256"],
        template=assembly.template,
        geometric_audit=audit,
        points={s: p.tolist() for s, p in points.items()},
        rotations={s: r.as_quat().tolist() for s, r in rotations.items()},
        frames=frames,
        phases=phases,
        maximum_ik_error=np.max(errors, axis=0).tolist(),
        fps=50,
        robot_collision_checked_frames=checked,
        robot_collision_check="sampled at 10 Hz; not a continuous robot certificate",
        robot_model_sha256=hashlib.sha256(
            Path(robot_asset(cfg.robot_control)).read_bytes()
        ).hexdigest(),
        scope="pregrasp reset, planned grasp, lift, complete prototype route and placement; no physics",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, separators=(",", ":")) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--template")
    args = parser.parse_args()
    build(args.output, args.template)
