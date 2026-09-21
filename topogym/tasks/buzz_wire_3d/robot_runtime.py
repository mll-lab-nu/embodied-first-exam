"""Measured single-arm dynamics; the wand is moved only through a contacted grasp."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import time

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from topogym.tasks._rigid_geometry import disk_linking_number
from .physics import array, save
from .render import sha
from .scene import BuzzWireSceneBuilder


def execute(plan_dir, output, dt=0.004, substeps=16, grasp_mode="friction", stop_after=None):
    import genesis as gs
    from topogym.utils.franka import initialize_franka_controller
    from topogym.robot.gripper import robotiq_joint_targets

    plan_dir, output = Path(plan_dir).resolve(), Path(output).resolve()
    plan = json.loads((plan_dir / "plan.json").read_text())
    if not plan["passed"]:
        raise ValueError("A complete collision-checked robot plan is required")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True)
    shutil.copytree(plan_dir, output / "planning")
    cfg = OmegaConf.load(plan_dir / "config.yaml")
    # The source 2F-85 tendon uses Kp=100, Kv=10, force limit=5 with
    # coefficient 0.5 on each driver. Restore that bounded per-driver tuning
    # locally; the shared tabletop defaults deliberately use a softer grasp.
    cfg.robot_control.gripper.robotiq.kp = 50.0
    cfg.robot_control.gripper.robotiq.kv = 5.0
    cfg.robot_control.gripper.robotiq.max_driver_torque_nm = 2.5
    cfg.robot_demo.max_linear_speed_m_s = min(
        float(cfg.robot_demo.max_linear_speed_m_s), 0.035
    )
    cfg.robot_demo.max_angular_speed_rad_s = min(
        float(cfg.robot_demo.max_angular_speed_rad_s), 0.45
    )
    cfg.robot_demo.max_joint_speed_rad_s = min(
        float(cfg.robot_demo.max_joint_speed_rad_s), 0.45
    )
    OmegaConf.update(cfg, "task.physics.noslip_iterations", 100, force_add=True)
    OmegaConf.update(cfg, "task.physics.noslip_tolerance", 1e-12, force_add=True)
    cfg.task.physics.constraint_timeconst = float(
        cfg.task.physics.get("constraint_timeconst", 0.0005)
    )
    OmegaConf.update(
        cfg,
        "robot_demo.settle_max_seconds",
        float(cfg.robot_demo.get("settle_max_seconds", 24.0)),
        force_add=True,
    )
    OmegaConf.update(
        cfg,
        "robot_demo.settled_window_seconds",
        float(cfg.robot_demo.get("settled_window_seconds", 1.0)),
        force_add=True,
    )
    cfg.env.cameras = {}
    cfg.env.sim.dt = dt
    cfg.env.sim.substeps = substeps
    cfg.env.genesis.backend = "cpu"
    cfg.env.genesis.precision = "64"
    cfg.env.renderer.type = "rasterizer"
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    implementation = output / "implementation"
    implementation.mkdir()
    for name in (
        "robot_runtime.py",
        "robot_plan.py",
        "geometry.py",
        "appearance.py",
        "preview.py",
        "templates.py",
        "scene.py",
        "verification.py",
        "family_geometry.py",
        "family_plan.py",
        "supports.py",
        "supported_plan.py",
    ):
        shutil.copy2(Path(__file__).with_name(name), implementation / name)
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output / "assets", include_robot=True
    )
    c = initialize_franka_controller(
        scene=task.scene,
        manifest=task.tabletop.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0,
    )
    solver = task.scene.sim.rigid_solver
    wand = task.wand
    supported = plan.get("supported_pick_place")
    frame = supported["pickup"][0] if supported else plan["frames"][0]
    q = np.asarray(plan["model_qpos"]).copy()
    q[:7] = supported["initial_arm_qpos"] if supported else frame["arm_qpos"]
    for name, value in robotiq_joint_targets(
        supported["open_half_gap_m"] if supported else float(cfg.task.geometry.grip_radius_m) + 0.0001
    ).items():
        name = {
            "right_driver_joint": "finger_joint1",
            "left_driver_joint": "finger_joint2",
        }.get(name, "r85_" + name)
        q[c.robot.get_joint(name).qs_idx_local[0]] = value
    # Reset only. Supported mode starts with the open arm separated from a
    # pre-threaded wand resting on physical wood, then uses joint commands only.
    wand.set_pos(frame["position_m"])
    wand.set_quat(frame["quaternion_wxyz"])
    wand.zero_all_dofs_velocity()
    c.robot.set_qpos(q, zero_velocity=True)
    c.robot.control_dofs_position(q[:7], c.arm_dofs)
    grip_command = (
        0.0  # Bounded closure maintains pressure through wrist reorientation.
    )
    c.set_gripper(supported["open_half_gap_m"] if supported else grip_command, steps=0)
    fingers = {c.robot.get_link(n).idx for n in ("left_finger", "right_finger")}
    robot_links = {
        link.idx for link in c.robot.links if link.idx != c.robot.base_link_idx
    }
    fixtures = {
        task.wire.base_link_idx,
        task.base.base_link_idx,
        task.tabletop.manifest.get("table").base_link_idx,
    }
    fixed_rail = task.origin + task.rotation.apply(task.route.rail)
    first, last = fixed_rail[0], fixed_rail[-1]
    closure = np.vstack(
        (
            fixed_rail,
            [*last[:2], task.origin[2] + task.route.layout.base_size_m[2] / 2],
            [*first[:2], task.origin[2] + task.route.layout.base_size_m[2] / 2],
        )
    )
    mass = float(task.geometry_report["wand_mass_kg"])
    local_com = np.array(task.geometry_report["wand_center_of_mass_m"])
    inertia = np.array(task.geometry_report["wand_inertia_kg_m2"])
    passive_energy = dict(initial_j=None, maximum_j=None, tolerance_j=0.001)
    passive_segments = []
    release_recontacts = 0
    steps = 0
    phase = "supported_start" if supported else "pregrasp_contact"
    grasp = False
    rows = []
    event = None
    maxima = dict(
        robot_fixture_penetration_m=0.0,
        robot_self_penetration_m=0.0,
        wand_penetration_m=0.0,
        tracking_error_m=0.0,
        angular_error_rad=0.0,
        linear_speed_m_s=0.0,
        angular_speed_rad_s=0.0,
    )
    peak_events = {}
    traverse_contacts = 0
    bilateral_traverse_steps = 0
    total_traverse_steps = 0
    finger_contact_count = 0
    base_contact_count = 0
    initial_support = None
    placement_support = None
    links = set()
    started = time.monotonic()
    target_p = None
    target_r = None
    progress = 0.0
    record_stride = round(0.02 / dt)
    if abs(record_stride * dt - 0.02) > 1e-9:
        raise ValueError("dt must divide the 50 Hz recording period")

    def pose():
        return array(wand.get_pos()), Rotation.from_quat(
            array(wand.get_quat())[[1, 2, 3, 0]]
        )

    def mechanical_energy(p, r, velocity, omega):
        com_offset = r.apply(local_com)
        com_velocity = velocity + np.cross(omega, com_offset)
        body_omega = r.inv().apply(omega)
        return float(
            0.5 * mass * (com_velocity @ com_velocity)
            + 0.5 * body_omega @ inertia @ body_omega
            + mass * 9.81 * (p[2] + com_offset[2] - task.origin[2])
        )

    def record():
        p, r = pose()
        link = disk_linking_number(
            p, r.apply([0, 0, 1]), task.route.layout.loop_radius_m, closure
        )
        links.add(int(link))
        rows.append(
            dict(
                time_s=steps * dt,
                physics_step=steps,
                phase=phase,
                progress=progress,
                position_m=p.tolist(),
                quaternion_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                robot_qpos=array(c.robot.get_qpos()).tolist(),
                grasp_constraint_active=grasp,
                finger_contact_count=finger_contact_count,
                base_contact_count=base_contact_count,
                linking_number=int(link),
                linear_speed_m_s=float(np.linalg.norm(array(wand.get_vel()))),
                angular_speed_rad_s=float(np.linalg.norm(array(wand.get_ang()))),
                linear_velocity_m_s=array(wand.get_vel()).tolist(),
                angular_velocity_rad_s=array(wand.get_ang()).tolist(),
                mechanical_energy_j=mechanical_energy(
                    p, r, array(wand.get_vel()), array(wand.get_ang())
                ),
            )
        )
        if abs(link) != 1:
            raise ValueError("Ring lost the threaded state")

    def step():
        nonlocal \
            steps, \
            traverse_contacts, \
            finger_contact_count, \
            bilateral_traverse_steps, \
            total_traverse_steps, \
            release_recontacts, \
            base_contact_count
        task.scene.step()
        steps += 1
        ct = solver.collider.get_contacts(as_tensor=True, to_torch=True)
        a, b, pen = (array(ct[k]) for k in ("link_a", "link_b", "penetration"))
        active = pen > 0
        base_contact_count = int(np.sum(active & (
            ((a == wand.base_link_idx) & (b == task.base.base_link_idx)) |
            ((b == wand.base_link_idx) & (a == task.base.base_link_idx))
        )))
        finger_contact_count = sum(
            bool(
                np.any(
                    active
                    & (
                        ((a == finger) & (b == wand.base_link_idx))
                        | ((b == finger) & (a == wand.base_link_idx))
                    )
                )
            )
            for finger in fingers
        )
        rf = (np.isin(a, list(robot_links)) & np.isin(b, list(fixtures))) | (
            np.isin(b, list(robot_links)) & np.isin(a, list(fixtures))
        )
        rr = np.isin(a, list(robot_links)) & np.isin(b, list(robot_links))
        wm = (a == wand.base_link_idx) | (b == wand.base_link_idx)
        wr = ((a == wand.base_link_idx) & (b == task.wire.base_link_idx)) | (
            (b == wand.base_link_idx) & (a == task.wire.base_link_idx)
        )
        for key, mask in [
            ("robot_fixture_penetration_m", rf),
            ("robot_self_penetration_m", rr),
            ("wand_penetration_m", wm),
        ]:
            maxima[key] = max(maxima[key], float(pen[mask].max(initial=0)))
        if phase == "traverse":
            total_traverse_steps += 1
            bilateral_traverse_steps += int(finger_contact_count == 2)
            traverse_contacts += int(np.any(wr & active))
            if np.any(wr & active):
                raise ValueError("Wire touch during traversal")
        if (
            maxima["robot_fixture_penetration_m"] > 0.0002
            or maxima["robot_self_penetration_m"] > 0.0002
        ):
            raise ValueError("Robot contact penetration exceeded 0.2 mm")
        p, r = pose()
        v = float(np.linalg.norm(array(wand.get_vel())))
        w = float(np.linalg.norm(array(wand.get_ang())))
        maxima["linear_speed_m_s"] = max(maxima["linear_speed_m_s"], v)
        maxima["angular_speed_rad_s"] = max(maxima["angular_speed_rad_s"], w)
        for key, value in (("linear_speed_m_s", v), ("angular_speed_rad_s", w)):
            if value > peak_events.get(key, {}).get("value", -1):
                peak_events[key] = dict(
                    value=value, phase=phase, time_s=steps * dt, progress=progress
                )
        if not np.isfinite(
            np.r_[p, r.as_quat(), array(c.robot.get_qpos()), v, w]
        ).all():
            raise ValueError("Nonfinite physical state")
        released = phase in ("release", "retreat", "settle")
        if v > 3 or w > (150 if released else 30):
            raise ValueError("Unstable ring speed")
        if released:
            robot_wand = (
                (np.isin(a, list(robot_links)) & (b == wand.base_link_idx))
                | (np.isin(b, list(robot_links)) & (a == wand.base_link_idx))
            ) & active
            if not np.any(robot_wand):
                energy = mechanical_energy(
                    p, r, array(wand.get_vel()), array(wand.get_ang())
                )
                if passive_energy["initial_j"] is None:
                    passive_energy["initial_j"] = energy
                    passive_energy["maximum_j"] = energy
                passive_energy["maximum_j"] = max(passive_energy["maximum_j"], energy)
            elif passive_energy["initial_j"] is not None:
                passive_segments.append(dict(passive_energy))
                release_recontacts += 1
                passive_energy.update(initial_j=None, maximum_j=None)
        if target_p is not None and phase == "traverse":
            maxima["tracking_error_m"] = max(
                maxima["tracking_error_m"], float(np.linalg.norm(p - target_p))
            )
            maxima["angular_error_rad"] = max(
                maxima["angular_error_rad"], float((r * target_r.inv()).magnitude())
            )
            if np.linalg.norm(p - target_p) > 0.008:
                raise ValueError("Ring position tracking exceeded 8 mm")
        if steps % record_stride == 0:
            record()
        if steps % round(2 / dt) == 0:
            print(
                f"{steps * dt:.1f}s {phase} progress={progress:.3f}, wall={time.monotonic() - started:.1f}s",
                flush=True,
            )

    feedback_maxima = dict(
        hand_position_correction_m=0.0, hand_orientation_correction_rad=0.0
    )
    result = dict(passed=False, complete=False)

    def free_motion(path):
        """Move the open arm without moving or constraining the resting wand."""
        for first, last in zip(path[:-1], path[1:]):
            qa, qb = np.array(first["arm_qpos"]), np.array(last["arm_qpos"])
            distance = np.linalg.norm(np.array(first["position_m"])-last["position_m"])
            duration = max(np.max(abs(qb-qa))/.25, distance/.025, dt)
            for u in np.linspace(0, 1, max(2, int(np.ceil(duration/dt))+1))[1:]:
                c.robot.control_dofs_position(qa*(1-u)+qb*u, c.arm_dofs)
                step()

    record()
    try:
        if supported:
            # Require a full ungrasped stable window before approaching.
            stable = 0
            for _ in range(round(2.0 / dt)):
                step()
                quiet = (base_contact_count > 0 and finger_contact_count == 0
                         and np.linalg.norm(array(wand.get_vel())) < .002
                         and np.linalg.norm(array(wand.get_ang())) < .02)
                stable = stable + 1 if quiet else 0
            initial_support = dict(stable_seconds=stable*dt, base_contacts=base_contact_count,
                                   finger_contacts=finger_contact_count,
                                   position_error_m=float(np.linalg.norm(pose()[0]-frame["position_m"])),
                                   orientation_error_rad=float((pose()[1]*Rotation.from_quat(np.array(frame["quaternion_wxyz"])[[1,2,3,0]]).inv()).magnitude()))
            if stable*dt < 1 or initial_support["position_error_m"] > .003 or initial_support["orientation_error_rad"] > .06:
                raise ValueError(f"Initial wand is not stably supported: {initial_support}")
            phase = "approach"
            free_motion(supported["approach"])
            phase = "grasp"
            c.set_gripper(grip_command, steps=0)
        for _ in range(round(0.3 / dt)):
            step()
            ct = c.robot.get_contacts(with_entity=wand)
            a, b = array(ct["link_a"]), array(ct["link_b"])
            touched = set(a.tolist()) | set(b.tolist())
            if fingers.issubset(touched):
                break
        else:
            raise ValueError("No simultaneous bilateral finger contact")
        if grasp_mode == "contact_weld":
            solver.add_weld_constraint(c.ee_link.idx, wand.base_link_idx)
            grasp = True
        event = dict(
            physics_step=steps,
            time_s=steps * dt,
            simultaneous_bilateral_contact=True,
            finger_link_ids=sorted(fingers),
        )
        phase = "hold_grasp"
        for _ in range(round(3.0 / dt)):
            step()
        poses = np.array([f["position_m"] for f in plan["frames"]])
        rots = Rotation.from_quat(
            np.array([f["quaternion_wxyz"] for f in plan["frames"]])[:, [1, 2, 3, 0]]
        )
        arms = np.array([f["arm_qpos"] for f in plan["frames"]])
        us = np.array([f["progress"] for f in plan["frames"]])
        segments = np.maximum.reduce(
            (
                np.linalg.norm(np.diff(poses, axis=0), axis=1)
                / cfg.robot_demo.max_linear_speed_m_s,
                (rots[:-1].inv() * rots[1:]).magnitude()
                / cfg.robot_demo.max_angular_speed_rad_s,
                np.max(abs(np.diff(arms, axis=0)), axis=1)
                / cfg.robot_demo.max_joint_speed_rad_s,
                np.full(len(arms) - 1, dt),
            )
        )
        times = np.r_[0, np.cumsum(segments)]
        duration = float(times[-1])
        slerp = Slerp(times, rots)
        from .robot_plan import Kinematics

        kin = Kinematics(cfg)
        retreat_height = float(cfg.robot_demo.get("retreat_height_m", 0.05))
        retreat_seed = arms[-1].copy()
        retreat_p, retreat_r = kin.forward(retreat_seed)
        for z in ([] if supported else np.linspace(0, retreat_height, 31)):
            retreat_seed, pe, re = kin.solve(
                retreat_p + [0, 0, z], retreat_r, retreat_seed
            )
            if pe > 1e-5 or re > 1e-4:
                raise ValueError("Planned retreat exceeds physical joint limits")
        nominal_offset = np.array(plan["hand_offset"])
        nominal_rotation = Rotation.from_quat(plan["hand_rotation_xyzw"])
        arm_correction = np.zeros(7)
        feedback_stride = round(0.02 / dt)

        def update_feedback(guide):
            nonlocal arm_correction
            # Estimate the current grasp transform from measured states. Only
            # robot joint commands change; the free ring remains contact-driven.
            measured_p, measured_r = pose()
            hand_p = c.hand_pos()
            hand_r = Rotation.from_quat(c.hand_quat()[[1, 2, 3, 0]])
            grasp_p = hand_r.inv().apply(measured_p - hand_p)
            grasp_r = hand_r.inv() * measured_r
            desired_hand_r = target_r * grasp_r.inv()
            desired_hand_p = target_p - desired_hand_r.apply(grasp_p)
            nominal_hand_p = target_p + target_r.apply(nominal_offset)
            nominal_hand_r = target_r * nominal_rotation
            dp = float(np.linalg.norm(desired_hand_p - nominal_hand_p))
            dr = float((desired_hand_r * nominal_hand_r.inv()).magnitude())
            feedback_maxima["hand_position_correction_m"] = max(
                feedback_maxima["hand_position_correction_m"], dp
            )
            feedback_maxima["hand_orientation_correction_rad"] = max(
                feedback_maxima["hand_orientation_correction_rad"], dr
            )
            if dp > 0.04 or dr > 0.5:
                raise ValueError(
                    "Grasp correction exceeded the bounded feedback region"
                )
            seed = np.clip(
                guide + arm_correction,
                kin.limits[:, 0] + 1e-5,
                kin.limits[:, 1] - 1e-5,
            )
            arm, pe, re = kin.solve(desired_hand_p, desired_hand_r, seed)
            if pe > 1e-5 or re > 1e-4:
                raise ValueError(f"Measured grasp feedback IK failed: {pe=}, {re=}")
            arm_correction = arm - guide

        def held_motion(path, motion_phase):
            nonlocal phase, target_p, target_r
            phase = motion_phase
            for first, last in zip(path[:-1], path[1:]):
                pa, pb = np.array(first["position_m"]), np.array(last["position_m"])
                qa, qb = np.array(first["arm_qpos"]), np.array(last["arm_qpos"])
                ra, rb = Rotation.from_quat(np.array([first["quaternion_wxyz"], last["quaternion_wxyz"]])[:, [1,2,3,0]])
                duration = max(np.linalg.norm(pb-pa)/.015, (ra.inv()*rb).magnitude()/.25,
                               np.max(abs(qb-qa))/.25, dt)
                rotation = Slerp([0, 1], Rotation.from_quat([ra.as_quat(), rb.as_quat()]))
                for tick, u in enumerate(np.linspace(0,1,max(2,int(np.ceil(duration/dt))+1))[1:]):
                    target_p, target_r = pa*(1-u)+pb*u, rotation(u)
                    guide = qa*(1-u)+qb*u
                    if tick % feedback_stride == 0:
                        update_feedback(guide)
                    c.robot.control_dofs_position(np.clip(guide+arm_correction, kin.limits[:,0]+1e-6, kin.limits[:,1]-1e-6), c.arm_dofs)
                    step()
                    if np.linalg.norm(pose()[0]-target_p) > .008:
                        raise ValueError(f"{motion_phase} tracking exceeded 8 mm")

        if supported:
            held_motion(supported["pickup"], "pickup")
            if stop_after == "pickup":
                raise ValueError("Requested pickup-only diagnostic stop")
        phase = "traverse"
        for tick, t in enumerate(
            np.linspace(0, duration, int(np.ceil(duration / dt)) + 1)
        ):
            guide = np.array([np.interp(t, times, arms[:, j]) for j in range(7)])
            target_p = np.array([np.interp(t, times, poses[:, j]) for j in range(3)])
            target_r = slerp(t)
            progress = float(np.interp(t, times, us))
            if tick % feedback_stride == 0:
                update_feedback(guide)
            command = np.clip(
                guide + arm_correction, kin.limits[:, 0] + 1e-6, kin.limits[:, 1] - 1e-6
            )
            c.robot.control_dofs_position(command, c.arm_dofs)
            step()
        phase = "hold_goal"
        for tick in range(round(0.5 / dt)):
            if tick % feedback_stride == 0:
                update_feedback(arms[-1])
            command = np.clip(
                arms[-1] + arm_correction,
                kin.limits[:, 0] + 1e-6,
                kin.limits[:, 1] - 1e-6,
            )
            c.robot.control_dofs_position(command, c.arm_dofs)
            step()
        final_error = float(np.linalg.norm(pose()[0] - poses[-1]))
        if final_error > 0.004:
            raise ValueError("Goal hold position outside 4 mm")
        if supported:
            held_motion(supported["placement"], "placement")
            supported_steps = 0
            for _ in range(round(.5 / dt)):
                step()
                supported_steps = supported_steps + 1 if base_contact_count else 0
            placement_support = dict(base_contacts=base_contact_count,
                                     supported_seconds=supported_steps*dt,
                                     position_error_m=float(np.linalg.norm(pose()[0]-supported["placement"][-1]["position_m"])))
            if supported_steps*dt < .2 or placement_support["position_error_m"] > .003:
                raise ValueError(f"Handle not placed on its support before release: {placement_support}")
        phase = "release"
        if grasp:
            solver.delete_weld_constraint(c.ee_link.idx, wand.base_link_idx)
        grasp = False
        c.set_gripper(supported["open_half_gap_m"], steps=0) if supported else c.open_gripper(steps=0)
        for _ in range(round(0.8 / dt)):
            step()
        from .robot_plan import Kinematics

        kin = Kinematics(cfg)
        kin.q = array(c.robot.get_qpos()).copy()
        hand_p = c.hand_pos()
        hand_r = Rotation.from_quat(c.hand_quat()[[1, 2, 3, 0]])
        seed = c.arm_qpos()
        phase = "retreat"
        if supported:
            free_motion(supported["retreat"])
        for u in ([] if supported else np.linspace(0, 1, round(1.5 / dt))):
            arm, pe, re = kin.solve(hand_p + [0, 0, retreat_height * u], hand_r, seed)
            if pe > 1e-5 or re > 1e-4:
                raise ValueError("Retreat IK failed")
            c.robot.control_dofs_position(arm, c.arm_dofs)
            seed = arm
            step()
        phase = "settle"
        settled_steps = 0
        settle_start = steps
        settled_window_steps = round(float(cfg.robot_demo.settled_window_seconds) / dt)
        if settled_window_steps < 1 or float(cfg.robot_demo.settle_max_seconds) < 4:
            raise ValueError(
                "Need a positive stable window and at least 4 s settling allowance"
            )
        for _ in range(round(float(cfg.robot_demo.settle_max_seconds) / dt)):
            step()
            quiet = (
                np.linalg.norm(array(wand.get_vel())) < 0.002
                and np.linalg.norm(array(wand.get_ang())) < 0.02
            )
            settled_steps = settled_steps + 1 if quiet else 0
            if (
                (steps - settle_start) * dt >= 4.0
                and settled_steps >= settled_window_steps
                and steps % round(0.04 / dt) == 0
            ):
                break
        while steps % round(0.04 / dt):
            step()
            quiet = (
                np.linalg.norm(array(wand.get_vel())) < 0.002
                and np.linalg.norm(array(wand.get_ang())) < 0.02
            )
            settled_steps = settled_steps + 1 if quiet else 0
        if rows[-1]["physics_step"] != steps:
            record()
        v = float(np.linalg.norm(array(wand.get_vel())))
        w = float(np.linalg.norm(array(wand.get_ang())))
        final_position = pose()[0]
        endpoint_distance = float(np.linalg.norm(final_position - fixed_rail[-1]))
        nearest_end_index = int(
            np.argmin(np.linalg.norm(fixed_rail - final_position, axis=1))
        )
        terminal_reached = endpoint_distance < 0.05 and nearest_end_index >= len(
            fixed_rail
        ) - max(3, round(0.05 / task.route.layout.rail_segment_m))
        if supported:
            terminal_reached = bool(base_contact_count and np.linalg.norm(
                final_position-supported["placement"][-1]["position_m"]) < .003)
        result.update(
            passed=v < 0.002
            and w < 0.02
            and settled_steps >= settled_window_steps
            and maxima["wand_penetration_m"] < 0.0005
            and terminal_reached
            and passive_energy["initial_j"] is not None
            and all(
                s["maximum_j"] <= s["initial_j"] + s["tolerance_j"]
                for s in [*passive_segments, passive_energy]
            ),
            complete=True,
            grasp_released=True,
            final_linear_speed_m_s=v,
            final_angular_speed_rad_s=w,
            goal_position_error_m=final_error,
            terminal_stop_reached=bool(terminal_reached),
            final_distance_to_terminal_stop_m=endpoint_distance,
            robot_release_progress=plan["release_progress"],
            remaining_post_completed_by_gravity=not bool(supported),
            settle_wait_seconds=(steps - settle_start) * dt,
            settled_continuous_seconds=settled_steps * dt,
            settled_window_seconds=float(cfg.robot_demo.settled_window_seconds),
            settle_max_seconds=float(cfg.robot_demo.settle_max_seconds),
        )
    except Exception as exc:
        result.update(error=str(exc), failed_phase=phase)
        print("FAILED:", exc, flush=True)
    finally:
        result.update(
            task_id="buzz_wire_3d",
            instance_id=str(cfg.robot_demo.instance_id),
            dt=dt,
            substeps=substeps,
            precision_bits=64,
            physics_steps=steps,
            simulated_seconds=steps * dt,
            pregrasp_start=not bool(supported),
            supported_pick_place=bool(supported),
            initial_support=initial_support,
            placement_support_before_release=placement_support,
            final_base_contacts=base_contact_count,
            assisted_grasp=grasp_mode == "contact_weld",
            grasp_method=grasp_mode,
            contact_gate=event,
            live_object_pose_overwrites=False,
            live_robot_pose_overwrites=False,
            object_external_wrenches=False,
            robot_gravity_compensation=1.0,
            automatic_neutral_self_collision_filter=False,
            noslip_iterations=int(cfg.task.physics.noslip_iterations),
            noslip_tolerance=float(cfg.task.physics.noslip_tolerance),
            max_contacts=int(cfg.task.physics.get("max_contacts", 512)),
            gripper_half_gap_command_m=grip_command,
            gripper_driver_kp=float(cfg.robot_control.gripper.robotiq.kp),
            gripper_driver_kv=float(cfg.robot_control.gripper.robotiq.kv),
            gripper_max_driver_torque_nm=float(
                cfg.robot_control.gripper.robotiq.max_driver_torque_nm
            ),
            controller="bounded joint position servos with measured grasp pose feedback at 50 Hz",
            feedback_maxima=feedback_maxima,
            feedback_rate_hz=50,
            retreat_height_m=float(cfg.robot_demo.get("retreat_height_m", 0.05)),
            passive_release_energy=passive_energy,
            passive_release_segments=[*passive_segments, passive_energy]
            if passive_energy["initial_j"] is not None
            else passive_segments,
            release_recontact_events=release_recontacts,
            angular_speed_limits_rad_s=dict(grasped=30, released=150),
            controller_force_lower=list(cfg.robot_control.controller.force_lower[:7])
            + [-float(cfg.robot_control.gripper.robotiq.max_driver_torque_nm)] * 2,
            controller_force_upper=list(cfg.robot_control.controller.force_upper[:7])
            + [float(cfg.robot_control.gripper.robotiq.max_driver_torque_nm)] * 2,
            bilateral_traverse_contact_steps=bilateral_traverse_steps,
            total_traverse_steps=total_traverse_steps,
            maxima=maxima,
            peak_events=peak_events,
            traverse_wire_contact_steps=traverse_contacts,
            recorded_linking_numbers=sorted(links),
            full_passive_robot_qpos_recorded=True,
            plan_sha256=sha(plan_dir / "plan.json"),
            contact_measurement_scope="contacts sampled after each outer physics step; not a substep penetration bound",
        )
        save(output / "frames.json", rows)
        save(output / "report.json", result)
        print(json.dumps(result, indent=2), flush=True)
    if not result["passed"]:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dt", type=float, default=0.004)
    parser.add_argument("--substeps", type=int, default=16)
    parser.add_argument("--stop-after", choices=("pickup",))
    parser.add_argument(
        "--grasp-mode", choices=("friction", "contact_weld"), default="friction"
    )
    args = parser.parse_args()
    execute(args.plan, args.output, args.dt, args.substeps, args.grasp_mode, args.stop_after)


if __name__ == "__main__":
    main()
