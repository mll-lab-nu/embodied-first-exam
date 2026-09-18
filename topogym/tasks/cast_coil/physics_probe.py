"""Cast Coil local qualification: gravity, blocking controls and a prototype route.

Run as a module, then repeat with --dt 0.0005 into a different output folder.
Motion probes explicitly fix gold and apply bounded external wrenches to the
free silver body. They are bench tests, not robot grasps or official demos.
"""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import generate_assets
from .verification import CompoundCollision, Motion, VARIANTS, box_corners, prototype_route


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def target_at(motions, seconds):
    """Smooth motion parameterization with zero speed at each junction."""
    if seconds <= 0:
        R, p = motions[0].pose(0)
        return R, p, np.zeros(3), np.zeros(3), motions[0].name
    for motion in motions:
        if seconds <= motion.duration_s:
            q = seconds/motion.duration_s
            u, du = 6*q**5-15*q**4+10*q**3, 30*q*q*(1-q)**2/motion.duration_s
            R, p = motion.pose(u)
            if motion.axis is None:
                return R, p, (motion.end_translation-motion.start_translation)*du, np.zeros(3), motion.name
            omega = motion.axis*motion.angle_rad*du
            return R, p, np.cross(omega, p-motion.pivot), omega, motion.name
        seconds -= motion.duration_s
    R, p = motions[-1].pose(1)
    return R, p, np.zeros(3), np.zeros(3), "hold_final"


def specifications():
    cases = []
    for variant in VARIANTS:
        cases.extend([dict(name=f"{variant}_settle", kind="settle", variant=variant),
                      dict(name=f"{variant}_route", kind="route", variant=variant)])
    for sign in (-1, 1):
        cases.append(dict(name=f"allowed_x_{sign:+d}", kind="allowed", variant="baseline_3x", axis=0, sign=sign))
        for axis in range(3):
            cases.append(dict(name=f"blocked_{'xyz'[axis]}_{sign:+d}", kind="blocked",
                              variant="baseline_3x", axis=axis, sign=sign))
    cases.append(dict(name="opposite_turn", kind="wrong_turn", variant="baseline_3x"))
    return cases


