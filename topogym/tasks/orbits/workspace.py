"""Finite ALOHA workspace audit for the rotated Orbits initial placement.

Checks approach poses, not grasping, continuous transfers or a puzzle solution.
Uses the same tabletop ALOHA asset and limits as the Genesis scene. MuJoCo is
used for FK only; no dynamics steps are taken.
"""
import argparse
import hashlib
import json
from pathlib import Path

import fcl
from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import trimesh

from .geometry import OrbitsLayout, make_meshes

ROOT = Path(__file__).resolve().parents[3]
PAD_CENTER = np.array([.14381, 0, -.00355])


def approach_points(layout):
    l = layout
    points = {}
    for i in range(4):
        for side, sign in (("left", 1), ("right", -1)):
            # Clearance offsets are tool-sized; the ALOHA fingers are not scaled.
            points[f"ring_{i+1}_{side}"] = np.array([l.ring_x[i], sign*(l.ring_radius_m+l.ring_tube_radius_m+.011), l.ring_z[i]+.025])
    points["over_ball"] = np.array([l.post_x[0], 0, l.ball_z+l.ball_radius_m+.040])
    points["bight_hover"] = np.array([l.post_x[-1]-l.bight_radius_m, 0, l.base_height_m+.045])
    points["handle_hover"] = np.array([l.handle_x_m, 0, l.handle_height_m+.045])
    return points


