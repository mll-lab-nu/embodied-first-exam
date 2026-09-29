"""Single-arm IK planning and collision audits for the compact spatial wire."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import fcl
from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
import trimesh

from topogym.robot.assets import robot_asset
from topogym.robot.gripper import robotiq_joint_targets
from .geometry import BuzzWireLayout, generate_assets
from .physics import ROOT, save
from .render import sha
from .verification import verify_route


def config():
    with initialize_config_dir(version_base="1.3", config_dir=str(ROOT / "configs")):
        return compose(config_name="buzz_wire_3d_robot")


class Kinematics:
    def __init__(self, cfg):
        self.asset = robot_asset(cfg.robot_control)
        self.model = mujoco.MjModel.from_xml_path(self.asset)
        self.data = mujoco.MjData(self.model)
        self.mount = np.array(cfg.env.robot_mount.pos)
        self.q = np.zeros(self.model.nq)
        self.q[:7] = cfg.robot_control.home.qpos[:7]
        self.hand = self.model.body("hand").id
        self.limits = self.model.jnt_range[:7].copy()
        self.set_gap(float(cfg.task.geometry.grip_radius_m))
        p, r = self.forward()
        pads = []
        for name in ("left_finger", "right_finger"):
            i = self.model.body(name).id
            pads.append(
                self.data.xpos[i]
                + self.mount
                + self.data.xmat[i].reshape(3, 3) @ np.array([0, -0.0066, 0.01875])
            )
        self.pad_offset = r.inv().apply(np.mean(pads, 0) - p)

    def set_gap(self, half_gap):
        for name, value in robotiq_joint_targets(half_gap).items():
            name = {
                "right_driver_joint": "finger_joint1",
                "left_driver_joint": "finger_joint2",
            }.get(name, "r85_" + name)
            self.q[self.model.joint(name).qposadr[0]] = value

    def forward(self, arm=None):
        if arm is not None:
            self.q[:7] = arm
        self.data.qpos[:] = self.q
        mujoco.mj_forward(self.model, self.data)
        return self.data.xpos[self.hand] + self.mount, Rotation.from_matrix(
            self.data.xmat[self.hand].reshape(3, 3)
        )

    def solve(self, p, r, seed, attempts=1, max_nfev=160):
        rng = np.random.default_rng(17)
        starts = [
            seed,
            *rng.uniform(
                self.limits[:, 0] + 1e-4,
                self.limits[:, 1] - 1e-4,
                size=(attempts - 1, 7),
            ),
        ]
        best = None
        for start in starts:

            def residual(arm):
                pos, rot = self.forward(arm)
                return np.r_[
                    20 * (pos - p), (rot * r.inv()).as_rotvec(), 0.00003 * (arm - seed)
                ]

            opt = least_squares(
                residual,
                start,
                bounds=(self.limits[:, 0] + 1e-6, self.limits[:, 1] - 1e-6),
                max_nfev=max_nfev,
                ftol=1e-11,
                xtol=1e-11,
                gtol=1e-11,
            )
            e = residual(opt.x)
            pe = float(np.linalg.norm(e[:3]) / 20)
            re = float(np.linalg.norm(e[3:6]))
            if best is None or np.linalg.norm(e[:6]) < best[0]:
                best = (np.linalg.norm(e[:6]), opt.x.copy(), pe, re)
            if pe < 1e-5 and re < 1e-4:
                break
        self.forward(best[1])
        return best[1:]


def capsule(a, b, r):
    length = float(np.linalg.norm(b - a))
    if length < 1e-10:
        return fcl.CollisionObject(fcl.Sphere(r), fcl.Transform(a))
    transform = trimesh.geometry.align_vectors([0, 0, 1], (b - a) / length)
    return fcl.CollisionObject(
        fcl.Capsule(r, length), fcl.Transform(transform[:3, :3], (a + b) / 2)
    )


def manager(objects):
    result = fcl.DynamicAABBTreeCollisionManager()
    result.registerObjects(objects)
    result.setup()
    return result


class RobotAudit:
    def __init__(self, kin, route, origin, rotation, signed_distance=False):
        self.kin = kin
        self.signed_distance = signed_distance
        self.route = route
        from .supports import fixture_boxes, support_spheres

        self.fixed = [
            capsule(origin + rotation.apply(a), origin + rotation.apply(b), rad)
            for a, b, rad, part in route.fixed_capsules()
            if not (part == "stop" and route.layout.end_stop_shape == "block_mount")
        ]
        self.fixed.extend(
            fcl.CollisionObject(
                fcl.Box(*size),
                fcl.Transform(
                    (rotation * rot).as_matrix(),
                    origin + rotation.apply(centre),
                ),
            )
            for centre, size, rot, _ in fixture_boxes(route)
        )
        self.fixed.extend(
            fcl.CollisionObject(
                fcl.Sphere(radius), fcl.Transform(origin + rotation.apply(centre))
            )
            for centre, radius, _ in support_spheres(route)
        )
        self.fixed_manager = manager(self.fixed)
        self.wire_manager = manager(self.fixed[: len(route.rail) - 1])
        self.tool = [
            capsule(a, b, rad) for a, b, rad, _ in route.layout.tool_capsules()
        ]
        if route.layout.grip_shape == "box":
            layout = route.layout
            center = [
                layout.loop_radius_m + layout.stem_length_m + layout.grip_length_m / 2,
                0,
                0,
            ]
            self.tool[-1] = fcl.CollisionObject(
                fcl.Box(
                    layout.grip_length_m,
                    2 * layout.grip_radius_m,
                    2 * layout.grip_half_thickness_m,
                ),
                fcl.Transform(
                    Rotation.from_euler(
                        "x", layout.grip_flat_roll_deg, degrees=True
                    ).as_matrix(),
                    center,
                ),
            )
        # Transform each entire local capsule pose when moving the wand.
        self.tool_transforms = [
            (o.getRotation().copy(), o.getTranslation().copy()) for o in self.tool
        ]
        self.tool_manager = manager(self.tool)
        self.metal_manager = manager(self.tool[:-1])
        m = kin.model
        self.geoms = []
        for i in range(m.ngeom):
            if not (m.geom_contype[i] or m.geom_conaffinity[i]):
                continue
            if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_MESH:
                mesh = m.mesh(m.geom_dataid[i])
                v = m.mesh_vert[mesh.vertadr[0] : mesh.vertadr[0] + mesh.vertnum[0]]
                hull = trimesh.convex.convex_hull(v)
                shape = fcl.Convex(
                    hull.vertices,
                    len(hull.faces),
                    np.column_stack([np.full(len(hull.faces), 3), hull.faces]).ravel(),
                )
                vertices = hull.vertices
            elif m.geom_type[i] == mujoco.mjtGeom.mjGEOM_BOX:
                size = m.geom_size[i]
                shape = fcl.Box(*(2 * size))
                vertices = trimesh.bounds.corners(np.array([-size, size]))
            else:
                raise ValueError(f"Unsupported robot geometry {m.geom_type[i]}")
            self.geoms.append(
                (i, m.body(m.geom_bodyid[i]).name, fcl.CollisionObject(shape), vertices)
            )
        self.robot = manager([g[2] for g in self.geoms])
        self.nonfinger = manager(
            [g[2] for g in self.geoms if g[1] not in ("left_finger", "right_finger")]
        )

    @staticmethod
    def distance(a, b, signed=False):
        # Ask GJK for separation first. Signed-distance EPA can stall for
        # deeply intersecting trial arm poses; collision contacts provide the
        # penetration cost without that signed-distance fallback.
        result = fcl.DistanceData(request=fcl.DistanceRequest())
        a.distance(b, result, fcl.defaultDistanceCallback)
        minimum = float(result.result.min_distance)
        if signed and minimum <= 0:
            # The default manager distance callback stops on the first overlap.
            # Its almost-zero depth can hide a deeper neighbouring capsule and
            # gives constrained IK an inconsistent penetration gradient. Visit
            # ALL overlapping AABB pairs for a meaningful signed search cost.
            depths = [0.0]

            def overlap_distance(first, second, values):
                pair = fcl.CollisionResult()
                fcl.collide(
                    first,
                    second,
                    fcl.CollisionRequest(num_max_contacts=32, enable_contact=True),
                    pair,
                )
                values.extend(-float(c.penetration_depth) for c in pair.contacts)
                return False

            a.collide(b, depths, overlap_distance)
            minimum = min(depths)
        return minimum

    def check(self, arm, p, r):
        self.kin.forward(arm)
        m, d = self.kin.model, self.kin.data
        failures = []
        for contact in d.contact:
            if contact.dist < -0.00005:
                failures.append(
                    dict(
                        pair="robot_self",
                        depth=float(-contact.dist),
                        links=[
                            m.body(m.geom_bodyid[i]).name
                            for i in (contact.geom1, contact.geom2)
                        ],
                    )
                )
        for i, name, obj, vertices in self.geoms:
            rot = d.geom_xmat[i].reshape(3, 3)
            pos = d.geom_xpos[i] + self.kin.mount
            obj.setTransform(fcl.Transform(rot, pos))
            low = (vertices @ rot.T + pos)[:, 2].min()
            if name != "link0" and low < self.kin.mount[2] - 0.00005:
                failures.append(
                    dict(pair="table/" + name, depth=float(self.kin.mount[2] - low))
                )
        self.robot.update()
        self.nonfinger.update()
        for obj, (rot, pos) in zip(self.tool, self.tool_transforms):
            obj.setTransform(fcl.Transform(r.as_matrix() @ rot, p + r.apply(pos)))
        self.tool_manager.update()
        self.metal_manager.update()
        distances = {
            name: self.distance(a, b, self.signed_distance)
            for name, a, b in [
                ("robot_fixture", self.robot, self.fixed_manager),
                ("nonfinger_tool", self.nonfinger, self.tool_manager),
                ("robot_metal", self.robot, self.metal_manager),
            ]
        }
        for name, value in distances.items():
            if value < 0.0005:
                failures.append(dict(pair=name, clearance_m=value))
        return failures, distances


def plan(output, seed_plan=None, continue_ik=False):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    cfg = config()
    if seed_plan:
        source = json.loads(Path(seed_plan).read_text())
        cfg.task.origin_xy_m = source["origin"][:2]
        cfg.task.yaw_deg = source["yaw"]
        cfg.task.geometry = source["layout"]
        cfg.task.variant = source["layout"]["template_id"]
        cfg.robot_demo.grasp_roll_deg = source["grip_roll_deg"]
        cfg.robot_demo.grasp_tilt_deg = 0.0
        cfg.robot_demo.grip_inset_m = source.get(
            "grip_inset_m", cfg.robot_demo.grip_inset_m
        )
        physics = source.get("physics", {})
        if set(physics) - {"constraint_timeconst", "max_contacts"}:
            raise ValueError("Unsupported seed contact settings")
        if (
            "constraint_timeconst" in physics
            and not 0 < float(physics["constraint_timeconst"]) <= 0.01
        ) or (
            "max_contacts" in physics
            and (
                not isinstance(physics["max_contacts"], int)
                or physics["max_contacts"] < 128
            )
        ):
            raise ValueError("Invalid seed contact settings")
        for name, value in physics.items():
            OmegaConf.update(cfg, "task.physics." + name, value, force_add=True)
        for name in (
            "instance_id",
            "release_progress",
            "plan_samples",
            "retreat_height_m",
            "placement_contact_confirmation_descent_m",
        ):
            if name in source:
                OmegaConf.update(
                    cfg, "robot_demo." + name, source[name], force_add=True
                )
        if cfg.task.geometry.get("supported_endpoints", False):
            if not source.get("supported_pick_place"):
                raise ValueError(
                    "Supported seeds must include approach, pickup, placement and retreat"
                )
            OmegaConf.update(
                cfg, "robot_demo.supported_pick_place", True, force_add=True
            )
        OmegaConf.update(
            cfg, "robot_demo.initial_arm_qpos", source["arm_qpos"][0], force_add=True
        )
        shutil.copy2(seed_plan, output / "seed_plan.json")
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    route, geometry = generate_assets(
        output / "assets",
        BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True)),
    )
    proof = verify_route(route)
    for name in ("wire.urdf", "wand.urdf"):
        # MuJoCo does not read GLB visuals. Validate the unchanged collision,
        # inertia and joint definitions independently of the rendering format.
        body = ET.parse(output / "assets" / name)
        for link in body.findall("link"):
            for visual in link.findall("visual"):
                link.remove(visual)
        mujoco.MjModel.from_xml_string(ET.tostring(body.getroot(), encoding="unicode"))
    save(output / "clearance.json", proof)
    if not proof["passed"]:
        raise ValueError("Compact tool path does not fit")
    kin = Kinematics(cfg)
    origin = np.r_[cfg.task.origin_xy_m, float(cfg.env.frames.table_surface.origin[2])]
    world = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    if seed_plan:
        hr = Rotation.from_quat(source["hand_rotation_xyzw"])
        hp = np.array(source["hand_offset"])
        seed = np.array(source["arm_qpos"][0])
    else:
        tilt = np.deg2rad(cfg.robot_demo.grasp_tilt_deg)
        approach = np.array([-np.cos(tilt), 0, np.sin(tilt)])
        closing = np.array([0, 1, 0])
        hr = Rotation.from_rotvec(
            [np.deg2rad(cfg.robot_demo.grasp_roll_deg), 0, 0]
        ) * Rotation.from_matrix(
            np.column_stack([np.cross(closing, approach), closing, approach])
        )
        hp = np.array(
            [
                route.layout.loop_radius_m
                + route.layout.stem_length_m
                + cfg.robot_demo.grip_inset_m,
                0,
                0,
            ]
        ) - hr.apply(kin.pad_offset)
        seed = np.asarray(
            cfg.robot_demo.get("initial_arm_qpos", kin.q[:7]), dtype=float
        )
    audit = RobotAudit(kin, route, origin, world)
    rows = []
    failure = None
    mins = {}
    peak_pe = peak_re = 0.0
    previous_pose_fallbacks = []
    authored_guide_fallbacks = []
    release_progress = float(cfg.robot_demo.get("release_progress", 1.0))
    tail = route.positions[route.progress >= release_progress]
    terminal_post = (
        len(tail) > 0
        and np.max(np.linalg.norm(tail[:, :2] - route.rail[-1, :2], axis=1)) < 0.001
        and np.all(np.diff(tail[:, 2]) <= 1e-8)
    )
    if not 0 < release_progress <= 1 or (release_progress < 1 and not terminal_post):
        raise ValueError(
            "Release may precede the witness end only on the final straight downward post"
        )
    for i, u in enumerate(
        np.linspace(0, release_progress, int(cfg.robot_demo.plan_samples))
    ):
        p, q = route.pose(float(u))
        p = origin + world.apply(p)
        r = world * Rotation.from_quat(q[[1, 2, 3, 0]])
        guide = seed
        if seed_plan:
            source_arms = np.asarray(source["arm_qpos"])
            guide = np.array(
                [np.interp(u, source["progress"], source_arms[:, j]) for j in range(7)]
            )
        arm, pe, re = kin.solve(
            p + r.apply(hp),
            r * hr,
            seed if continue_ik and i else guide,
            attempts=8 if i == 0 else 1,
            max_nfev=40 if continue_ik and i else 160,
        )
        jump = float(np.max(abs(arm - seed)))
        bad, dist = audit.check(arm, p, r)
        if continue_ik and i and (pe > 1e-5 or re > 1e-4 or jump > 0.35 or bad):
            arm, pe, re = kin.solve(p + r.apply(hp), r * hr, guide)
            jump = float(np.max(abs(arm - seed)))
            bad, dist = audit.check(arm, p, r)
            authored_guide_fallbacks.append(float(u))
        if i and (pe > 1e-5 or re > 1e-4 or jump > 0.35 or bad):
            # A remapped guide may converge slowly near a singularity or pick
            # a different redundant posture. Retry from the last accepted pose
            # under the SAME joint, residual, continuity and collision limits.
            original = dict(
                position_error=pe, rotation_error=re, jump=jump, contacts=bad
            )
            fallback, fpe, fre = kin.solve(p + r.apply(hp), r * hr, seed, max_nfev=600)
            fjump = float(np.max(abs(fallback - seed)))
            fbad, fdist = audit.check(fallback, p, r)
            if fpe <= 1e-5 and fre <= 1e-4 and fjump <= 0.35 and not fbad:
                arm, pe, re, jump, bad, dist = fallback, fpe, fre, fjump, fbad, fdist
                previous_pose_fallbacks.append(
                    dict(progress=float(u), rejected_guide=original)
                )
            else:
                kin.forward(arm)
        peak_pe = max(peak_pe, pe)
        peak_re = max(peak_re, re)
        if pe > 1e-5 or re > 1e-4 or (i and jump > 0.35):
            failure = dict(
                index=i,
                progress=u,
                reason="ik",
                position_error=pe,
                rotation_error=re,
                jump=jump,
            )
            break
        for name, value in dist.items():
            mins[name] = min(mins.get(name, float("inf")), value)
        if bad:
            failure = dict(index=i, progress=u, reason="collision", contacts=bad)
            break
        rows.append(
            dict(
                progress=float(u),
                arm_qpos=arm.tolist(),
                position_m=p.tolist(),
                quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
            )
        )
        seed = arm
        if i % 100 == 0:
            print(
                f"plan {i}/{cfg.robot_demo.plan_samples}, clearance={dist}", flush=True
            )
    result = dict(
        passed=failure is None,
        task_id="buzz_wire_3d",
        variant=str(cfg.robot_demo.instance_id),
        failure=failure,
        frames=rows,
        hand_offset=hp.tolist(),
        hand_rotation_xyzw=hr.as_quat().tolist(),
        pad_offset=kin.pad_offset.tolist(),
        minimum_robot_clearances_m=mins,
        maximum_ik_position_error_m=peak_pe,
        maximum_ik_orientation_error_rad=peak_re,
        previous_pose_fallbacks=previous_pose_fallbacks,
        authored_guide_fallbacks=authored_guide_fallbacks,
        guide_strategy="previous_pose_first" if continue_ik else "authored_guide_first",
        geometry=geometry,
        model_qpos=kin.q.tolist(),
        robot_asset_sha256=sha(kin.asset),
        release_progress=release_progress,
        remaining_path_is_terminal_post=bool(terminal_post),
        scope="Dense collision-checked robot traversal through every maze bend, ending at the straight finish post for gravity release; live dynamics checks still required",
    )
    if route.layout.supported_endpoints and result["passed"]:
        from .supported_plan import verify_supported_paths

        result["supported_pick_place"] = source["supported_pick_place"]
        result["scope"] = (
            "Complete supported pickup, maze traversal and placement guide; fresh physical validation required"
        )
        result["passed"] = False
        save(output / "plan.json", result)
        result["passed"] = verify_supported_paths(output)["passed"]
    save(output / "plan.json", result)
    shutil.copy2(__file__, output / "plan_source.py")
    implementation = output / "implementation"
    implementation.mkdir()
    for name in (
        "geometry.py",
        "appearance.py",
        "preview.py",
        "scene.py",
        "templates.py",
        "verification.py",
        "robot_plan.py",
        "family_geometry.py",
        "family_plan.py",
        "supports.py",
        "supported_plan.py",
    ):
        shutil.copy2(Path(__file__).with_name(name), implementation / name)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("frames", "geometry", "model_qpos", "supported_pick_place")
            },
            indent=2,
        ),
        flush=True,
    )
    if not result["passed"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-plan", type=Path)
    parser.add_argument("--continue-ik", action="store_true")
    args = parser.parse_args()
    plan(args.output, args.seed_plan, args.continue_ik)


if __name__ == "__main__":
    main()