def build_probe(output, dt, selected):
    import genesis as gs

    scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(dt=dt, substeps=4, gravity=(0, 0, -9.81)),
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            iterations=100, max_collision_pairs=4096, constraint_timeconst=.001))
    scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(friction=.35))
    assets = {name: generate_assets(output/"assets"/name, scale=values["scale"]) for name, values in VARIANTS.items()}
    cases, entities = [], []
    for index, spec in enumerate(selected):
        variant = spec["variant"]
        assembly, report = assets[variant]
        yaw = Rotation.from_euler("z", VARIANTS[variant]["yaw_deg"], degrees=True)
        root = np.array([index % 5*.6, index//5*.6, .30])
        settle = spec["kind"] == "settle"
        if settle:
            root[2] = -report["bounds_m"][0][2]+.0005
        bodies, body_indices, origins = [], [], []
        for number, info in enumerate(report["bodies"]):
            name = info["name"]
            origin = np.asarray(info["origin_m"])
            body = scene.add_entity(gs.morphs.URDF(
                file=str((output/"assets"/variant/name/f"{name}.urdf").resolve()),
                pos=root+yaw.apply(origin), quat=yaw.as_quat()[[3, 0, 1, 2]],
                fixed=number == 0 and not settle, align=False, convexify=False, decimate=False,
                merge_fixed_links=False), material=gs.materials.Rigid(friction=.35,
                    gravity_compensation=0. if settle else 1.), name=f"{spec['name']}_{name}")
            bodies.append(body)
            body_indices.append(len(entities))
            entities.append(body)
            origins.append(origin)
        route = prototype_route(assembly)
        if spec["kind"] == "wrong_turn":
            route = route[:2]
            route[1].angle_rad *= -1
        elif spec["kind"] in ("allowed", "blocked"):
            travel_mm = 7.25 if spec["kind"] == "allowed" else (30 if spec["axis"] == 0 else 5)
            translation = np.eye(3)[spec["axis"]]*spec["sign"]*travel_mm*assembly.unit
            route = [Motion(spec["name"], 1.5, np.eye(3), np.zeros(3), translation)]
        cases.append(dict(**spec, root=root, yaw=yaw, assembly=assembly, report=report,
            bodies=bodies, indices=body_indices, origins=origins, route=route,
            collision=CompoundCollision(*(b.boxes for b in assembly.bodies)),
            stats=dict(max_penetration_m=0., max_interpiece_penetration_m=0., max_contact_force_N=0.,
                contact_steps=0, min_observed_sat_gap_m=float("inf"), max_position_error_m=0.,
                max_rotation_error_rad=0., max_displacement_m=0., max_rotation_from_initial_rad=0.,
                max_command_force_N=0., max_command_torque_Nm=0., tail_max_speed_m_s=0.), trace=[]))
    scene.build()
    for c in cases:
        if [b.n_dofs for b in c["bodies"]] != ([6, 6] if c["kind"] == "settle" else [0, 6]):
            raise RuntimeError("Unexpected body constraints")
    return scene, cases, entities


def run_probe(output, dt=.001, only=None):
    import genesis as gs

    if not np.isfinite(dt) or not 0 < dt <= .001:
        raise ValueError("Require 0 < dt <= 0.001")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = [c for c in specifications() if only is None or c["name"] in only]
    if not selected or (only and set(only)-{c["name"] for c in selected}):
        raise ValueError("Unknown or empty probe selection")
    config = dict(dt=dt, substeps=4, iterations=100, friction=.35, constraint_timeconst=.001,
        duration_s=8.5, controller=dict(kp_position=6000., kd_position=190., kp_rotation=30., kd_rotation=1.,
            max_force_N=60., max_torque_Nm=3., velocity_feedforward=True),
        pose_writes_after_reset=False, gold_fixed_in_motion_probes=True, moving_silver_dofs=6,
        gravity_compensation_in_motion_probes=1., gravity_compensation_in_settle_probes=0.,
        variants=VARIANTS, cases=selected, seed=0,
        scope="local contact bench; no robot; discovered prototype route, not official tutorial")
    (output/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    gs.init(backend=gs.cuda, logging_level="warning", seed=0)
    started = time.monotonic()
    scene, cases, entities = build_probe(output, dt, selected)
    solver = scene.sim.rigid_solver
    indices = [b.base_link_idx for b in entities]
    controlled = [c for c in cases if c["kind"] != "settle"]
    controlled_links = [c["bodies"][1].base_link_idx for c in controlled]
    initial = None
    frames = []
    steps = round(config["duration_s"]/dt)
    for step in range(steps):
        now = step*dt
        pos = array(solver.get_links_pos(indices, relative=True))
        quat = array(solver.get_links_quat(indices, relative=True))
        vel = array(solver.get_links_vel(indices))
        angular = array(solver.get_links_ang(indices))
        if not np.isfinite(np.r_[pos.ravel(), quat.ravel(), vel.ravel(), angular.ravel()]).all():
            raise RuntimeError(f"Non-finite rigid state at step {step}")
        rotations = Rotation.from_quat(quat[:, [1, 2, 3, 0]])
        if initial is None:
            initial = pos.copy()
        commands, torques = [], []
        for c in controlled:
            i = c["indices"][1]
            R, t, velocity, omega, phase = target_at(c["route"], now-.5)
            center = R@c["origins"][1]
            target_pos = c["root"]+c["yaw"].apply(t+center)
            target_rotation = c["yaw"]*Rotation.from_matrix(R)
            target_vel = c["yaw"].apply(velocity+np.cross(omega, center))
            target_omega = c["yaw"].apply(omega)
            error = target_pos-pos[i]
            rot_error = (target_rotation*rotations[i].inv()).as_rotvec()
            force = 6000*error+190*(target_vel-vel[i])
            torque = 30*rot_error+(target_omega-angular[i])
            force *= min(1., 60/max(np.linalg.norm(force), 1e-10))
            torque *= min(1., 3/max(np.linalg.norm(torque), 1e-10))
            # Hold after completing the motion, then remove drive. No pose reset.
            release_at = .5+sum(m.duration_s for m in c["route"])+.5
            if now >= release_at:
                force, torque, phase = np.zeros(3), np.zeros(3), "drive_released"
            commands.append(force)
            torques.append(torque)
            c["target_pos"], c["target_rotation"], c["phase"] = target_pos, target_rotation, phase
            c["stats"]["max_command_force_N"] = max(c["stats"]["max_command_force_N"], float(np.linalg.norm(force)))
            c["stats"]["max_command_torque_Nm"] = max(c["stats"]["max_command_torque_Nm"], float(np.linalg.norm(torque)))
        if controlled:
            solver.apply_links_external_force(np.asarray(commands), controlled_links, ref="link_com")
            solver.apply_links_external_torque(np.asarray(torques), controlled_links, ref="link_com")
        scene.step()
        # Audit the post-step state that actually resulted from forces/contact.
        pos = array(solver.get_links_pos(indices, relative=True))
        quat = array(solver.get_links_quat(indices, relative=True))
        vel = array(solver.get_links_vel(indices))
        rotations = Rotation.from_quat(quat[:, [1, 2, 3, 0]])
        contacts = {k: array(v) for k, v in solver.collider.get_contacts().items()}
        ga, gb = contacts["geom_a"], contacts["geom_b"]
        sample = (step+1) % max(1, round(.025/dt)) == 0
        for c in cases:
            ia, ib = c["indices"]
            a, b = c["bodies"]
            stats = c["stats"]
            ma = ((ga >= a.geom_start) & (ga < a.geom_end)) | ((gb >= a.geom_start) & (gb < a.geom_end))
            mb = ((ga >= b.geom_start) & (ga < b.geom_end)) | ((gb >= b.geom_start) & (gb < b.geom_end))
            mask, pair = ma | mb, ma & mb
            if mask.any():
                penetration = float(contacts["penetration"][mask].max())
                stats["max_penetration_m"] = max(stats["max_penetration_m"], penetration)
                stats["max_contact_force_N"] = max(stats["max_contact_force_N"],
                    float(np.linalg.norm(contacts["force"][mask], axis=-1).max()))
                stats["contact_steps"] += 1
            if pair.any():
                stats["max_interpiece_penetration_m"] = max(stats["max_interpiece_penetration_m"],
                                                            float(contacts["penetration"][pair].max()))
            gold_origin = pos[ia]-rotations[ia].apply(c["origins"][0])
            silver_origin = pos[ib]-rotations[ib].apply(c["origins"][1])
            relative_R = (rotations[ia].inv()*rotations[ib]).as_matrix()
            relative_t = rotations[ia].inv().apply(silver_origin-gold_origin)
            gap = c["collision"].gap(relative_R, relative_t)
            stats["min_observed_sat_gap_m"] = min(stats["min_observed_sat_gap_m"], gap)
            displacement = float(np.linalg.norm(pos[c["indices"]]-initial[c["indices"]], axis=1).max())
            stats["max_displacement_m"] = max(stats["max_displacement_m"], displacement)
            angle = float((c["yaw"].inv()*rotations[c["indices"]]).magnitude().max())
            stats["max_rotation_from_initial_rad"] = max(stats["max_rotation_from_initial_rad"], angle)
            if c["kind"] != "settle":
                pe = float(np.linalg.norm(c["target_pos"]-pos[ib]))
                re = float((c["target_rotation"]*rotations[ib].inv()).magnitude())
                stats["max_position_error_m"] = max(stats["max_position_error_m"], pe)
                stats["max_rotation_error_rad"] = max(stats["max_rotation_error_rad"], re)
                if now < .5+sum(m.duration_s for m in c["route"])+.5:
                    c["loaded_error"] = [pe, re]
                    c["loaded_translation"] = relative_t.copy()
            if now >= config["duration_s"]-.3:
                stats["tail_max_speed_m_s"] = max(stats["tail_max_speed_m_s"], float(np.linalg.norm(vel[c["indices"]], axis=1).max()))
            if sample:
                c["trace"].append(dict(time_s=(step+1)*dt, translation_m=relative_t.tolist(),
                    quaternion_xyzw=Rotation.from_matrix(relative_R).as_quat().tolist(), sat_gap_m=gap,
                    phase=c.get("phase", "free_gravity")))
            c["final_relative_R"], c["final_relative_t"] = relative_R, relative_t
        if sample:
            frames.append(dict(time_s=(step+1)*dt, positions_m=pos.tolist(), quaternions_wxyz=quat.tolist()))
        if (step+1) % max(1, round(1./dt)) == 0:
            print(f"Local physics {step+1}/{steps}; {time.monotonic()-started:.1f}s wall", flush=True)
    reports = []
    for c in cases:
        stats, kind = c["stats"], c["kind"]
        contact_ok = stats["max_penetration_m"] < .0005 and stats["min_observed_sat_gap_m"] > -.0005
        if kind == "settle":
            behavior_ok = stats["max_displacement_m"] < .003 and stats["max_rotation_from_initial_rad"] < .05
        elif kind in ("route", "allowed"):
            behavior_ok = stats["max_position_error_m"] < .0005 and stats["max_rotation_error_rad"] < .01
        elif kind == "blocked":
            maximum = (20. if c["axis"] == 0 else .25)*c["assembly"].unit
            achieved = float(c["loaded_translation"][c["axis"]]*c["sign"])
            behavior_ok = (abs(achieved-maximum) < .001 and c["loaded_error"][0] > .005 and stats["contact_steps"] > 0
                           and stats["max_rotation_from_initial_rad"] < .05)
        else:
            behavior_ok = c["loaded_error"][1] > .2 and stats["contact_steps"] > 0
        final_points = box_corners(c["assembly"].bodies[1].boxes)@c["final_relative_R"].T+c["final_relative_t"]
        exit_gap = float(final_points[:, 0].min()-c["assembly"].bodies[0].boxes[:, 1, 0].max())
        if kind == "route":
            behavior_ok = behavior_ok and exit_gap > .01
        passed = bool(contact_ok and behavior_ok and stats["tail_max_speed_m_s"] < .01)
        reports.append(dict(name=c["name"], kind=kind, variant=c["variant"], passed=passed,
            contact_reliable=bool(contact_ok), expected_behavior_verified=bool(behavior_ok), **stats,
            loaded_error=c.get("loaded_error"), loaded_translation_m=c.get("loaded_translation", np.zeros(3)).tolist(),
            final_relative_translation_m=c["final_relative_t"].tolist(),
            final_relative_quaternion_xyzw=Rotation.from_matrix(c["final_relative_R"]).as_quat().tolist(),
            final_separating_plane_gap_m=exit_gap, body_dofs=[b.n_dofs for b in c["bodies"]]))
        (output/f"{c['name']}_trace.json").write_text(json.dumps(c["trace"], indent=2, allow_nan=False)+"\n")
        print(c["name"], passed, "penetration", stats["max_penetration_m"], "error", c.get("loaded_error"), flush=True)
    result = dict(scope=config["scope"], config=config, genesis_version=version("genesis-world"),
        passed=all(r["passed"] for r in reports), cases=reports, physics_steps=steps,
        simulated_seconds=steps*dt, wall_seconds=time.monotonic()-started,
        pose_writes_after_reset=False, robot_grasp_verified=False, official_route_verified=False,
        formal_demo_qualified=False)
    (output/"report.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    (output/"states.json").write_text(json.dumps(dict(entity_order=[b.name for b in entities], frames=frames), allow_nan=False)+"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/environment-solvability/cast_coil/photo_reference_v1/nominal"))
    parser.add_argument("--dt", type=float, default=.001)
    parser.add_argument("--only", nargs="+")
    args = parser.parse_args()
    result = run_probe(args.output, args.dt, args.only)
    if not result["passed"]:
        raise SystemExit("One or more local probe checks failed; inspect report.json")


if __name__ == "__main__":
    main()