class WorkspaceAudit:
    def __init__(self, cfg):
        from topogym.robot.assets import robot_asset
        self.cfg = cfg
        self.layout = OrbitsLayout(**OmegaConf.to_container(cfg.task.geometry)).scaled(float(cfg.task.get("scale", 1.)))
        self.asset = Path(robot_asset(cfg.robot_control))
        self.model = m = mujoco.MjModel.from_xml_path(str(self.asset))
        self.data = mujoco.MjData(m)
        mujoco.mj_resetDataKeyframe(m, self.data, 0)
        self.indices = {s: [int(m.joint(f"{s}/{n}").qposadr[0])
                           for n in cfg.robot_control.robot.arm_joint_names] for s in ("left", "right")}
        for side in self.indices:
            names = list(cfg.robot_control.robot.arm_joint_names)+list(cfg.robot_control.robot.finger_joint_names)
            for name, value in zip(names, cfg.robot_control.home[side]):
                self.data.qpos[int(m.joint(f"{side}/{name}").qposadr[0])] = value
        self.home = self.data.qpos.copy()
        self.limits = np.asarray(cfg.robot_control.robot.arm_joint_limits)
        if not np.allclose(cfg.env.robot_mount.euler, [0, 0, 0]):
            raise ValueError("Workspace audit currently requires the standard unrotated ALOHA mount")
        self.mount = np.asarray(cfg.env.robot_mount.pos, dtype=float)
        self.yaw = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
        self.origin = np.r_[np.asarray(cfg.task.origin_xy_m)-self.mount[:2],
                            float(cfg.env.frames.table_surface.origin[2])-self.mount[2]]
        parts, _ = make_meshes(self.layout)
        self.fixture = []
        for name, mesh in parts.items():
            vertices = self.yaw.apply(mesh.vertices)+self.origin
            shape = fcl.BVHModel(); shape.beginModel(len(mesh.vertices), len(mesh.faces))
            shape.addSubModel(vertices, mesh.faces); shape.endModel()
            self.fixture.append((name, fcl.CollisionObject(shape), vertices.min(0), vertices.max(0)))
        self.robot_geoms = []
        for i in range(m.ngeom):
            if not (m.geom_contype[i] or m.geom_conaffinity[i]):
                continue
            if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = m.mesh(m.geom_dataid[i])
                vertices = m.mesh_vert[mesh.vertadr[0]:mesh.vertadr[0]+mesh.vertnum[0]]
                hull = trimesh.convex.convex_hull(vertices)
                vertices = hull.vertices
                shape = fcl.Convex(vertices, len(hull.faces),
                    np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel())
            elif m.geom_type[i] == mujoco.mjtGeom.mjGEOM_SPHERE:
                radius = m.geom_size[i, 0]; shape = fcl.Sphere(radius)
                vertices = trimesh.bounds.corners([[-radius]*3, [radius]*3])
            else:
                raise ValueError("Unsupported ALOHA collision shape")
            self.robot_geoms.append((i, m.body(m.geom_bodyid[i]).name, fcl.CollisionObject(shape), vertices))

    def forward(self, q):
        self.data.qpos[:] = q
        mujoco.mj_forward(self.model, self.data)

    def pose(self, side):
        i = self.model.body(f"{side}/gripper_link").id
        r = self.data.xmat[i].reshape(3, 3).copy()
        return self.data.xpos[i].copy()+r@PAD_CENTER, r

    def solve(self, side, point, rotation, seed):
        q = seed.copy(); indices = self.indices[side]
        def residual(angles):
            q[indices] = angles; self.forward(q)
            p, r = self.pose(side)
            return np.r_[10*(p-point), Rotation.from_matrix(rotation.as_matrix()@r.T).as_rotvec()]
        result = least_squares(residual, q[indices], bounds=(self.limits[:, 0]+1e-6, self.limits[:, 1]-1e-6),
                               max_nfev=140, ftol=1e-10, xtol=1e-10, gtol=1e-10)
        error = residual(result.x)
        return q, float(np.linalg.norm(error[:3])/10), float(np.linalg.norm(error[3:]))

    def violations(self, q):
        self.forward(q); m, d = self.model, self.data
        bad = []
        for c in d.contact:
            if c.dist < -.0001:
                bad.append(dict(kind="robot_self", depth_m=float(-c.dist),
                    a=m.body(m.geom_bodyid[c.geom1]).name, b=m.body(m.geom_bodyid[c.geom2]).name))
        for i, name, obj, verts in self.robot_geoms:
            r, p = d.geom_xmat[i].reshape(3, 3), d.geom_xpos[i]
            obj.setTransform(fcl.Transform(r, p))
            vertices = verts@r.T+p; low, high = vertices.min(0), vertices.max(0)
            if low[2] < self.origin[2]-.0002 and "base_link" not in name:
                bad.append(dict(kind="robot_table", link=name, depth_m=float(self.origin[2]-low[2])))
            for part, other, lo, hi in self.fixture:
                if np.any(low > hi) or np.any(high < lo):
                    continue
                result = fcl.CollisionResult()
                fcl.collide(obj, other, fcl.CollisionRequest(), result)
                if result.is_collision:
                    bad.append(dict(kind="robot_fixture", link=name, part=part))
        return bad

    def find_pose(self, side, point):
        sign = 1 if side == "left" else -1
        failures = []; attempts = 0
        # The wrist can approach the far side diagonally around the upright;
        # directly reaching across a ring can be valid IK but collide with wood.
        for azimuth in (0, 45, -45, 90, -90):
            heading = Rotation.from_euler("z", azimuth, degrees=True)
            for tilt in (0, 30, 60, 90, -30):
                x = heading.apply([sign*np.cos(np.radians(tilt)), 0, -np.sin(np.radians(tilt))])
                y = heading.apply([0, 1, 0])
                for roll in (0, 90, 180, 270):
                    r = Rotation.from_matrix(np.column_stack([x, y, np.cross(x, y)]))*Rotation.from_euler("x", roll, degrees=True)
                    q, pe, re = self.solve(side, point, r, self.home)
                    attempts += 1
                    bad = self.violations(q) if pe < .0005 and re < .005 else [dict(kind="ik_tolerance")]
                    if not bad:
                        return dict(passed=True, qpos=q.tolist(), tcp_quat_xyzw=r.as_quat().tolist(),
                                    position_error_m=pe, rotation_error_rad=re, attempts=attempts,
                                    collisions=[], azimuth_deg=azimuth, tilt_deg=tilt, roll_deg=roll)
                    failures.append(dict(position_error_m=pe, rotation_error_rad=re, violations=bad))
        return dict(passed=False, attempts=attempts, failures=failures)


