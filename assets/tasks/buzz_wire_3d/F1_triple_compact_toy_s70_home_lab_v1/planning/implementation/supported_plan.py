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
from .verification import ClearanceOracle, verify_route


def verify_supported_paths(plan_dir):
    """Certify conductive-wire clearance; audit intentional wooden-seat contact separately."""
    from .geometry import SpatialWire

    plan_dir = Path(plan_dir)
    cfg = OmegaConf.load(plan_dir / "config.yaml")
    plan = json.loads((plan_dir / "plan.json").read_text())
    route = SpatialWire(BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry)))
    kin = Kinematics(cfg)
    origin = np.r_[cfg.task.origin_xy_m, cfg.env.frames.table_surface.origin[2]]
    world = Rotation.from_euler("z", cfg.task.yaw_deg, degrees=True)
    audit = RobotAudit(kin, route, origin, world)
    wire_oracle = ClearanceOracle(route, spacing=route.layout.clearance_cover_m)
    wire_oracle.boxes = []  # block mounts are already excluded from fixed capsules
    wire_oracle.spheres = []
    paths = plan["supported_pick_place"]
    hp, hr = (
        np.array(plan["hand_offset"]),
        Rotation.from_quat(plan["hand_rotation_xyzw"]),
    )

    def pose(row):
        return np.array(row["position_m"]), Rotation.from_quat(
            np.array(row["quaternion_wxyz"])[[1, 2, 3, 0]]
        )

    def same_pose(a, b):
        pa, ra = pose(a)
        pb, rb = pose(b)
        return np.linalg.norm(pa - pb) < 1e-6 and (ra * rb.inv()).magnitude() < 1e-5

    for end, phase in ((0, "pickup"), (1, "placement")):
        local_p, local_r = endpoint_pose(route, end)
        p, r = pose(paths[phase][0 if end == 0 else -1])
        if (
            np.linalg.norm(p - origin - world.apply(local_p)) > 1e-6
            or (r * (world * local_r).inv()).magnitude() > 1e-5
        ):
            raise ValueError(
                f"{phase} rest pose differs from the current wooden support"
            )
        join = paths[phase][-1 if end == 0 else 0]
        maze = plan["frames"][0 if end == 0 else -1]
        if (
            not same_pose(join, maze)
            or np.max(abs(np.array(join["arm_qpos"]) - maze["arm_qpos"])) > 0.02
        ):
            raise ValueError(f"{phase} no longer joins the current maze IK")
    if not same_pose(paths["approach"][-1], paths["pickup"][0]) or not same_pose(
        paths["retreat"][0], paths["placement"][-1]
    ):
        raise ValueError("Free arm motions do not join the grasp/release poses")
    for a, b in (
        (paths["approach"][-1], paths["pickup"][0]),
        (paths["placement"][-1], paths["retreat"][0]),
    ):
        if np.max(abs(np.array(a["arm_qpos"]) - b["arm_qpos"])) > 0.02:
            raise ValueError("Grasp/release joins use different arm branches")
    first_phase = "home_approach" if paths.get("home_approach") else "approach"
    if first_phase == "home_approach":
        if not np.allclose(
            paths["initial_arm_qpos"],
            cfg.robot_control.home.qpos[:7],
            atol=1e-8,
            rtol=0,
        ):
            raise ValueError("Home guide must start at the configured default arm pose")
        if not same_pose(
            paths["home_approach"][-1], paths["approach"][0]
        ) or not np.allclose(
            paths["home_approach"][-1]["arm_qpos"],
            paths["approach"][0]["arm_qpos"],
            atol=1e-8,
            rtol=0,
        ):
            raise ValueError("Home motion does not join the supported approach")
    if not np.allclose(
        paths["initial_arm_qpos"], paths[first_phase][0]["arm_qpos"], atol=1e-8
    ):
        raise ValueError("Initial arm pose differs from the approach")
    summaries = {}
    phases = (["home_approach"] if first_phase == "home_approach" else []) + [
        "approach",
        "pickup",
        "placement",
        "retreat",
    ]
    for phase in phases:
        rows = paths[phase]
        held = phase in ("pickup", "placement")
        kin.set_gap(
            paths.get("home_motion_half_gap_m", paths.get("home_open_half_gap_m"))
            if phase == "home_approach"
            else route.layout.grip_radius_m
            if held
            else paths["open_half_gap_m"]
        )
        ps = np.array([row["position_m"] for row in rows])
        rs = Rotation.from_quat(
            np.array([row["quaternion_wxyz"] for row in rows])[:, [1, 2, 3, 0]]
        )
        wire_bound = None
        if held:
            clearances = np.array(
                [
                    wire_oracle.clearance(
                        world.inv().apply(p - origin), world.inv() * r
                    )
                    for p, r in zip(ps, rs)
                ]
            )
            displacements = np.linalg.norm(
                np.diff(ps, axis=0), axis=1
            ) / 2 + 2 * wire_oracle.radius * np.sin(
                (rs[:-1].inv() * rs[1:]).magnitude() / 4
            )
            wire_bound = float(
                np.min(np.minimum(clearances[:-1], clearances[1:]) - displacements)
            )
        rest = pose(
            paths["pickup"][0]
            if phase in ("home_approach", "approach")
            else paths["placement"][-1]
        )
        fixture_min = float("inf")
        previous = None
        for row, p, r in zip(rows, ps, rs):
            arm = np.array(row["arm_qpos"])
            if (
                not np.isfinite(arm).all()
                or np.any(arm < kin.limits[:, 0])
                or np.any(arm > kin.limits[:, 1])
            ):
                raise ValueError(f"{phase} exceeds physical joint limits")
            fk_p, fk_r = kin.forward(arm)
            if (
                np.linalg.norm(fk_p - p - r.apply(hp)) > 1e-5
                or (fk_r * (r * hr).inv()).magnitude() > 1e-4
            ):
                raise ValueError(f"{phase} has stale endpoint IK")
            if previous is not None and np.max(abs(arm - previous)) > 0.2:
                raise ValueError(f"{phase} has a discontinuous arm guide")
            previous = arm
            tool_p, tool_r = (p, r) if held else rest
            bad, _ = audit.check(arm, tool_p, tool_r)
            if bad:
                raise ValueError(f"{phase} robot audit failed: {bad}")
            fixture_min = min(
                fixture_min,
                audit.distance(audit.tool_manager, audit.fixed_manager, True),
            )
        summaries[phase] = dict(
            samples=len(rows),
            continuous_wire_clearance_lower_bound_m=wire_bound,
            sampled_tool_fixture_separation_m=fixture_min,
            passed=(wire_bound is None or wire_bound > 0.001)
            and fixture_min >= -0.00005,
        )
    result = dict(
        passed=all(row["passed"] for row in summaries.values()),
        phases=summaries,
        scope="Continuous capsule-cover clearance against conductive wire; exact fixture collisions sampled at every endpoint-motion knot. Wooden seat contact is intentional; live dynamics verifies placement.",
    )
    save(plan_dir / "supported_motion_clearance.json", result)
    return result


