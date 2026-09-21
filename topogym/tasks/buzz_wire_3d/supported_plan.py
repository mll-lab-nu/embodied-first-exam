"""Extend a certified maze traversal with supported pickup and placement."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from .geometry import BuzzWireLayout, generate_assets
from .physics import save
from .robot_plan import Kinematics, RobotAudit
from .supports import endpoint_pose
from .verification import verify_route


def build(source, output, elevation=.025, mount_height=.044, shift_x=-.06, raise_maze=True):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cfg = OmegaConf.load(source / "config.yaml")
    old = json.loads((source / "plan.json").read_text())
    if not old["passed"] or old["release_progress"] != 1:
        raise ValueError("A complete maze IK plan is required")
    layout = replace(BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry)),
                     base_elevation_m=elevation, supported_endpoints=True,
                     mount_size_m=(.030, .030, mount_height),
                     end_stop_radius_m=float(np.linalg.norm([.015, .015, mount_height / 2]) + .0001))
    if raise_maze:
        if layout.template_id != "authored_multistage_v1":
            raise ValueError("An authored maze is required for rigid elevation")
        controls = np.array(layout.authored_controls_m)
        controls[:, 2] += elevation
        layout = replace(layout, authored_controls_m=controls.tolist())
    cfg.task.origin_xy_m[0] += shift_x
    cfg.task.geometry = asdict(layout)
    cfg.robot_demo.instance_id = str(cfg.robot_demo.instance_id).replace("v2", "supported_v3")
    OmegaConf.update(cfg, "robot_demo.supported_pick_place", True, force_add=True)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    route, geometry = generate_assets(output / "assets", layout)
    proof = verify_route(route)
    save(output / "clearance.json", proof)
    if not proof["passed"]:
        raise ValueError("Raised supports obstruct the maze traversal")
    kin = Kinematics(cfg)
    origin = np.r_[cfg.task.origin_xy_m, float(cfg.env.frames.table_surface.origin[2])]
    world = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    audit = RobotAudit(kin, route, origin, world)
    hp = np.array(old["hand_offset"])
    hr = Rotation.from_quat(old["hand_rotation_xyzw"])

    def pose(row):
        return np.array(row["position_m"]), Rotation.from_quat(np.array(row["quaternion_wxyz"])[[1, 2, 3, 0]])

    def row(p, r, arm):
        return dict(position_m=p.tolist(), quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(), arm_qpos=arm.tolist())

    def solve_path(waypoints, seed, held=True, resting=None):
        rows = []
        for index, (p, r) in enumerate(waypoints):
            arm, pe, re = kin.solve(p + r.apply(hp), r * hr, seed, max_nfev=400)
            tp, tr = (p, r) if held else resting
            bad, _ = audit.check(arm, tp, tr)
            if pe > 1e-5 or re > 1e-4 or bad or (rows and np.max(abs(arm-seed)) > .2):
                save(output / "failed_path.json", dict(index=index, pose=row(p, r, arm), position_error=pe, rotation_error=re, contacts=bad, accepted=rows))
                raise ValueError(f"Endpoint IK failed at {index}: {pe=}, {re=}, {bad=}")
            rows.append(row(p, r, arm))
            seed = arm
        return rows

    def interpolate(waypoints):
        result = []
        for (p0, r0), (p1, r1) in zip(waypoints[:-1], waypoints[1:]):
            count = max(2, int(np.ceil(np.linalg.norm(p1-p0)/.001)), int(np.ceil((r0.inv()*r1).magnitude()/.012)))
            rot = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), r1.as_quat()]))
            result.extend((p0*(1-u)+p1*u, rot(u)) for u in np.linspace(0, 1, count, endpoint=False))
        return [*result, waypoints[-1]]

    # Re-audit all old arm samples against the new deck, feet, and saddles.
    minimum = {}
    previous = None
    for i, frame in enumerate(old["frames"]):
        p, r = pose(frame)
        p += [shift_x, 0, elevation if raise_maze else 0]
        arm, pe, re = kin.solve(p+r.apply(hp), r*hr, np.array(frame["arm_qpos"]))
        if (pe > 1e-5 or re > 1e-4) and previous is not None:
            arm, pe, re = kin.solve(p+r.apply(hp), r*hr, previous, max_nfev=600)
        if pe > 1e-5 or re > 1e-4:
            raise ValueError(f"Elevated maze IK failed at {i}: {pe=}, {re=}")
        bad, distances = audit.check(arm, p, r)
        if bad:
            raise ValueError(f"Changed fixture intersects maze IK at {i}: {bad}")
        frame.update(row(p, r, arm))
        if previous is not None and np.max(abs(arm-previous)) > .2:
            raise ValueError(f"Discontinuous maze IK at {i}")
        previous = arm
        for name, value in distances.items():
            minimum[name] = min(minimum.get(name, float("inf")), value)
        if i % 2000 == 0:
            print("maze fixture audit", i, len(old["frames"]), flush=True)
    paths = {}
    for end, name in ((0, "pickup"), (1, "placement")):
        p, r = endpoint_pose(route, end)
        rest = origin + world.apply(p), world * r
        top = pose(old["frames"][0 if end == 0 else -1])
        upright = (np.r_[rest[0][:2], top[0][2]], rest[1])
        waypoints = interpolate([top, upright, rest])
        down = solve_path(waypoints, np.array(old["frames"][0 if end == 0 else -1]["arm_qpos"]))
        paths[name] = list(reversed(down)) if end == 0 else down
        save(output / f"{name}.json", paths[name])
        print(name, len(down), flush=True)
    rest = pose(paths["pickup"][0])
    far = (rest[0] + rest[1].apply([.075, 0, 0]), rest[1])
    kin.set_gap(.015)
    reverse_approach = solve_path(interpolate([rest, far]), np.array(paths["pickup"][0]["arm_qpos"]), held=False, resting=rest)
    paths["approach"] = list(reversed(reverse_approach))
    # The arm starts open, separated from the supported wand; no pregrasp.
    paths["initial_arm_qpos"] = paths["approach"][0]["arm_qpos"]
    paths["open_half_gap_m"] = .015
    endrest = pose(paths["placement"][-1])
    far = (endrest[0] + endrest[1].apply([.075, 0, 0]), endrest[1])
    paths["retreat"] = solve_path(interpolate([endrest, far]), np.array(paths["placement"][-1]["arm_qpos"]), held=False, resting=endrest)
    old.update(geometry=geometry, supported_pick_place=paths,
               minimum_robot_clearances_m=minimum, variant=str(cfg.robot_demo.instance_id),
               scope="Full maze plus supported pickup and controlled placement; dynamics validation still required")
    save(output / "plan.json", old)
    implementation = output / "implementation"
    implementation.mkdir()
    for name in ("supported_plan.py", "supports.py", "geometry.py", "appearance.py", "scene.py", "verification.py", "robot_plan.py"):
        shutil.copy2(Path(__file__).with_name(name), implementation / name)
    save(output / "source.json", dict(source=str(source), elevation_m=elevation, mount_height_m=mount_height,
                                      origin_x_shift_m=shift_x, maze_rigidly_elevated=raise_maze))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--elevation", type=float, default=.025)
    p.add_argument("--mount-height", type=float, default=.044)
    p.add_argument("--shift-x", type=float, default=-.06)
    p.add_argument("--keep-maze-height", action="store_true")
    a = p.parse_args()
    build(a.source, a.output, a.elevation, a.mount_height, a.shift_x, not a.keep_maze_height)


if __name__ == "__main__":
    main()