def audit(cfg):
    checker = WorkspaceAudit(cfg)
    results = {}
    for name, local in approach_points(checker.layout).items():
        point = checker.yaw.apply(local)+checker.origin
        results[name] = dict(point_task_m=local.tolist(), point_world_m=(point+checker.mount).tolist(),
                             arms={side:checker.find_pose(side, point) for side in ("left", "right")})
        print(name, {s:v["passed"] for s,v in results[name]["arms"].items()}, flush=True)
    pairs = {}
    for i in range(1, 5):
        a, b = results[f"ring_{i}_left"]["arms"]["left"], results[f"ring_{i}_right"]["arms"]["right"]
        if a["passed"] and b["passed"]:
            q = np.array(a["qpos"]); q[checker.indices["right"]] = np.array(b["qpos"])[checker.indices["right"]]
            bad = checker.violations(q)
            pairs[f"ring_{i}"] = dict(passed=not bad, qpos=q.tolist(), violations=bad)
        else:
            pairs[f"ring_{i}"] = dict(passed=False, reason="No accepted individual pose")
    low = np.min([lo for _,_,lo,_ in checker.fixture], axis=0)+checker.mount
    high = np.max([hi for _,_,_,hi in checker.fixture], axis=0)+checker.mount
    midpoint = checker.model.body("left/base_link").pos+checker.model.body("right/base_link").pos
    midpoint = midpoint/2+checker.mount
    base_center = (checker.origin+checker.mount)[:2]
    table_lo = np.asarray(cfg.env.world.table.pos)[:2]-np.asarray(cfg.env.world.table.size)[:2]/2
    table_hi = np.asarray(cfg.env.world.table.pos)[:2]+np.asarray(cfg.env.world.table.size)[:2]/2
    table_margin = float(min(*(low[:2]-table_lo), *(table_hi-high[:2])))
    home_bad = checker.violations(checker.home)
    pose_passed = all(v["passed"] for p in results.values() for v in p["arms"].values())
    resolved = OmegaConf.to_container(cfg, resolve=True)
    return dict(schema_version=1, task_id="orbits", scope="finite_collision_checked_approach_pose_audit",
        passed=pose_passed and all(p["passed"] for p in pairs.values()) and not home_bad and table_margin>0,
        pose_count=len(results)*2, target_count=len(results), paired_pose_count=len(pairs),
        origin_xy_m=list(cfg.task.origin_xy_m), yaw_deg=float(cfg.task.yaw_deg),
        uniform_scale=float(cfg.task.get("scale", 1.)),
        centering_reference=cfg.task.get("centering_reference", "complete_set_bounds"),
        wooden_base_xy_center_m=base_center.tolist(),
        wooden_base_offset_from_robot_midpoint_m=(base_center-midpoint[:2]).tolist(),
        complete_set_world_bounds_m=[low.tolist(), high.tolist()],
        complete_set_xy_center_m=((low[:2]+high[:2])/2).tolist(), robot_base_midpoint_world_m=midpoint.tolist(),
        minimum_table_edge_margin_m=table_margin, home_collisions=home_bad,
        position_tolerance_m=.0005, rotation_tolerance_rad=.005, pad_center_gripper_local_m=PAD_CENTER.tolist(),
        targets=results, simultaneous_ring_approaches=pairs,
        config=resolved, robot_asset_sha256=hashlib.sha256(checker.asset.read_bytes()).hexdigest(),
        simulation_steps=0, continuous_paths_verified=False, grasp_contact_verified=False,
        entire_workspace_volume_verified=False, physics_qualified=False,
        limitations=["Sampled approach poses with the other arm at home; four paired ring-side approaches also checked.",
                    "Approach points hover near task features; no cord pickup or handle grasp is certified.",
                    "No continuous transfer, full workspace volume, deformable cord or solution is certified."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="orbits_preview")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name=args.config)
    report = audit(cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(f"Placement audit passed={report['passed']}: {args.output}", flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