def refresh_supported_plan(source, output):
    """Rebuild fixtures and re-audit a saved complete guide; no dynamics inherited."""
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cfg = OmegaConf.load(source / "config.yaml")
    plan = json.loads((source / "plan.json").read_text())
    if not plan["passed"] or not plan.get("supported_pick_place"):
        raise ValueError("Need a complete supported motion guide")
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    route, geometry = generate_assets(
        output / "assets", BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry))
    )
    proof = verify_route(route)
    save(output / "clearance.json", proof)
    if not proof["passed"]:
        raise ValueError("Changed fixtures obstruct the maze")
    kin = Kinematics(cfg)
    origin = np.r_[cfg.task.origin_xy_m, cfg.env.frames.table_surface.origin[2]]
    world = Rotation.from_euler("z", cfg.task.yaw_deg, degrees=True)
    audit = RobotAudit(kin, route, origin, world)
    for i, row in enumerate(plan["frames"]):
        p = np.array(row["position_m"])
        r = Rotation.from_quat(np.array(row["quaternion_wxyz"])[[1, 2, 3, 0]])
        bad, _ = audit.check(np.array(row["arm_qpos"]), p, r)
        if bad:
            raise ValueError(f"Changed fixture intersects maze at {i}: {bad}")
    plan.update(passed=False, geometry=geometry)
    save(output / "plan.json", plan)
    endpoint = verify_supported_paths(output)
    if not endpoint["passed"]:
        raise ValueError(f"Changed fixture intersects pickup or placement: {endpoint}")
    plan["passed"] = True
    save(output / "plan.json", plan)
    shutil.copytree(
        Path(__file__).parent,
        output / "implementation",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    save(
        output / "source.json",
        dict(source=str(source.resolve()), physical_execution_verified=False),
    )


def solve_audited(kin, audit, target_p, target_r, seed, tool_p, tool_r, previous=None):
    """Keep the hand pose exact while using Panda's redundancy to avoid obstacles."""
    seed = np.clip(seed, kin.limits[:, 0] + 1e-5, kin.limits[:, 1] - 1e-5)
    arm, pe, re = kin.solve(target_p, target_r, seed, max_nfev=160)

    def check(q, pos_error, rot_error):
        bad, distances = audit.check(q, tool_p, tool_r)
        good = (
            pos_error <= 1e-5
            and rot_error <= 1e-4
            and not bad
            and (previous is None or np.max(abs(q - previous)) <= 0.18)
        )
        return good, bad, distances

    good, bad, distances = check(arm, pe, re)
    if good:
        return arm, pe, re, bad, distances
    p0, r0 = kin.forward(arm)
    jac = np.zeros((6, 7))
    for j in range(7):
        perturbed = arm.copy()
        perturbed[j] += 1e-5
        p1, r1 = kin.forward(perturbed)
        jac[:, j] = np.r_[20 * (p1 - p0), (r1 * r0.inv()).as_rotvec()] / 1e-5
    direction = np.linalg.svd(jac)[2][-1]
    direction /= np.max(abs(direction))
    for amount in [
        0.001,
        -0.001,
        0.002,
        -0.002,
        0.005,
        -0.005,
        0.01,
        -0.01,
        0.02,
        -0.02,
        0.04,
        -0.04,
        0.08,
        -0.08,
        0.14,
        -0.14,
        0.22,
        -0.22,
    ]:
        trial = np.clip(
            arm + amount * direction, kin.limits[:, 0] + 1e-5, kin.limits[:, 1] - 1e-5
        )
        candidate, cpe, cre = kin.solve(target_p, target_r, trial, max_nfev=400)
        good, cbad, cdist = check(candidate, cpe, cre)
        if good:
            return candidate, cpe, cre, cbad, cdist
    return arm, pe, re, bad, distances


def measured_retreat(cfg, plan, robot_qpos, tool_p, tool_r):
    """Continue the released arm's measured IK branch along the authored retreat.

    Grasp feedback can migrate along Panda's redundant joint manifold. Returning
    directly to the nominal joint guide would jump branches despite a matching
    hand pose. Translate the guide from the measured hand, solve continuously,
    and audit it against the stationary released tool before moving.
    """
    from .geometry import SpatialWire

    kin = Kinematics(cfg)
    kin.q = np.array(robot_qpos, dtype=float).copy()
    kin.set_gap(float(plan["supported_pick_place"]["open_half_gap_m"]))
    route = SpatialWire(BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry)))
    origin = np.r_[cfg.task.origin_xy_m, cfg.env.frames.table_surface.origin[2]]
    world = Rotation.from_euler("z", cfg.task.yaw_deg, degrees=True)
    audit = RobotAudit(kin, route, origin, world)
    seed = np.array(robot_qpos[:7], dtype=float)
    actual_p, actual_r = kin.forward(seed)
    hp = np.array(plan["hand_offset"])
    hr = Rotation.from_quat(plan["hand_rotation_xyzw"])
    guide = plan["supported_pick_place"]["retreat"]
    first_r = Rotation.from_quat(np.array(guide[0]["quaternion_wxyz"])[[1, 2, 3, 0]])
    first_p = np.array(guide[0]["position_m"]) + first_r.apply(hp)
    correction_r = (first_r * hr).inv() * actual_r
    rows = []
    clearance = float("inf")
    for i, row in enumerate(guide):
        r = Rotation.from_quat(np.array(row["quaternion_wxyz"])[[1, 2, 3, 0]])
        target_p = actual_p + np.array(row["position_m"]) + r.apply(hp) - first_p
        target_r = r * hr * correction_r
        q, pe, re, bad, _ = solve_audited(
            kin, audit, target_p, target_r, seed, tool_p, tool_r, previous=seed
        ) if i else (seed.copy(), 0., 0., [], {})
        if pe > 1e-5 or re > 1e-4 or bad or np.max(abs(q - seed)) > 0.18:
            raise ValueError(f"Measured retreat IK rejected at {i}: {bad}, {pe=}, {re=}")
        for arm in np.linspace(seed, q, max(2, int(np.ceil(np.max(abs(q-seed))/.01))+1)):
            bad, _ = audit.check(arm, tool_p, tool_r)
            separation = audit.distance(audit.robot, audit.tool_manager)
            if bad or separation < 0.001:
                raise ValueError(f"Measured retreat clearance rejected at {i}: {bad}, {separation=}")
            clearance = min(clearance, separation)
        ghost_r = target_r * hr.inv()
        rows.append(dict(arm_qpos=q.tolist(), position_m=(target_p-ghost_r.apply(hp)).tolist(),
                         quaternion_wxyz=ghost_r.as_quat()[[3,0,1,2]].tolist()))
        seed = q
    return dict(passed=True, scope="Measured release branch, stationary tool, dense robot/fixture/self/tool audit",
                minimum_robot_tool_clearance_m=clearance, max_joint_sample_spacing_rad=.01,
                initial_arm_qpos=list(robot_qpos[:7]), tool_position_m=np.asarray(tool_p).tolist(),
                tool_quaternion_wxyz=tool_r.as_quat()[[3,0,1,2]].tolist(), frames=rows)


