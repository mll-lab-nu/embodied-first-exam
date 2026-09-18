"""Bounded ALOHA control following the recorded route, with removable grasps.

Starts pregrasped with declared ideal weld retention, matching the source's
grasp abstraction. After initialization no body or joint poses are overwritten.
The trace contains actual integrated states for independent checks/rendering.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .collision import ClawCollision
from .reference import ReferenceMotion, ROOT


def run(output, dt=.002, duration=None, start_time=0., backend="cpu"):
    import genesis as gs
    from .scene import as_numpy, build_scene
    from topogym.tasks.cast_coil.robot_grasp import active_grasps, release_grasps

    if dt not in (.002, .001) or start_time < 0:
        raise ValueError("Use dt 0.002 or 0.001 and a nonnegative reference start time")
    output = Path(output).resolve()
    if (output/"result.json").exists():
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    motion = ReferenceMotion()
    start_q, _, start_poses, start_held, _ = motion.sample(start_time)
    seconds = (motion.duration-start_time+2.) if duration is None else float(duration)
    if seconds <= 0 or start_time >= motion.duration:
        raise ValueError("Invalid physical execution interval")
    with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
        cfg = compose(config_name="interlocked_claws_physics")
    cfg.env.sim.dt = dt
    cfg.env.genesis.backend = backend
    cfg.env.cameras = {}
    cfg.run.output = str(output)
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    (output/"execution_source.py").write_text(Path(__file__).read_text())
    (output/"source_motion.json").write_bytes(motion.path.read_bytes())
    gs.init(backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0)
    task = build_scene(cfg, output/"assets")
    robot, solver = task.controller.robot, task.scene.sim.rigid_solver
    bodies = list(task.bodies.values())
    arms = list(task.controller.arms.values())
    robot.set_qpos(start_q, zero_velocity=True)
    for body, pose in zip(bodies, start_poses):
        body.set_pos(task.world_offset+pose[:3, 3])
        body.set_quat(Rotation.from_matrix(pose[:3, :3]).as_quat()[[3, 0, 1, 2]])
    # Register right then left. Source releases left first, so both deletions
    # remove the tail equality and avoid the installed solver's non-tail bug.
    held = list(start_held)
    welds = [(arm.ee_link.idx, body.base_link_idx) for arm, body in zip(arms, bodies)]
    for i in (1, 0):
        if held[i]:
            solver.add_weld_constraint(*welds[i])
    hand_ids = [set(robot.get_link(f"{side}/{f}_finger_link").idx for f in ("left", "right"))
                for side in ("left", "right")]
    robot_links = {l.idx: l.name for l in robot.links}
    body_links = {b.base_link_idx for b in bodies}
    table_link = task.tabletop.manifest.get("table").base_link_idx
    fixture_links = {task.tabletop.manifest.get(n).base_link_idx for n in task.loading_report["fixtures"]}
    collision = ClawCollision(task.assembly)
    stats = dict(max_interpiece_penetration_m=0., max_forbidden_robot_penetration_m=0.,
                 max_finger_penetration_m=0., max_fixture_penetration_m=0., max_joint_tracking_error_rad=0.,
                 min_sampled_exact_clearance_m=float("inf"), max_held_position_error_m=0.,
                 max_triangle_contact_depth_m=0., max_object_table_penetration_m=0.)
    releases, phases, tail, initial_contacts = [], [], [], {}
    failed, phase, step = None, "", 0
    started = time.monotonic()
    steps = int(np.ceil(seconds/dt))
    capture_stride = round(.1/dt)
    audit_stride = round(.02/dt)
    frame_count, last_support = 0, [0., 0.]

    def poses_and_state():
        poses, state = [], []
        for body in bodies:
            p, q = as_numpy(body.get_pos()), as_numpy(body.get_quat())
            pose = np.eye(4); pose[:3, :3] = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix(); pose[:3, 3] = p
            poses.append(pose)
            state.append(dict(pos=p.tolist(), quat_wxyz=q.tolist(),
                              linear_speed_m_s=float(np.linalg.norm(as_numpy(body.get_vel()))),
                              angular_speed_rad_s=float(np.linalg.norm(as_numpy(body.get_ang())))))
        return poses, state

    def capture(stream):
        nonlocal frame_count
        poses, state = poses_and_state()
        stream.write(json.dumps(dict(frame=frame_count, step=step, time_s=step*dt,
            reference_time_s=min(start_time+step*dt, motion.duration), phase=phase,
            qpos=as_numpy(robot.get_qpos()).tolist(), bodies=state, held=list(held),
            signed_support_force_z_N=last_support)) + "\n")
        stream.flush()
        frame_count += 1

    try:
        with (output/"states.jsonl").open("w") as trace:
            phase = motion.sample(start_time)[4]
            phases.append(dict(name=phase, time_s=0.))
            capture(trace)
            for step in range(1, steps+1):
                reference_time = start_time+(step-1)*dt
                q, v, desired_held, label = motion.control(reference_time)
                if label != phase:
                    phase = label; phases.append(dict(name=phase, time_s=(step-1)*dt))
                    print(f"PHASE {phase} at {(step-1)*dt:.3f} s", flush=True)
                for i in range(2):
                    if held[i] and not desired_held[i]:
                        evidence = release_grasps(solver, [welds[i]])
                        releases.append(dict(piece=i, time_s=(step-1)*dt, **evidence))
                        held[i] = False
                for i, arm in enumerate(arms):
                    ids = arm.actuated_dofs
                    robot.control_dofs_position_velocity(q[8*i:8*i+7], v[8*i:8*i+7], ids)
                task.scene.step()
                ct = {k: as_numpy(v) for k, v in solver.collider.get_contacts().items()}
                la, lb, pen, force = ct["link_a"], ct["link_b"], ct["penetration"], ct["force"]
                if not np.isfinite(np.r_[as_numpy(robot.get_qpos()), pen]).all():
                    raise RuntimeError("Non-finite physical state")
                pair = np.isin(la, list(body_links)) & np.isin(lb, list(body_links))
                allowed_finger = np.zeros(len(pen), dtype=bool)
                last_support = []
                for i, body in enumerate(bodies):
                    link = body.base_link_idx
                    fingers = ((la == link)&np.isin(lb, list(hand_ids[i]))) | ((lb == link)&np.isin(la, list(hand_ids[i])))
                    allowed_finger |= fingers
                    if step <= round(.1/dt):
                        touched = set(la[fingers].tolist())|set(lb[fingers].tolist())
                        initial_contacts.setdefault(str(i), set()).update(touched & hand_ids[i])
                    supports = ((la == link)&np.isin(lb, list(fixture_links))) | ((lb == link)&np.isin(la, list(fixture_links)))
                    signs = np.where(lb[supports] == link, 1., -1.)
                    last_support.append(float(np.sum(force[supports, 2]*signs)))
                robot_any = np.isin(la, list(robot_links)) | np.isin(lb, list(robot_links))
                cross = np.array([(str(robot_links.get(int(a), "")).split('/')[0] != str(robot_links.get(int(b), "")).split('/')[0])
                                  for a, b in zip(la, lb)], dtype=bool)
                # Fixed base/table contact and same-arm adjacent geometry are
                # evaluated by the source articulation; monitor cross-arm and
                # all non-finger robot/puzzle/fixture/table contacts here.
                monitored = robot_any & (np.isin(la, list(body_links|fixture_links|{table_link}))
                                         | np.isin(lb, list(body_links|fixture_links|{table_link})) | cross)
                for link, name in robot_links.items():
                    if name.endswith("base_link"):
                        monitored &= ~(((la == link)&(lb == table_link))|((lb == link)&(la == table_link)))
                forbidden = monitored & ~allowed_finger
                fixture_contact = (np.isin(la, list(body_links))&np.isin(lb, list(fixture_links))) | (np.isin(lb, list(body_links))&np.isin(la, list(fixture_links)))
                table_contact = (np.isin(la,list(body_links))&(lb==table_link)) | (np.isin(lb,list(body_links))&(la==table_link))
                for key, mask in (("max_interpiece_penetration_m", pair), ("max_forbidden_robot_penetration_m", forbidden),
                                  ("max_finger_penetration_m", allowed_finger), ("max_fixture_penetration_m", fixture_contact),
                                  ("max_object_table_penetration_m", table_contact)):
                    stats[key] = max(stats[key], float(pen[mask].max(initial=0)))
                if max(stats[k] for k in ("max_interpiece_penetration_m", "max_forbidden_robot_penetration_m", "max_object_table_penetration_m", "max_fixture_penetration_m")) > .001:
                    raise RuntimeError(f"Contact penetration exceeded 1 mm: {stats}")
                if step % audit_stride == 0:
                    expected = motion.sample(reference_time)[2]
                    actual_poses, states = poses_and_state()
                    gap = collision.clearance(actual_poses)
                    if gap < 0:
                        depth = collision.contact_depth()
                        stats["max_triangle_contact_depth_m"] = max(stats["max_triangle_contact_depth_m"], depth)
                        gap = -depth
                    stats["min_sampled_exact_clearance_m"] = min(stats["min_sampled_exact_clearance_m"], gap)
                    if gap < -.00015:
                        raise RuntimeError(f"Actual triangle contact depth exceeded 0.15 mm: {-gap}")
                    actual_q = as_numpy(robot.get_qpos())
                    err = float(np.max(np.abs(actual_q[np.r_[0:6, 8:14]]-q[np.r_[0:6, 8:14]])))
                    stats["max_joint_tracking_error_rad"] = max(stats["max_joint_tracking_error_rad"], err)
                    for i in range(2):
                        if held[i]:
                            error = float(np.linalg.norm(actual_poses[i][:3, 3]-task.world_offset-expected[i][:3, 3]))
                            stats["max_held_position_error_m"] = max(stats["max_held_position_error_m"], error)
                            if error > .008:
                                raise RuntimeError(f"Held piece {i} tracking error exceeded 8 mm: {error}")
                    if reference_time >= motion.duration-1:
                        tail.append(dict(time_s=step*dt, bodies=states, support_force_z_N=last_support, held=list(held)))
                if step % capture_stride == 0:
                    capture(trace)
                if step % round(2/dt) == 0:
                    print(json.dumps(dict(t=round(step*dt, 3), phase=phase, wall=round(time.monotonic()-started, 1), **stats)), flush=True)
    except Exception as exc:
        failed = str(exc)
        print(f"PHYSICS FAILED at {step*dt:.3f}: {failed}", flush=True)
    actual_poses, final = poses_and_state()
    remaining = active_grasps(solver, body_links)
    full = duration is None and start_time == 0 and failed is None and step == steps
    stable = bool(tail and not any(any(t["held"]) for t in tail)
        and max(b["linear_speed_m_s"] for t in tail for b in t["bodies"]) < .005
        and max(b["angular_speed_rad_s"] for t in tail for b in t["bodies"]) < .05
        and np.min(np.mean([t["support_force_z_N"] for t in tail], axis=0)) > .1)
    separation = collision.clearance(actual_poses)
    result = dict(passed=failed is None, success=bool(full and stable and not remaining and separation>.02),
        complete=full, failed=failed, scope="pregrasped ideal-grasp-assisted dynamic joint control",
        reference_motion_sha256=motion.sha256, initial_reference_time_s=start_time,
        simulated_seconds=step*dt, physics_steps=step, dt=dt, backend=backend, substeps=int(cfg.env.sim.substeps),
        source_duration_s=motion.duration, final_reference_time_s=min(start_time+step*dt, motion.duration),
        stats={k:(v if np.isfinite(v) else None) for k,v in stats.items()}, releases=releases,
        remaining_grasps=remaining, held_at_end=held, final=final, final_separation_m=separation,
        final_stable=stable, final_stability_window=tail,
        initial_finger_contact_links={k:sorted(v) for k,v in initial_contacts.items()},
        physical_frame_count=frame_count, physical_frame_fps=10, phases=phases,
        states_sha256=hashlib.sha256((output/"states.jsonl").read_bytes()).hexdigest(),
        source_mesh_sha256=[b.source["sha256"] for b in task.assembly.bodies],
        actual_loading=task.loading_report, pose_writes_after_initialization=False,
        pregrasped_start=True, initial_welds_assumed=True, friction_only_grasp_verified=False,
        original_actuator_force_limits=OmegaConf.to_container(cfg.robot_control.controller.force_limit),
        triangle_contact_depth_limit_m=.00015, native_non_grasp_penetration_limit_m=.001,
        wall_seconds=time.monotonic()-started)
    (output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("final_stability_window", "actual_loading")}, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--start-time", type=float, default=0.)
    parser.add_argument("--backend", choices=("cuda", "cpu"), default="cpu")
    args = parser.parse_args()
    r = run(args.output, args.dt, args.duration, args.start_time, args.backend)
    if not r["passed"] or (args.duration is None and not r["success"]):
        raise SystemExit(1)
