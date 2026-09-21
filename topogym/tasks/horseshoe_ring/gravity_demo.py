"""Gravity-enabled ALOHA hold check and physical audit of the old IK trace.

All five puzzle bodies are free rigid bodies. Only the initially grasped shoes
receive declared hand/body weld assistance. After reset, neither robot nor
puzzle poses are assigned: joint position control and scene.step() drive them.
Ungrasped rings receive no assistance. Failed handovers stop the trace audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MOTION = ROOT / "runs/environment_bootstrap/horseshoe_ring/aloha_full/robot_motion.json"


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output, *, motion_path=DEFAULT_MOTION, config_path=None, mode="hold",
        seconds=None, dt=.002, gravity=9.81, isolate_ring=False, backend="cpu"):
    import genesis as gs
    from topogym.robot.aloha import AlohaDualArmController
    from topogym.tasks.cast_coil.robot_grasp import active_grasps, release_grasps
    from topogym.world.aloha_cameras import configure_aloha_rig
    from .demo import current_loops
    from .scene import build_scene

    if mode not in ("hold", "trace") or gravity not in (0., 9.81):
        raise ValueError("Use hold/trace and normal gravity or the explicit zero-gravity control")
    if not np.isfinite(dt) or dt <= 0 or not np.isclose(.05 / dt, round(.05 / dt)):
        raise ValueError("dt must divide the 20 Hz recording interval")
    if seconds is not None and (not np.isfinite(seconds) or seconds <= 0):
        raise ValueError("seconds must be positive and finite")
    output, motion_path = Path(output).resolve(), Path(motion_path).resolve()
    if output.exists():
        raise FileExistsError(f"Preserve existing evidence: {output}")
    motion = json.loads(motion_path.read_text())
    if not motion["report"].get("sampled_robot_scene_clearance_passed"):
        raise ValueError("The input IK trace has not passed its geometry checks")
    if config_path:
        cfg = OmegaConf.load(config_path)
    else:
        with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
            cfg = compose(config_name="horseshoe_ring_aloha")
    cfg.env.genesis.backend = backend
    cfg.env.renderer.type = "rasterizer"
    cfg.env.sim.dt, cfg.env.sim.substeps = dt, 4
    cfg.env.sim.gravity = [0., 0., -gravity]
    cfg.robot_control.controller.kp = [10000, 18000, 14000, 6000, 4000, 2500, 2000]
    cfg.robot_control.controller.kv = [200, 300, 250, 100, 80, 40, 124]
    configure_aloha_rig(cfg, keep=(), resolution=(960, 540), low_pitch_offset_deg=20)
    OmegaConf.set_struct(cfg.env.cameras, False)
    cfg.env.cameras.detail = dict(res=[960, 720], pos=[.12, -.53, 1.43],
        lookat=[-.1356786, .05, 1.10], up=[0, 0, 1], fov=43, near=.005, far=12)
    output.mkdir(parents=True)
    (output / "recording_cameras.json").write_text(json.dumps(OmegaConf.to_container(cfg.env.cameras, resolve=True), indent=2))
    cfg.env.cameras = {}
    template = Path(cfg.task.template_path)
    if not template.is_absolute():
        template = ROOT / template
    shutil.copy2(template, output / "input_template.json")
    cfg.task.template_path = str(output / "input_template.json")
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    shutil.copy2(motion_path, output / "source_motion.json")
    shutil.copy2(__file__, output / "execution_source.py")
    shutil.copy2(Path(__file__).with_name("scene.py"), output / "scene_source.py")
    (output / "result.json").write_text(json.dumps(dict(complete=False, task_success=False, status="running")))
    gs.init(backend=getattr(gs, backend), logging_level="warning", precision="64", seed=0)
    task = build_scene(cfg, output / "assets")
    digest = hashlib.sha256(json.dumps(task.assembly.template, sort_keys=True).encode()).hexdigest()
    if digest != motion["report"]["source_template_sha256"] or float(cfg.task.scale) != motion["report"]["scene_scale"]:
        raise ValueError("The trace and physical geometry differ")
    robot = task.manifest.get("robot")
    ctrl = AlohaDualArmController(task.scene, robot, cfg.robot_control)
    ctrl.configure()
    solver = task.scene.sim.rigid_solver
    frames = motion["frames"]
    q = np.asarray(frames[0]["qpos"])
    robot.set_qpos(q, zero_velocity=True)
    mount = np.asarray(cfg.env.robot_mount.pos)
    for name, body in task.bodies.items():
        source = frames[0]["bodies"][name]
        pos = mount + source["pos"]
        if isolate_ring and name == "target_ring":
            pos += [.35, -.3, .2]
        body.set_pos(pos)
        body.set_quat(np.asarray(source["quat"])[[3, 0, 1, 2]])
    registrations = []

    def replace_grasps(pairs):
        # The installed solver requires reverse-order deletion of dynamic welds.
        if registrations:
            release_grasps(solver, registrations)
        registrations[:] = [(robot.get_link(side + "/gripper_link").idx,
                              task.bodies[name].base_link_idx) for side, name in pairs]
        for a, b in registrations:
            solver.add_weld_constraint(a, b)

    replace_grasps([("left", "horseshoe_left"), ("right", "horseshoe_right")])
    names = {body.base_link_idx: name for name, body in task.bodies.items()}
    names.update({link.idx: "robot/" + link.name for link in robot.links})
    names[task.manifest.get("table").base_link_idx] = "table"
    fingerlinks = {side: {robot.get_link(f"{side}/{finger}_finger_link").idx
                         for finger in ("left", "right")} for side in ("left", "right")}
    ring = task.bodies["target_ring"]
    z0 = float(array(ring.get_pos())[2])
    phases = {p["name"]: p["time_s"] for p in motion["phases"]}
    events = []
    completed_events = set()
    total = seconds if seconds is not None else (3. if mode == "hold" else (len(frames)-1) / motion["fps"])
    nsteps = round(total / dt)
    stride = round(.05 / dt)
    max_pen = 0.
    first_contact = None
    failure = None
    count = 0
    contacts = None
    start = time.monotonic()
    trace_path = output / "physical_states.jsonl"

    def bilateral(side, name):
        if contacts is None:
            return False
        a, b, force = contacts
        link = task.bodies[name].base_link_idx
        mask = ((a == link) | (b == link)) & (force > .01)
        return fingerlinks[side].issubset(set(a[mask]) | set(b[mask]))

    def handovers(t):
        for key, threshold in (("right_release", phases["双臂交接支撑"]),
                               ("combined_support", phases["左臂换抓圆环"]),
                               ("ring_grasp", phases["调整圆环并脱出"])):
            if t + 1e-10 < threshold or key in completed_events:
                continue
            if key == "right_release":
                replace_grasps([("left", "horseshoe_left")])
            elif key == "combined_support":
                if not all(bilateral("right", name) for name in ("horseshoe_left", "horseshoe_right")):
                    return "Old IK handover missed bilateral contact with both actual horseshoes"
                replace_grasps([("right", "horseshoe_left"), ("right", "horseshoe_right")])
            else:
                if not bilateral("left", "target_ring"):
                    return "Old IK ring grasp missed the gravity-settled target ring"
                replace_grasps([("right", "horseshoe_left"), ("right", "horseshoe_right"), ("left", "target_ring")])
            completed_events.add(key)
            events.append(dict(time_s=t, event=key, active_welds=active_grasps(solver, set(names))))
        return None

    with trace_path.open("w") as trace:
        for step in range(nsteps + 1):
            t = step * dt
            if mode == "trace":
                u = min(t * motion["fps"], len(frames) - 1)
                i = min(int(u), len(frames) - 2)
                q = (1-(u-i))*np.asarray(frames[i]["qpos"]) + (u-i)*np.asarray(frames[i+1]["qpos"])
                failure = failure or handovers(t)
            stage = frames[min(int(t*motion["fps"]), len(frames)-1)]["stage"] if mode == "trace" else "gravity_hold"
            if step % stride == 0 or failure or step == nsteps:
                ct = solver.collider.get_contacts(as_tensor=True, to_torch=True)
                a, b = array(ct["link_a"]), array(ct["link_b"])
                force = np.linalg.norm(array(ct["force"]), axis=-1)
                contacts = a, b, force
                mask = ((a == ring.base_link_idx) | (b == ring.base_link_idx)) & (force > .001)
                peers = sorted({names.get(int(v), str(v)) for v in np.r_[a[mask], b[mask]] if v != ring.base_link_idx})
                if peers and first_contact is None:
                    first_contact = dict(time_s=t, other_bodies=peers)
                poses = {name: dict(pos=array(body.get_pos()).tolist(), quat_wxyz=array(body.get_quat()).tolist(),
                                   velocity=array(body.get_vel()).tolist()) for name, body in task.bodies.items()}
                if not isolate_ring:
                    loops = current_loops(task)
                    linked = [int(loops[a].linking(loops[b])) for a, b in task.assembly.edges]
                    if any(abs(v) != 1 for v in linked):
                        failure = failure or "A chain/eye topology connection was lost in the physical execution"
                else:
                    linked = None
                trace.write(json.dumps(dict(frame=count, step=step, time_s=t, stage=stage,
                    qpos=array(robot.get_qpos()).tolist(), bodies=poses, ring_contact_bodies=peers,
                    chain_link_numbers=linked, max_penetration_m=max_pen,
                    active_welds=active_grasps(solver, set(task.bodies[n].base_link_idx for n in task.bodies)))) + "\n")
                count += 1
            if failure or step == nsteps:
                break
            for arm in ctrl.arms.values():
                arm.set_arm_qpos(q[arm.qs_idx[:6]])
                arm.set_gripper(q[arm.qs_idx[6]])
            task.scene.step()
            ct = solver.collider.get_contacts(as_tensor=True, to_torch=True)
            a, b = array(ct["link_a"]), array(ct["link_b"])
            puzzle = np.isin(a, list(task.bodies[n].base_link_idx for n in task.bodies)) | np.isin(b, list(task.bodies[n].base_link_idx for n in task.bodies))
            pen = float(array(ct["penetration"])[puzzle].max(initial=0))
            max_pen = max(max_pen, pen)
            contacts = a, b, np.linalg.norm(array(ct["force"]), axis=-1)
            if pen > .002:
                failure = f"Puzzle contact penetration exceeded 2 mm ({pen*1000:.3f} mm)"
            if not np.isfinite(array(ring.get_pos())).all():
                failure = "Non-finite target ring state"
            if (step+1) % round(2/dt) == 0:
                print(f"Physics {mode}: {(step+1)*dt:.2f}/{total:.2f} s", flush=True)
    result = dict(mode=mode, complete=failure is None and step==nsteps, task_success=False,
        counts_as_complete_robotics_demo=False, status="physical_audit_failed" if failure else "gravity_check_complete",
        failure=failure, classification="physical_gravity_check_with_pregrasp_assistance",
        scope="Initial shoes explicitly grasp-assisted; ungrasped target ring and chain links fully dynamic; no post-reset pose writes",
        gravity_m_s2=list(cfg.env.sim.gravity), puzzle_gravity_compensation=0., physics_steps=step, dt=dt,
        substeps=int(cfg.env.sim.substeps), precision="64", simulated_seconds=step*dt,
        pose_writes_after_reset=False, ring_initial_assistance=False, chain_assistance=False,
        initial_grasp_assistance="Two shoe/hand welds at declared pregrasp reset, not a validated pickup",
        isolated_ring_control=isolate_ring, ring_initial_height_m=z0,
        ring_final_height_m=float(array(ring.get_pos())[2]), ring_downward_displacement_m=z0-float(array(ring.get_pos())[2]),
        ring_final_velocity_m_s=array(ring.get_vel()).tolist(), maximum_puzzle_penetration_m=max_pen,
        ring_first_contact=first_contact, events=events, physical_frame_count=count, physical_frame_fps=20,
        physical_states_sha256=sha(trace_path), source_motion_sha256=sha(output/"source_motion.json"),
        template_sha256=sha(output/"input_template.json"), wall_seconds=time.monotonic()-start)
    if mode == "trace":
        result["classification"] = "physical_audit_of_kinematic_trace"
        result["status"] = "physical_audit_failed" if failure else "trace_finished_requires_extraction_qualification"
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--motion", type=Path, default=DEFAULT_MOTION)
    parser.add_argument("--config-path", type=Path)
    parser.add_argument("--mode", choices=("hold", "trace"), default="hold")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--gravity", type=float, choices=(0., 9.81), default=9.81)
    parser.add_argument("--isolate-ring", action="store_true", help="Move only the initial ring clear of the puzzle for a free-fall control")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    run(args.output, motion_path=args.motion, config_path=args.config_path, mode=args.mode,
        seconds=args.seconds, dt=args.dt, gravity=args.gravity, isolate_ring=args.isolate_ring, backend=args.backend)


if __name__ == "__main__":
    main()