def build(
    source,
    output,
    elevation=0.025,
    mount_height=0.044,
    shift_x=-0.06,
    raise_maze=True,
    rest_pitch=15.0,
    maze_frames=None,
    finish_lift=0.0,
    keep_finish_orientation=False,
    shift_y=0.0,
    reference_seeds=False,
):
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cfg = OmegaConf.load(source / "config.yaml")
    old = json.loads((source / "plan.json").read_text())
    if not old["passed"] or old["release_progress"] != 1:
        raise ValueError("A complete maze IK plan is required")
    layout = replace(
        BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry)),
        base_elevation_m=elevation,
        supported_endpoints=True,
        rest_handle_pitch_deg=rest_pitch,
        mount_size_m=(0.030, 0.030, mount_height),
        end_stop_radius_m=float(
            np.linalg.norm([0.015, 0.015, mount_height / 2]) + 0.0001
        ),
    )
    if raise_maze:
        if layout.template_id != "authored_multistage_v1":
            raise ValueError("An authored maze is required for rigid elevation")
        controls = np.array(layout.authored_controls_m)
        controls[:, 2] += elevation
        layout = replace(layout, authored_controls_m=controls.tolist())
    if keep_finish_orientation:
        finish = Rotation.from_quat(
            np.array(old["frames"][-1]["quaternion_wxyz"])[[1, 2, 3, 0]]
        )
        world = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
        layout = replace(
            layout,
            rest_finish_quaternion_wxyz=tuple(
                (world.inv() * finish).as_quat()[[3, 0, 1, 2]].tolist()
            ),
            finish_cradle_mount_clearance_m=0.0,
            finish_cradle_neck_pair=False,
        )
        OmegaConf.update(
            cfg,
            "robot_demo.placement_contact_confirmation_descent_m",
            0.000025,
            force_add=True,
        )
    cfg.task.origin_xy_m[0] += shift_x
    cfg.task.origin_xy_m[1] += shift_y
    cfg.task.geometry = asdict(layout)
    cfg.robot_demo.instance_id = str(cfg.robot_demo.instance_id).replace(
        "v2", "supported_v3"
    )
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
        return np.array(row["position_m"]), Rotation.from_quat(
            np.array(row["quaternion_wxyz"])[[1, 2, 3, 0]]
        )

    def row(p, r, arm):
        return dict(
            position_m=p.tolist(),
            quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
            arm_qpos=arm.tolist(),
        )

    def solve_path(waypoints, seed, held=True, resting=None, relax_interior=False):
        rows = []

        def advance(p, r, depth=0, final=False):
            nonlocal seed
            tp, tr = (p, r) if held else resting
            arm, pe, re, bad, _ = solve_audited(
                kin,
                audit,
                p + r.apply(hp),
                r * hr,
                seed,
                tp,
                tr,
                seed if rows else None,
            )
            if (
                rows
                and np.max(abs(arm - seed)) > 0.18
                and not bad
                and pe <= 0.001
                and re <= 0.035
                and depth < 8
            ):
                p0, r0 = pose(rows[-1])
                mid_p = (p0 + p) / 2
                mid_r = r0 * Rotation.from_rotvec((r0.inv() * r).as_rotvec() / 2)
                advance(mid_p, mid_r, depth + 1)
                advance(p, r, depth + 1, final)
                return
            if relax_interior and not final and rows and (pe > 1e-5 or re > 1e-4):
                # The ring has orientation freedom on the straight final post.
                # Author a nearby reachable FK pose, with physical joint margin;
                # never label an approximate IK solution as the requested pose.
                candidate = np.clip(
                    arm, kin.limits[:, 0] + 0.005, kin.limits[:, 1] - 0.005
                )
                hand_p, hand_r = kin.forward(candidate)
                candidate_r = hand_r * hr.inv()
                candidate_p = hand_p - candidate_r.apply(hp)
                dp = np.linalg.norm(candidate_p - p)
                dr = (candidate_r * r.inv()).magnitude()
                candidate_bad, _ = audit.check(candidate, candidate_p, candidate_r)
                if (
                    dp <= 0.008
                    and dr <= 0.08
                    and not candidate_bad
                    and np.max(abs(candidate - seed)) <= 0.18
                ):
                    p, r, arm, pe, re, bad = (
                        candidate_p,
                        candidate_r,
                        candidate,
                        0.0,
                        0.0,
                        [],
                    )
            if (
                pe > 1e-5
                or re > 1e-4
                or bad
                or (rows and np.max(abs(arm - seed)) > 0.2)
            ):
                save(
                    output / "failed_path.json",
                    dict(
                        index=len(rows),
                        pose=row(p, r, arm),
                        position_error=pe,
                        rotation_error=re,
                        contacts=bad,
                        accepted=rows,
                    ),
                )
                raise ValueError(
                    f"Endpoint IK failed at {len(rows)}: {pe=}, {re=}, {bad=}"
                )
            rows.append(row(p, r, arm))
            seed = arm

        for index, (p, r) in enumerate(waypoints):
            advance(p, r, final=index == len(waypoints) - 1)
        return rows

    def interpolate(waypoints):
        result = []
        for (p0, r0), (p1, r1) in zip(waypoints[:-1], waypoints[1:]):
            count = max(
                2,
                int(np.ceil(np.linalg.norm(p1 - p0) / 0.001)),
                int(np.ceil((r0.inv() * r1).magnitude() / 0.012)),
            )
            rot = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), r1.as_quat()]))
            result.extend(
                (p0 * (1 - u) + p1 * u, rot(u))
                for u in np.linspace(0, 1, count, endpoint=False)
            )
        return [*result, waypoints[-1]]

    # Re-audit all old arm samples against the new deck, feet, and saddles.
    minimum = {}
    previous = None
    correction = np.zeros(7)
    cached = json.loads(Path(maze_frames).read_text()) if maze_frames else None
    if cached is not None and len(cached) != len(old["frames"]):
        raise ValueError("Cached maze sample count differs")
    for i, frame in enumerate(old["frames"]):
        p, r = pose(frame)
        p += [shift_x, shift_y, elevation if raise_maze else 0]
        original_arm = np.array(frame["arm_qpos"])
        if cached is None:
            arm, pe, re, bad, distances = solve_audited(
                kin,
                audit,
                p + r.apply(hp),
                r * hr,
                original_arm if reference_seeds else original_arm + correction,
                p,
                r,
                previous,
            )
        else:
            if abs(cached[i]["progress"] - frame["progress"]) > 1e-12:
                raise ValueError("Cached progress differs")
            arm = np.array(cached[i]["arm_qpos"])
            fk_p, fk_r = kin.forward(arm)
            pe = np.linalg.norm(fk_p - p - r.apply(hp))
            re = (fk_r * (r * hr).inv()).magnitude()
            bad, distances = audit.check(arm, p, r)
        if (
            pe > 1e-5
            or re > 1e-4
            or bad
            or (previous is not None and np.max(abs(arm - previous)) > 0.2)
        ):
            save(
                output / "failed_maze.json",
                dict(
                    index=i,
                    position_error_m=float(pe),
                    rotation_error_rad=float(re),
                    failures=bad,
                    candidate=row(p, r, arm),
                    previous_arm_qpos=None if previous is None else previous.tolist(),
                ),
            )
            save(output / "maze_partial.json", old["frames"][:i])
        if pe > 1e-5 or re > 1e-4:
            raise ValueError(f"Elevated maze IK failed at {i}: {pe=}, {re=}")
        if bad:
            raise ValueError(f"Changed fixture intersects maze IK at {i}: {bad}")
        frame.update(row(p, r, arm))
        if previous is not None and np.max(abs(arm - previous)) > 0.2:
            raise ValueError(f"Discontinuous maze IK at {i}")
        previous = arm
        correction = arm - original_arm
        for name, value in distances.items():
            minimum[name] = min(minimum.get(name, float("inf")), value)
        if i % 500 == 0:
            print("maze fixture audit", i, len(old["frames"]), flush=True)
    save(output / "maze_frames.json", old["frames"])
    paths = {}
    for end, name in ((0, "pickup"), (1, "placement")):
        p, r = endpoint_pose(route, end)
        rest = origin + world.apply(p), world * r
        top = pose(old["frames"][0 if end == 0 else -1])
        if end and finish_lift:
            lifted = top[0] + [0, 0, finish_lift]
            waypoints = interpolate([top, (lifted, top[1]), (lifted, rest[1]), rest])
        else:
            waypoints = interpolate([top, rest])
        down = solve_path(
            waypoints,
            np.array(old["frames"][0 if end == 0 else -1]["arm_qpos"]),
            relax_interior=bool(end),
        )
        paths[name] = list(reversed(down)) if end == 0 else down
        save(output / f"{name}.json", paths[name])
        print(name, len(down), flush=True)
    rest = pose(paths["pickup"][0])
    far = (rest[0] + rest[1].apply([0.05, 0, 0]) + [0, 0, 0.04], rest[1])
    kin.set_gap(0.015)
    reverse_approach = solve_path(
        interpolate([rest, far]),
        np.array(paths["pickup"][0]["arm_qpos"]),
        held=False,
        resting=rest,
    )
    paths["approach"] = list(reversed(reverse_approach))
    # The arm starts open, separated from the supported wand; no pregrasp.
    paths["initial_arm_qpos"] = paths["approach"][0]["arm_qpos"]
    paths["open_half_gap_m"] = 0.015
    endrest = pose(paths["placement"][-1])
    far = (endrest[0] + endrest[1].apply([0.05, 0, 0]) + [0, 0, 0.04], endrest[1])
    paths["retreat"] = solve_path(
        interpolate([endrest, far]),
        np.array(paths["placement"][-1]["arm_qpos"]),
        held=False,
        resting=endrest,
    )
    old.update(
        geometry=geometry,
        supported_pick_place=paths,
        minimum_robot_clearances_m=minimum,
        variant=str(cfg.robot_demo.instance_id),
        scope="Full maze plus supported pickup and controlled placement; dynamics validation still required",
    )
    old["passed"] = False
    save(output / "plan.json", old)
    endpoint_proof = verify_supported_paths(output)
    if not endpoint_proof["passed"]:
        raise ValueError(f"Supported endpoint motion is obstructed: {endpoint_proof}")
    old["passed"] = True
    save(output / "plan.json", old)
    implementation = output / "implementation"
    implementation.mkdir()
    for name in (
        "supported_plan.py",
        "supports.py",
        "geometry.py",
        "appearance.py",
        "scene.py",
        "verification.py",
        "robot_plan.py",
    ):
        shutil.copy2(Path(__file__).with_name(name), implementation / name)
    save(
        output / "source.json",
        dict(
            source=str(source),
            elevation_m=elevation,
            mount_height_m=mount_height,
            origin_x_shift_m=shift_x,
            origin_y_shift_m=shift_y,
            use_original_reference_seeds=reference_seeds,
            maze_rigidly_elevated=raise_maze,
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--elevation", type=float, default=0.025)
    p.add_argument("--mount-height", type=float, default=0.044)
    p.add_argument("--shift-x", type=float, default=-0.06)
    p.add_argument("--shift-y", type=float, default=0.0)
    p.add_argument("--reference-seeds", action="store_true")
    p.add_argument("--keep-maze-height", action="store_true")
    p.add_argument("--rest-pitch", type=float, default=15)
    p.add_argument("--maze-frames", type=Path)
    p.add_argument("--finish-lift", type=float, default=0)
    p.add_argument("--keep-finish-orientation", action="store_true")
    a = p.parse_args()
    build(
        a.source,
        a.output,
        a.elevation,
        a.mount_height,
        a.shift_x,
        not a.keep_maze_height,
        a.rest_pitch,
        a.maze_frames,
        a.finish_lift,
        a.keep_finish_orientation,
        a.shift_y,
        a.reference_seeds,
    )


if __name__ == "__main__":
    main()
