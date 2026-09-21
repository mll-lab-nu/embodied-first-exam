"""Construct supported F1/F2/F3 curves and search a continuous contact-grasp IK seed."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil
import time

import yaml
from types import SimpleNamespace

import fcl
import numpy as np
from omegaconf import OmegaConf
from scipy.optimize import minimize
from scipy.ndimage import gaussian_filter1d
from scipy.spatial.transform import Rotation

from .family_geometry import clean, compose, join, line, vertical_wave_controls
from .geometry import BuzzWireLayout, SpatialWire
from .physics import ROOT, save
from .robot_plan import Kinematics, RobotAudit, config
from .verification import ClearanceOracle


def construct(family, smoothing_m=0.0, design_spec=None):
    if not np.isfinite(smoothing_m) or not 0 <= smoothing_m <= 0.03:
        raise ValueError("Arc-length fairing must be between 0 and 30 mm")
    name = {
        "F1": "vertical_wave_v1.yaml",
        "F2": "over_under_eight_v1.yaml",
        "F3": "plane_switch_v1.yaml",
    }[family]
    path = Path(design_spec or ROOT / "configs/task_variants/buzz_wire_3d" / name)
    if family == "F1":
        spec = yaml.safe_load(path.read_text())
        controls, ends = vertical_wave_controls(spec)
    else:
        spec, proto, pieces = compose(path)
        start = pieces[0][1][0]
        tangent = pieces[0][1][1] - start
        tangent /= np.linalg.norm(tangent)
        radius = 0.040
        center = start - [0, 0, radius]
        theta = np.linspace(0, np.pi / 2, 25)
        entry = (
            center
            - radius * np.cos(theta)[:, None] * tangent
            + np.c_[np.zeros_like(theta), np.zeros_like(theta), radius * np.sin(theta)]
        )
        stop_height = 0.040
        controls = clean(np.vstack([line([*entry[0, :2], stop_height], entry[0]), entry]))
        ends = [["start_post", len(controls) - 1]]
        for stage_name, points, _ in pieces:
            controls = clean(np.vstack([controls, points]))
            if stage_name != "connector":
                ends.append([stage_name, len(controls) - 1])
        if family == "F2":
            p = controls[-1]
            theta = np.linspace(np.pi, 0, 40)
            exit_curve = (
                p
                + np.c_[
                    0.035 * (1 + np.cos(theta)), np.zeros_like(theta), 0.035 * np.sin(theta)
                ]
            )
        else:
            end = np.array([0.320, -0.030, 0.210])
            exit_curve = join(controls[-2:], np.array([end, end - [0, 0, 0.01]]), 0.035)
        controls = clean(np.vstack([controls, exit_curve]))
        ends.append(["exit_bend", len(controls) - 1])
        controls = clean(
            np.vstack([controls, line(controls[-1], [*controls[-1, :2], stop_height])])
        )
        ends.append(["finish_post", len(controls) - 1])
    if smoothing_m:
        # Soften sketch joins with an arc-length Gaussian; smoothing_m is not
        # a minimum bend-radius guarantee. Preserve the support endpoints.
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(controls, axis=0), axis=1))]
        stage_arcs = [(name, arc[index]) for name, index in ends]
        samples = np.linspace(0.0, arc[-1], int(np.ceil(arc[-1] / 0.001)) + 1)
        original = np.column_stack(
            [np.interp(samples, arc, controls[:, k]) for k in range(3)]
        )
        smoothed = gaussian_filter1d(
            original, smoothing_m / (samples[1] - samples[0]), axis=0, mode="nearest"
        )
        weight = np.clip(np.minimum(samples, samples[-1] - samples) / (0.06), 0.0, 1.0)
        controls = original + weight[:, None] * (smoothed - original)
        ends = [(name, int(np.argmin(abs(samples - s)))) for name, s in stage_arcs]
    cfg = config()
    base = BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
    layout = replace(
        base,
        template_id="authored_multistage_v1",
        authored_controls_m=controls.tolist(),
        authored_section_ends=ends,
        orientation_knots_wxyz=(),
        normal_tilt_knots=(),
        end_reserve_m=0.140,
        rail_segment_m=0.004,
        witness_step_m=0.00025,
    )
    overrides = spec.get("engineering", {}).get("layout_overrides", {})
    allowed = {"base_size_m", "stem_length_m", "grip_length_m", "end_reserve_m"}
    if set(overrides) - allowed:
        raise ValueError(
            f"Unsupported engineering layout overrides: {set(overrides) - allowed}"
        )
    layout = replace(layout, **overrides)
    layout.validate()
    cfg.task.geometry = asdict(layout)
    cfg.task.variant = layout.template_id
    cfg.robot_demo.instance_id = spec["default_prototype"]
    if smoothing_m:
        cfg.robot_demo.instance_id += f"_rounded{round(1000 * smoothing_m)}mm"
    cfg.robot_demo.release_progress = 1.0
    cfg.robot_demo.plan_samples = 2201
    cfg.robot_demo.retreat_height_m = 0.05
    return cfg, layout, spec


def handle_guide(route, family, progress):
    """Stage-aware handle directions, blended before entering a new plane."""
    if family == "F1":
        return np.array([0.0, -1.0, 0.0])
    if family == "F2":
        # Move behind the lower crossing, then raise the palm after clearing
        # the upper strand. A constant upward or backward handle gets trapped.
        eight = route.sections["layered_eight"]
        lo, hi = eight["start_progress"], eight["end_progress"]
        knots = [(0.0, [0, -0.15, 1]), (lo - 0.055, [0, -0.15, 1])]
        knots += [
            (lo + (hi - lo) * t, v)
            for t, v in [
                (0.0, [0, 1, 0.3]),
                (0.30, [0, 1, 0.3]),
                (0.41, [-0.23, 0.53, 0.81]),
                (0.48, [-0.23, 0.53, 0.81]),
                (0.63, [0, 0, 1]),
                (0.82, [0, 0, 1]),
                (1.0, [0, -1, 0.3]),
            ]
        ]
        knots.append((1.0, [0, -1, 0.3]))
        vector = np.array(
            [
                np.interp(progress, [a for a, _ in knots], [v[k] for _, v in knots])
                for k in range(3)
            ]
        )
        return vector / np.linalg.norm(vector)
    else:
        stages = [
            ("entry_comb", [0, -0.15, 1]),
            ("upright_w", [0, -1, 0.3]),
            ("side_omega", [1, 0, 0.4]),
            ("tilted_coil", [1, 0, 0.7]),
            ("exit_bend", [1, 0, 0.7]),
        ]
    knots = [(0.0, stages[0][1])]
    for name, direction in stages[1:]:
        u = route.sections[name]["start_progress"]
        knots += [(max(knots[-1][0] + 1e-6, u - 0.055), knots[-1][1]), (u, direction)]
    knots.append((1.0, knots[-1][1]))
    if family == "F3":
        omega = route.sections["side_omega"]
        lo, hi = omega["start_progress"], omega["end_progress"]
        knots = [(u, v) for u, v in knots if not lo < u < hi]
        knots += [
            (lo + (hi - lo) * t, v)
            for t, v in [
                (0.35, [1, 0, 0.4]),
                (0.68, [0.26, -0.86, 0.44]),
                (0.86, [0.26, -0.86, 0.44]),
            ]
        ]
        knots.sort(key=lambda row: row[0])
    vector = np.array(
        [
            np.interp(progress, [a for a, _ in knots], [v[k] for _, v in knots])
            for k in range(3)
        ]
    )
    return vector / np.linalg.norm(vector)


def search(
    family,
    output,
    samples=801,
    max_progress=1.0,
    fixture_margin=0.002,
    continuity_weight=1.0,
    height_weight=0.008,
    resume_from=None,
    iterations=80,
    guided=False,
    smoothing_m=0.0,
    resume_count=None,
    origin_x_offset=0.0,
    origin_y_offset=0.0,
    grip_half_turn=False,
    max_joint_step=0.25,
    plan_samples=2201,
    unsigned_search=False,
    candidate_seeds=None,
    design_spec=None,
    joint_center_weight=0.010,
    joint_margin=0.00001,
    warm_start=None,
    grip_roll_offset_deg=0.0,
    normal_cos_min=0.38,
    center_tolerance_m=0.0,
    warm_start_weight=0.0,
    finite_difference_step=1e-5,
    search_tolerance=2e-5,
    motion_checks=0,
    tool_motion_checks=0,
    rigid_grasp_motion=False,
    optimizer_ftol=2e-10,
    pose_reference=None,
    pose_reference_weight=1.0,
    reference_ik_first=False,
    scene_config=None,
    tool_clearance_margin=0.003,
    reverse=False,
    feasible_iterations=0,
    handle_guide_knots=None,
):
    if not 0.0015 <= tool_clearance_margin <= 0.010:
        raise ValueError("Tool search margin must be between 1.5 and 10 mm")
    if samples < 2 or not 0 < max_progress <= 1 or iterations < 1:
        raise ValueError(
            "Need at least two samples, positive iterations and progress in (0,1]"
        )
    if reverse and max_progress != 1.0:
        raise ValueError("Reverse search requires the complete progress interval")
    if not isinstance(feasible_iterations, int) or feasible_iterations < 0:
        raise ValueError("Feasible-iterate stopping count must be nonnegative")
    if not 0 < max_joint_step <= 2 or not 0 <= joint_margin < 0.3:
        raise ValueError("Invalid joint step or physical-limit margin")
    if joint_center_weight < 0:
        raise ValueError("Joint-centering weight must be nonnegative")
    if not 0 < normal_cos_min <= 1:
        raise ValueError("Normal alignment search bound must lie in (0,1]")
    if not 0 <= center_tolerance_m <= 0.014:
        raise ValueError("Search center tolerance must be between 0 and 14 mm")
    if not 0 < finite_difference_step < 0.01:
        raise ValueError("Finite difference step must lie in (0,0.01)")
    if not 0 <= search_tolerance <= 0.0002:
        raise ValueError("Search residual tolerance must lie in [0,0.0002]")
    if not 0 <= motion_checks <= 8:
        raise ValueError("Motion checks must lie in [0,8]")
    if not 0 <= tool_motion_checks <= 8:
        raise ValueError("Tool motion checks must lie in [0,8]")
    if rigid_grasp_motion and not motion_checks:
        raise ValueError("Rigid-grasp motion needs intermediate joint checks")
    if not 0 < optimizer_ftol <= 1e-4:
        raise ValueError("Optimizer termination tolerance must lie in (0,1e-4]")
    if pose_reference_weight < 0:
        raise ValueError("Pose reference weight must be nonnegative")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "implementation").mkdir()
    for name in (
        "family_plan.py",
        "family_geometry.py",
        "robot_plan.py",
        "geometry.py",
        "verification.py",
    ):
        shutil.copy2(Path(__file__).with_name(name), output / "implementation" / name)
    save(
        output / "search_settings.json",
        dict(
            family=family,
            samples=samples,
            max_progress=max_progress,
            fixture_margin=fixture_margin,
            continuity_weight=continuity_weight,
            height_weight=height_weight,
            iterations=iterations,
            guided=guided,
            smoothing_m=smoothing_m,
            origin_x_offset=origin_x_offset,
            origin_y_offset=origin_y_offset,
            grip_half_turn=grip_half_turn,
            resume_from=str(resume_from) if resume_from else None,
            resume_count=resume_count,
            max_joint_step=max_joint_step,
            plan_samples=plan_samples,
            unsigned_search=unsigned_search,
            candidate_seeds=str(candidate_seeds) if candidate_seeds else None,
            design_spec=str(design_spec) if design_spec else None,
            joint_center_weight=joint_center_weight,
            joint_margin=joint_margin,
            warm_start=str(warm_start) if warm_start else None,
            grip_roll_offset_deg=grip_roll_offset_deg,
            normal_cos_min=normal_cos_min,
            center_tolerance_m=center_tolerance_m,
            warm_start_weight=warm_start_weight,
            finite_difference_step=finite_difference_step,
            search_tolerance=search_tolerance,
            motion_checks=motion_checks,
            tool_motion_checks=tool_motion_checks,
            rigid_grasp_motion=rigid_grasp_motion,
            optimizer_ftol=optimizer_ftol,
            pose_reference=str(pose_reference) if pose_reference else None,
            pose_reference_weight=pose_reference_weight,
            reference_ik_first=reference_ik_first,
            scene_config=str(scene_config) if scene_config else None,
            tool_clearance_margin=tool_clearance_margin,
            reverse=reverse,
            feasible_iterations=feasible_iterations,
            handle_guide_knots=str(handle_guide_knots) if handle_guide_knots else None,
        ),
    )
    if candidate_seeds:
        shutil.copy2(candidate_seeds, output / "candidate_seeds.json")
    if scene_config:
        if design_spec or smoothing_m:
            raise ValueError(
                "A resolved scene cannot also be reconstructed from a design"
            )
        cfg = OmegaConf.load(scene_config)
        layout = BuzzWireLayout(
            **OmegaConf.to_container(cfg.task.geometry, resolve=True)
        )
        spec = dict(default_prototype=str(cfg.robot_demo.instance_id), engineering={})
        shutil.copy2(scene_config, output / "source_scene_config.yaml")
    else:
        cfg, layout, spec = construct(family, smoothing_m, design_spec)
    cfg.task.origin_xy_m[0] += origin_x_offset
    cfg.task.origin_xy_m[1] += origin_y_offset
    roll_offset = grip_roll_offset_deg + (180.0 if grip_half_turn else 0.0)
    if roll_offset:
        cfg.robot_demo.grasp_roll_deg = (
            float(cfg.robot_demo.grasp_roll_deg) + roll_offset
        ) % 360.0
        layout = replace(
            layout, grip_flat_roll_deg=float(cfg.robot_demo.grasp_roll_deg)
        )
        cfg.task.geometry = asdict(layout)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    save(output / "design_spec.json", spec)
    route = SpatialWire(layout)
    pose_route = None
    if pose_reference:
        pose_source = json.loads(Path(pose_reference).read_text())
        pose_layout = BuzzWireLayout(**pose_source["layout"])

        def physical(x):
            return json.dumps(
                asdict(replace(x, orientation_knots_wxyz=(), center_offset_knots_m=())),
                sort_keys=True,
            )

        if physical(pose_layout) != physical(layout):
            raise ValueError("Pose reference must use identical physical geometry")
        pose_route = SpatialWire(pose_layout)
        shutil.copy2(pose_reference, output / "pose_reference_seed.json")
    kin = Kinematics(cfg)
    # Ask MuJoCo for near self-pairs as well as penetrations so the optimizer
    # receives a clearance gradient before the hard independent audit rejects it.
    kin.model.geom_margin[:] = 0.010
    source = json.loads(
        (
            ROOT / "assets/tasks/buzz_wire_3d/compact_single_arm_v1/robot_seed.json"
        ).read_text()
    )
    hr = Rotation.from_quat(source["hand_rotation_xyzw"])
    if roll_offset:
        hr = Rotation.from_euler("x", roll_offset, degrees=True) * hr
    hp = np.array(source["hand_offset"])
    hp[0] += (
        layout.loop_radius_m
        + layout.stem_length_m
        + float(cfg.robot_demo.grip_inset_m)
        - source["layout"]["loop_radius_m"]
        - source["layout"]["stem_length_m"]
        - source["grip_inset_m"]
    )
    if scene_config:
        # Recompute the grasp with the unchanged gripper and the smaller handle.
        # Old seeds encode the old finger gap and cannot be scaled with the toy.
        hr = Rotation.from_euler(
            "x", float(cfg.robot_demo.grasp_roll_deg), degrees=True
        ) * Rotation.from_matrix(np.column_stack([[0, 0, 1], [0, 1, 0], [-1, 0, 0]]))
        hp = np.array(
            [
                layout.loop_radius_m
                + layout.stem_length_m
                + float(cfg.robot_demo.grip_inset_m),
                0,
                0,
            ]
        ) - hr.apply(kin.pad_offset)
    save(
        output / "grasp_transform.json",
        dict(hand_offset=hp.tolist(), hand_rotation_xyzw=hr.as_quat().tolist()),
    )
    world = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    origin = np.r_[cfg.task.origin_xy_m, float(cfg.env.frames.table_surface.origin[2])]
    oracle = ClearanceOracle(route, spacing=layout.clearance_cover_m)
    guide_knots = spec.get("engineering", {}).get("handle_direction_knots")
    if handle_guide_knots:
        guide_knots = json.loads(Path(handle_guide_knots).read_text())
        shutil.copy2(handle_guide_knots, output / "handle_guide_knots.json")
    if guide_knots is not None:
        guide_knots = np.asarray(guide_knots, dtype=float)
        if guide_knots.ndim != 2 or guide_knots.shape[1] != 4:
            raise ValueError("Handle guide rows must be [progress, x, y, z]")
        if (
            not np.all(np.isfinite(guide_knots))
            or np.any(np.diff(guide_knots[:, 0]) <= 0)
            or np.any(np.linalg.norm(guide_knots[:, 1:], axis=1) < 1e-9)
        ):
            raise ValueError(
                "Handle guides need increasing progress and finite nonzero directions"
            )
    audit = RobotAudit(kin, route, origin, world, signed_distance=not unsigned_search)
    q = np.array(source["arm_qpos"][0])
    if roll_offset:
        q[-1] -= np.deg2rad(roll_offset)
        q[-1] = (q[-1] + np.pi) % (2 * np.pi) - np.pi
    lower, upper = kin.limits[:, 0] + joint_margin, kin.limits[:, 1] - joint_margin
    mid, half = (upper + lower) / 2, (upper - lower) / 2
    rng = np.random.default_rng(371)
    extra_seeds = []
    warm_rows = None
    if warm_start:
        warm_rows = json.loads(Path(warm_start).read_text())
        shutil.copy2(warm_start, output / "warm_start_rows.json")
        initial_progress = 1.0 if reverse else 0.0
        if (
            warm_rows
            and warm_rows[0]["progress"] <= initial_progress <= warm_rows[-1]["progress"]
        ):
            # Preserve the reference branch from the first target, rather than
            # accepting an unrelated baseline branch before trying warm seeds.
            q = np.clip(
                [
                    np.interp(
                        initial_progress,
                        [row["progress"] for row in warm_rows],
                        [row["arm_qpos"][j] for row in warm_rows],
                    )
                    for j in range(7)
                ],
                lower,
                upper,
            )
    if candidate_seeds:
        extra_seeds = [
            np.asarray(row["arm_qpos"])
            for row in json.loads(Path(candidate_seeds).read_text())["valid"]
        ]
    rows, failure = [], None
    if resume_from:
        resume_from = Path(resume_from)
        saved = OmegaConf.load(resume_from / "config.yaml")
        saved.task.geometry = asdict(
            BuzzWireLayout(**OmegaConf.to_container(saved.task.geometry))
        )
        if OmegaConf.to_container(saved, resolve=True) != OmegaConf.to_container(
            cfg, resolve=True
        ):
            raise ValueError(
                "Resume requires identical geometry and robot configuration"
            )
        rows = json.loads((resume_from / "search_rows.json").read_text())
        if resume_count is not None:
            rows = rows[:resume_count]
        if rows:
            q = np.array(rows[-1]["arm_qpos"])
    started = time.monotonic()
    us = (
        np.linspace(1, 0, samples) if reverse else np.linspace(0, max_progress, samples)
    )
    positions = np.array([route.pose(float(u))[0] for u in us])
    tangents = np.gradient(positions, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    if reverse:
        # Keep the ring-normal convention attached to the authored wire, not
        # to the search direction. The physical grasp and scene stay identical.
        tangents *= -1
    for index, (u, local_p, local_t) in enumerate(zip(us, positions, tangents)):
        if index < len(rows):
            if abs(rows[index]["progress"] - u) > 1e-10:
                raise ValueError("Resume requires the same progress grid")
            continue
        target = origin + world.apply(local_p)
        tangent = world.apply(local_t)
        guide = (
            world.apply(handle_guide(route, family, u))
            if guided
            else np.array([0.0, 0.0, 1.0])
        )
        if guided and guide_knots is not None:
            local_guide = np.array(
                [
                    np.interp(u, guide_knots[:, 0], guide_knots[:, j])
                    for j in range(1, 4)
                ]
            )
            norm = np.linalg.norm(local_guide)
            if norm < 1e-9:
                raise ValueError("Interpolated handle direction must be nonzero")
            guide = world.apply(local_guide / norm)
        previous = q.copy()
        previous_hand_p, previous_hand_r = kin.forward(previous)
        previous_r = previous_hand_r * hr.inv()
        previous_p = previous_hand_p - previous_r.apply(hp)
        reference_rotation = (
            world * Rotation.from_quat(pose_route.pose(float(u))[1][[1, 2, 3, 0]])
            if pose_route is not None
            else None
        )
        warm_guide = None
        if warm_rows and warm_rows[0]["progress"] <= u <= warm_rows[-1]["progress"]:
            warm_guide = np.array(
                [
                    np.interp(
                        u,
                        [row["progress"] for row in warm_rows],
                        [row["arm_qpos"][j] for row in warm_rows],
                    )
                    for j in range(7)
                ]
            )
        center_radius = center_tolerance_m * min(1.0, u / 0.015, (1.0 - u) / 0.015)
        cache = {}
        edge_cache = {}
        tool_edge_cache = {}

        def evaluate(arm):
            key = np.asarray(arm).tobytes()
            if key not in cache:
                hand_p, hand_r = kin.forward(arm)
                r = hand_r * hr.inv()
                p = hand_p - r.apply(hp)
                clearance = oracle.clearance(
                    world.inv().apply(p - origin), world.inv() * r
                )
                bad, distances = audit.check(arm, p, r)
                self_clearance = min(
                    [
                        0.020,
                        *[
                            float(c.dist)
                            for c in kin.data.contact
                            if {
                                kin.model.body(kin.model.geom_bodyid[g]).name
                                for g in [c.geom1, c.geom2]
                            }
                            != {"link0", "link1"}
                        ],
                    ]
                )
                ground = min(
                    [
                        0.020,
                        *[
                            (
                                vertices @ kin.data.geom_xmat[i].reshape(3, 3).T
                                + kin.data.geom_xpos[i]
                            )[:, 2].min()
                            for i, name, _, vertices in audit.geoms
                            if name != "link0"
                        ],
                    ]
                )
                ineq = np.array(
                    [
                        r.apply([0, 0, 1]) @ tangent - normal_cos_min,
                        clearance - tool_clearance_margin,
                        distances["robot_fixture"] - fixture_margin,
                        distances["nonfinger_tool"] - 0.001,
                        distances["robot_metal"] - 0.002,
                        ground - 0.005,
                        self_clearance - 0.003,
                    ]
                )
                cache[key] = p, r, ineq, clearance, bad
            return cache[key]

        def objective(arm):
            p, r, _, _, _ = evaluate(arm)
            return float(
                continuity_weight * np.sum((arm - previous) ** 2)
                + joint_center_weight * np.sum(((arm - mid) / half) ** 8)
                + height_weight * np.sum((r.apply([1, 0, 0]) - guide) ** 2)
                + (0.01 * (1 - r.apply([0, 0, 1]) @ tangent) ** 2 if guided else 0.0)
                + (2000 * np.sum((p - target) ** 2) if center_radius else 0.0)
                + (
                    warm_start_weight * np.sum((arm - warm_guide) ** 2)
                    if warm_guide is not None
                    else 0.0
                )
                + (
                    pose_reference_weight
                    * (r * reference_rotation.inv()).magnitude() ** 2
                    if reference_rotation is not None
                    else 0.0
                )
            )

        def eq(arm):
            if center_radius > 1e-8:
                return np.array([(evaluate(arm)[0] - target) @ tangent * 100])
            return (evaluate(arm)[0] - target) * 100

        def inequality(arm):
            values = evaluate(arm)[2] * np.array([1, 100, 100, 100, 100, 100, 100])
            if index and tool_motion_checks:
                key = np.asarray(arm).tobytes()
                if key not in tool_edge_cache:
                    p, r = evaluate(arm)[:2]
                    turn = (r * previous_r.inv()).as_rotvec()
                    tool_edge_cache[key] = [
                        oracle.clearance(
                            world.inv().apply(
                                previous_p + t * (p - previous_p) - origin
                            ),
                            world.inv() * Rotation.from_rotvec(t * turn) * previous_r,
                        )
                        for t in np.linspace(0, 1, tool_motion_checks + 2)[1:-1]
                    ]
                values = np.r_[
                    values,
                    (np.array(tool_edge_cache[key]) - tool_clearance_margin) * 100,
                ]
            if center_radius > 1e-8:
                values = np.r_[
                    values,
                    (center_radius**2 - np.sum((evaluate(arm)[0] - target) ** 2))
                    * 10000,
                ]
            if index and motion_checks:
                # Reject a search edge that cuts through a neighbour even if
                # both endpoint configurations are clear. The independent
                # dense task-space plan still validates the final trajectory.
                for fraction in np.linspace(0, 1, motion_checks + 2)[1:-1]:
                    middle = previous + fraction * (arm - previous)
                    key = middle.tobytes()
                    if key not in edge_cache:
                        middle_hand_p, middle_hand_r = kin.forward(middle)
                        extra = []
                        if rigid_grasp_motion:
                            middle_r = middle_hand_r * hr.inv()
                            middle_p = middle_hand_p - middle_r.apply(hp)
                            local_middle = world.inv().apply(middle_p - origin)
                            middle_u = us[index - 1] + fraction * (u - us[index - 1])
                            wire_middle = route.pose(float(middle_u))[0]
                            extra = [
                                (
                                    oracle.clearance(
                                        local_middle, world.inv() * middle_r
                                    )
                                    - tool_clearance_margin
                                )
                                * 100,
                                (0.0145 - np.linalg.norm(local_middle - wire_middle))
                                * 100,
                            ]
                        for geom, _, obj, _ in audit.geoms:
                            obj.setTransform(
                                fcl.Transform(
                                    kin.data.geom_xmat[geom].reshape(3, 3),
                                    kin.data.geom_xpos[geom] + kin.mount,
                                )
                            )
                        audit.robot.update()
                        edge_cache[key] = (
                            RobotAudit.distance(
                                audit.robot, audit.fixed_manager, signed=True
                            ),
                            extra,
                        )
                    distance, extra = edge_cache[key]
                    values = np.r_[values, (distance - fixture_margin) * 100, extra]
            return values

        def feasible(arm):
            p, _, inequalities, _, bad = evaluate(arm)
            return (
                np.linalg.norm(p - target) < center_radius + 1e-5
                and np.all(arm >= lower)
                and np.all(arm <= upper)
                and np.linalg.norm(eq(arm)) < 0.001
                and inequalities.min() > -search_tolerance
                and (
                    not (motion_checks or tool_motion_checks)
                    or inequality(arm).min() > -100 * search_tolerance
                )
                and not bad
                and (index == 0 or np.max(abs(arm - previous)) < max_joint_step)
            )

        class FeasibleIterate(Exception):
            pass

        candidates = []
        base_attempts = 5 if index == 0 else 2
        local_seeds = list(extra_seeds)
        if warm_rows:
            local_seeds.insert(
                0,
                np.array(
                    [
                        np.interp(
                            u,
                            [row["progress"] for row in warm_rows],
                            [row["arm_qpos"][j] for row in warm_rows],
                        )
                        for j in range(7)
                    ]
                ),
            )
        direct = []
        if reference_ik_first and reference_rotation is not None:
            turn = (reference_rotation * previous_r.inv()).as_rotvec()
            radial = previous_p - target
            radial -= tangent * (radial @ tangent)
            radial *= min(1.0, center_radius / max(np.linalg.norm(radial), 1e-12))
            for fraction in (1.0, 0.5, 0.25):
                desired_r = Rotation.from_rotvec(fraction * turn) * previous_r
                desired_p = target + (1 - fraction) * radial
                arm, _, _ = kin.solve(
                    desired_p + desired_r.apply(hp),
                    desired_r * hr,
                    previous,
                    max_nfev=60,
                )
                direct.append(
                    SimpleNamespace(x=arm, message=f"Reference IK fraction {fraction}")
                )
        for candidate_index in range(len(direct) + base_attempts + len(local_seeds)):
            attempt = candidate_index - len(direct)
            if candidate_index < len(direct):
                opt = direct[candidate_index]
            else:
                seed = (
                    local_seeds[attempt - base_attempts]
                    if attempt >= base_attempts
                    else previous
                    if attempt == 0
                    else np.clip(
                        previous + rng.normal(0, 0.25 if index == 0 else 0.07, 7),
                        lower,
                        upper,
                    )
                )
                accepted = {}
                iteration_count = 0

                def accept_feasible(arm):
                    nonlocal iteration_count
                    iteration_count += 1
                    if iteration_count >= feasible_iterations and feasible(arm):
                        accepted["arm"] = arm.copy()
                        raise FeasibleIterate

                try:
                    opt = minimize(
                        objective,
                        np.clip(seed, lower, upper),
                        method="SLSQP",
                        bounds=list(zip(lower, upper)),
                        constraints=[
                            dict(type="eq", fun=eq),
                            dict(type="ineq", fun=inequality),
                        ],
                        callback=accept_feasible if feasible_iterations else None,
                        options=dict(
                            maxiter=max(100, iterations) if index == 0 else iterations,
                            ftol=optimizer_ftol,
                            eps=finite_difference_step,
                        ),
                    )
                except FeasibleIterate:
                    opt = SimpleNamespace(
                        x=accepted["arm"],
                        message=f"Feasible iterate accepted after {iteration_count} iterations",
                    )
            p, r, inequalities, clearance, bad = evaluate(opt.x)
            pe = float(np.linalg.norm(p - target))
            # The optional early exit uses these same physical and continuity
            # checks, and only skips further objective minimization.
            valid = feasible(opt.x)
            candidates.append(
                dict(
                    valid=bool(valid),
                    position_error_m=pe,
                    equality_residual_norm=float(np.linalg.norm(eq(opt.x))),
                    minimum_constraint=float(inequalities.min()),
                    scaled_minimum_constraint_including_edges=float(
                        inequality(opt.x).min()
                    ),
                    joint_search_bounds_ok=bool(
                        np.all(opt.x >= lower) and np.all(opt.x <= upper)
                    ),
                    maximum_joint_step_rad=float(np.max(abs(opt.x - previous))),
                    message=str(opt.message),
                    arm_qpos=opt.x.tolist(),
                    contacts=bad,
                    constraints=dict(
                        zip(
                            [
                                "normal",
                                "tool_fixture",
                                "robot_fixture",
                                "nonfinger_tool",
                                "robot_metal",
                                "ground",
                                "self_clearance",
                            ],
                            inequalities.tolist(),
                        )
                    ),
                )
            )
            if valid:
                q = opt.x.copy()
                local_r = world.inv() * r
                rows.append(
                    dict(
                        progress=float(u),
                        arm_qpos=q.tolist(),
                        quaternion_wxyz=local_r.as_quat()[[3, 0, 1, 2]].tolist(),
                        clearance_m=float(clearance),
                        center_offset_m=world.inv().apply(p - target).tolist(),
                    )
                )
                break
        else:
            failure = dict(index=index, progress=float(u), candidates=candidates)
            break
        if index % 20 == 0 or motion_checks or tool_motion_checks:
            save(output / "search_rows.json", rows)
            print(
                f"{family} {index}/{samples} u={u:.4f} clearance={clearance:.4f} elapsed={time.monotonic() - started:.1f}s",
                flush=True,
            )
    save(output / "search_rows.json", rows)
    result = dict(
        passed=failure is None and max_progress == 1,
        family=family,
        failure=failure,
        solved_samples=len(rows),
        requested_samples=samples,
        robot_execution_verified=False,
        scope="Contact-grasp kinematic seed search only; continuous geometric certificate and live physics required",
    )
    save(output / "search_report.json", result)
    if result["passed"]:
        # Search checkpoints retain execution order for resumability; exported
        # forward-demo seeds always use increasing task progress.
        rows = sorted(rows, key=lambda row: row["progress"])
        layout = replace(
            layout,
            orientation_knots_wxyz=[
                [r["progress"], *r["quaternion_wxyz"]] for r in rows
            ],
            center_offset_knots_m=[
                [r["progress"], *r.get("center_offset_m", [0.0, 0.0, 0.0])]
                for r in rows
            ]
            if center_tolerance_m
            else (),
        )
        save(
            output / "seed.json",
            dict(
                layout=asdict(layout),
                origin=origin.tolist(),
                yaw=float(cfg.task.yaw_deg),
                progress=[r["progress"] for r in rows],
                arm_qpos=[r["arm_qpos"] for r in rows],
                hand_offset=hp.tolist(),
                hand_rotation_xyzw=hr.as_quat().tolist(),
                grip_roll_deg=float(cfg.robot_demo.grasp_roll_deg),
                grip_inset_m=float(cfg.robot_demo.grip_inset_m),
                instance_id=str(cfg.robot_demo.instance_id),
                release_progress=1.0,
                plan_samples=plan_samples,
            ),
        )
    shutil.copy2(
        output / "implementation/family_plan.py", output / "family_plan_source.py"
    )
    print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["F1", "F2", "F3"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=801)
    parser.add_argument("--max-progress", type=float, default=1.0)
    parser.add_argument("--fixture-margin", type=float, default=0.002)
    parser.add_argument("--continuity-weight", type=float, default=1.0)
    parser.add_argument("--height-weight", type=float, default=0.008)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--guided", action="store_true")
    parser.add_argument("--smoothing-m", type=float, default=0.0)
    parser.add_argument("--resume-count", type=int)
    parser.add_argument("--origin-x-offset", type=float, default=0.0)
    parser.add_argument("--origin-y-offset", type=float, default=0.0)
    parser.add_argument("--grip-half-turn", action="store_true")
    parser.add_argument("--max-joint-step", type=float, default=0.25)
    parser.add_argument("--plan-samples", type=int, default=2201)
    parser.add_argument("--unsigned-search", action="store_true")
    parser.add_argument("--candidate-seeds", type=Path)
    parser.add_argument("--design-spec", type=Path)
    parser.add_argument("--joint-center-weight", type=float, default=0.010)
    parser.add_argument("--joint-margin", type=float, default=0.00001)
    parser.add_argument("--warm-start", type=Path)
    parser.add_argument("--grip-roll-offset-deg", type=float, default=0.0)
    parser.add_argument("--normal-cos-min", type=float, default=0.38)
    parser.add_argument("--center-tolerance-m", type=float, default=0.0)
    parser.add_argument("--warm-start-weight", type=float, default=0.0)
    parser.add_argument("--finite-difference-step", type=float, default=1e-5)
    parser.add_argument("--search-tolerance", type=float, default=2e-5)
    parser.add_argument("--motion-checks", type=int, default=0)
    parser.add_argument("--tool-motion-checks", type=int, default=0)
    parser.add_argument("--rigid-grasp-motion", action="store_true")
    parser.add_argument("--optimizer-ftol", type=float, default=2e-10)
    parser.add_argument("--pose-reference", type=Path)
    parser.add_argument("--pose-reference-weight", type=float, default=1.0)
    parser.add_argument("--reference-ik-first", action="store_true")
    parser.add_argument("--scene-config", type=Path)
    parser.add_argument("--tool-clearance-margin", type=float, default=0.003)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--feasible-iterations", type=int, default=0)
    parser.add_argument("--handle-guide-knots", type=Path)
    args = parser.parse_args()
    if not search(**vars(args))["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
