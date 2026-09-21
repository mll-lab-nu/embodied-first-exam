"""Physical qualification of the fixed spatial wire and free ring/handle.

The fixture actuator uses bounded forces and torques. It is not a robot grasp.
No object poses are overwritten after the initial scene construction.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import time

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.tasks._rigid_geometry import disk_linking_number
from .scene import BuzzWireSceneBuilder

ROOT = Path(__file__).resolve().parents[3]


def array(value):
    return (
        value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)
    )


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


@dataclass(frozen=True)
class PhysicsSettings:
    dt: float = 0.004
    substeps: int = 16
    constraint_timeconst: float = 0.001
    travel_seconds: float = 60.0
    position_gain: float = 300.0
    velocity_gain: float = 10.0
    orientation_gain: float = 225.0
    angular_gain: float = 30.0
    max_force_N: float = 8.0
    max_torque_Nm: float = 0.25
    contact_threshold_N: float = 0.02
    penetration_limit_m: float = 0.0005
    tracking_limit_m: float = 0.008
    angular_limit_rad: float = 0.10
    record_hz: int = 50


def load_config(dt, substeps, backend, config_path=None):
    if config_path:
        cfg = OmegaConf.load(config_path)
    else:
        with initialize_config_dir(
            version_base="1.3", config_dir=str(ROOT / "configs")
        ):
            cfg = compose(config_name="buzz_wire_3d_preview")
    cfg.env.sim.dt = dt
    cfg.env.sim.substeps = substeps
    cfg.env.genesis.backend = backend
    cfg.env.renderer.type = "rasterizer"
    cfg.env.presentation.background = "checker"
    cfg.env.cameras = {}
    return cfg


def setup(output, settings, backend="cuda", config_path=None):
    import genesis as gs

    cfg = load_config(settings.dt, settings.substeps, backend, config_path)
    cfg.task.physics.constraint_timeconst = settings.constraint_timeconst
    gs.init(
        backend=getattr(gs, backend), precision="64", logging_level="warning", seed=0
    )
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    task = BuzzWireSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output / "assets",
        constraint_timeconst=settings.constraint_timeconst,
    )
    return task, cfg


def phase_plan(case, settings):
    if case == "gravity":
        return [("free_drop", 5.0)]
    if case == "contact":
        return [
            ("hold", 1.0),
            ("press", 2.0),
            ("pressed_hold", 1.0),
            ("return", 2.0),
            ("hold_final", 1.0),
        ]
    if case == "traverse":
        return [
            ("hold", 1.0),
            ("traverse", settings.travel_seconds),
            ("hold_final", 1.0),
            ("release", 4.0),
        ]
    raise ValueError(case)


def reference(task, phase, u):
    progress = (
        u
        if phase == "traverse"
        else (1.0 if phase in ("hold_final", "release") else 0.0)
    )
    p, q = task.reference_pose(progress)
    rotation = Rotation.from_quat(q[[1, 2, 3, 0]])
    offset = (
        0.036 * (u * u * (3 - 2 * u))
        if phase == "press"
        else (
            0.036
            if phase == "pressed_hold"
            else (0.036 * (1 - u * u * (3 - 2 * u)) if phase == "return" else 0.0)
        )
    )
    return p + rotation.apply([offset, 0, 0]), rotation, progress


def wrench_command(
    settings,
    mass,
    com,
    inertia,
    p,
    rotation,
    velocity,
    omega,
    target,
    rtarget,
    vtarget,
    wtarget,
):
    """Genesis free joints take world force and *body-frame* torque."""
    force = np.clip(
        settings.position_gain * (target - p)
        + settings.velocity_gain * (vtarget - velocity)
        + np.array([0.0, 0.0, mass * 9.81]),
        -settings.max_force_N,
        settings.max_force_N,
    )
    # Scale angular PD by inertia: scalar torque gains destabilize the light
    # ring-axis at the outer control timestep despite fine solver substeps.
    acceleration = settings.orientation_gain * (rtarget * rotation.inv()).as_rotvec()
    acceleration += settings.angular_gain * (wtarget - omega)
    matrix = rotation.as_matrix()
    world_inertia = matrix @ inertia @ matrix.T
    torque = world_inertia @ acceleration + np.cross(omega, world_inertia @ omega)
    torque += np.cross(rotation.apply(com), force)
    body_torque = rotation.inv().apply(torque)
    return np.r_[
        force, np.clip(body_torque, -settings.max_torque_Nm, settings.max_torque_Nm)
    ]


def run(output, case, settings, backend="cuda", config_path=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Use a new output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    save(
        output / "settings.json",
        dict(case=case, settings=asdict(settings), backend=backend),
    )
    (output / "implementation").mkdir()
    for source in Path(__file__).parent.glob("*.py"):
        shutil.copy2(source, output / "implementation" / source.name)
    started = time.monotonic()
    task, cfg = setup(output, settings, backend, config_path)
    build_seconds = time.monotonic() - started
    wand = task.wand
    mass = task.geometry_report["wand_mass_kg"]
    com = np.asarray(task.geometry_report["wand_center_of_mass_m"])
    inertia = np.asarray(task.geometry_report["wand_inertia_kg_m2"])
    fixed = np.vstack(
        (
            task.route.rail,
            [*task.route.rail[-1, :2], task.route.layout.base_size_m[2] / 2],
            [*task.route.rail[0, :2], task.route.layout.base_size_m[2] / 2],
        )
    )
    fixed = task.origin + task.rotation.apply(fixed)
    phases = phase_plan(case, settings)
    rows = []
    stats = {}
    step = 0
    max_penetration = 0.0
    max_speed = 0.0
    max_angular_speed = 0.0
    error = None
    stride = max(1, round(1 / (settings.record_hz * settings.dt)))
    start = time.monotonic()

    def measured(phase, progress, target, rotation):
        p = array(wand.get_pos()).reshape(3)
        q = array(wand.get_quat()).reshape(4)
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        vel = array(wand.get_vel()).reshape(3)
        omega = array(wand.get_ang()).reshape(3)
        contacts = wand.get_contacts(with_entity=task.wire)
        forces = array(contacts["force_a"]).reshape(-1, 3)
        force = float(np.linalg.norm(forces, axis=1).sum()) if forces.size else 0.0
        native = task.scene.sim.rigid_solver.collider.get_contacts()
        depths = array(native["penetration"])
        penetration = float(depths.max()) if depths.size else 0.0
        return dict(
            step=step,
            time_s=step * settings.dt,
            phase=phase,
            progress=progress,
            position_m=p.tolist(),
            quaternion_wxyz=q.tolist(),
            velocity_m_s=vel.tolist(),
            angular_velocity_rad_s=omega.tolist(),
            target_m=target.tolist(),
            target_quaternion_wxyz=rotation.as_quat()[[3, 0, 1, 2]].tolist(),
            tracking_error_m=float(np.linalg.norm(p - target)),
            angular_error_rad=float((rotation * r.inv()).magnitude()),
            wire_force_N=force,
            penetration_m=penetration,
            linking_number=disk_linking_number(
                p, r.apply([0, 0, 1]), task.route.layout.loop_radius_m, fixed
            ),
        )

    p, r, progress = reference(task, "hold", 0.0)
    rows.append(measured("initial", progress, p, r))
    try:
        for phase, duration in phases:
            count = round(duration / settings.dt)
            sample = dict(
                max_wire_force_N=0.0,
                max_tracking_error_m=0.0,
                max_angular_error_rad=0.0,
                contact_steps=0,
                topology_failures=0,
            )
            for j in range(count):
                u = (j + 1) / count
                # Smooth global start/stop, with arc-length-based reference poses.
                path_u = u * u * (3 - 2 * u) if phase == "traverse" else u
                target, rtarget, progress = reference(task, phase, path_u)
                if case == "contact" and phase == "hold_final":
                    target, rtarget, progress = reference(task, "hold", 0.0)
                if phase not in ("free_drop", "release"):
                    p = array(wand.get_pos()).reshape(3)
                    q = array(wand.get_quat()).reshape(4)
                    rotation = Rotation.from_quat(q[[1, 2, 3, 0]])
                    velocity = array(wand.get_vel()).reshape(3)
                    omega = array(wand.get_ang()).reshape(3)
                    # Finite-difference feedforward at the requested path speed.
                    next_u = min(1.0, (j + 2) / count)
                    if phase == "traverse":
                        next_u = next_u * next_u * (3 - 2 * next_u)
                    pn, rn, _ = reference(task, phase, next_u)
                    if case == "contact" and phase == "hold_final":
                        pn, rn, _ = reference(task, "hold", 0.0)
                    vtarget = (pn - target) / settings.dt
                    wtarget = (rn * rtarget.inv()).as_rotvec() / settings.dt
                    command = wrench_command(
                        settings,
                        mass,
                        com,
                        inertia,
                        p,
                        rotation,
                        velocity,
                        omega,
                        target,
                        rtarget,
                        vtarget,
                        wtarget,
                    )
                    wand.control_dofs_force(command)
                else:
                    command = np.zeros(6)
                    wand.control_dofs_force(command)
                task.scene.step()
                step += 1
                state = measured(phase, progress, target, rtarget)
                state["applied_wrench"] = command.tolist()
                if not all(
                    np.isfinite(state[k]).all()
                    for k in (
                        "position_m",
                        "quaternion_wxyz",
                        "velocity_m_s",
                        "angular_velocity_rad_s",
                    )
                ):
                    raise RuntimeError("Non-finite state")
                max_speed = max(max_speed, float(np.linalg.norm(state["velocity_m_s"])))
                max_angular_speed = max(
                    max_angular_speed,
                    float(np.linalg.norm(state["angular_velocity_rad_s"])),
                )
                max_penetration = max(max_penetration, state["penetration_m"])
                sample["max_wire_force_N"] = max(
                    sample["max_wire_force_N"], state["wire_force_N"]
                )
                sample["max_tracking_error_m"] = max(
                    sample["max_tracking_error_m"], state["tracking_error_m"]
                )
                sample["max_angular_error_rad"] = max(
                    sample["max_angular_error_rad"], state["angular_error_rad"]
                )
                sample["contact_steps"] += int(
                    state["wire_force_N"] > settings.contact_threshold_N
                )
                sample["topology_failures"] += int(abs(state["linking_number"]) != 1)
                if step % stride == 0 or j == count - 1:
                    rows.append(state)
                if j % max(1, round(2 / settings.dt)) == 0:
                    print(
                        f"{case} {phase} t={step * settings.dt:.3f} error={state['tracking_error_m']:.5f} force={state['wire_force_N']:.3f} penetration={state['penetration_m']:.6f}",
                        flush=True,
                    )
            sample["final_tracking_error_m"] = state["tracking_error_m"]
            stats[phase] = sample
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    save(output / "frames.json", rows)
    final_window = [s for s in rows if s["time_s"] >= rows[-1]["time_s"] - 1.0]
    positions = np.asarray([s["position_m"] for s in final_window])
    drift = float(np.linalg.norm(positions - positions[-1], axis=1).max())
    last_speed = float(np.linalg.norm(rows[-1]["velocity_m_s"]))
    checks = dict(
        completed=error is None and len(stats) == len(phases),
        penetration_ok=max_penetration < settings.penetration_limit_m,
        remained_threaded=all(s["topology_failures"] == 0 for s in stats.values()),
        bounded_velocities=max_speed < 3.0 and max_angular_speed < 30.0,
    )
    if case == "gravity":
        checks.update(settled=drift < 0.004 and last_speed < 0.02)
    elif case == "contact":
        checks.update(
            initial_hold_clear=stats.get("hold", {}).get(
                "max_wire_force_N", float("inf")
            )
            < settings.contact_threshold_N,
            touch_detected=stats.get("pressed_hold", {}).get("contact_steps", 0) > 20,
            wall_blocks_target=stats.get("pressed_hold", {}).get(
                "final_tracking_error_m", 0.0
            )
            > 0.008,
            returned_to_center=stats.get("hold_final", {}).get(
                "final_tracking_error_m", float("inf")
            )
            < 0.003,
            orientation_stable=all(
                s["max_angular_error_rad"] < settings.angular_limit_rad
                for s in stats.values()
            ),
        )
    else:
        moving = stats.get("traverse", {})
        checks.update(
            full_route_clear=moving.get("contact_steps", 1) == 0,
            path_tracking=moving.get("max_tracking_error_m", float("inf"))
            < settings.tracking_limit_m,
            orientation_tracking=moving.get("max_angular_error_rad", float("inf"))
            < settings.angular_limit_rad,
            reached_goal=stats.get("hold_final", {}).get(
                "final_tracking_error_m", float("inf")
            )
            < 0.003,
            released_and_settled=drift < 0.004 and last_speed < 0.02,
        )
    result = dict(
        task_id="buzz_wire_3d",
        variant=task.route.layout.template_id,
        case=case,
        passed=all(checks.values()),
        checks=checks,
        scope="fixed rigid guide and free tool; finite-wrench fixture qualification, not a robot execution",
        settings=asdict(settings),
        phases=stats,
        error=error,
        physics_steps=step,
        measurement_scope="contacts, penetration and topology after each outer step; internal substeps are not logged",
        simulated_seconds=step * settings.dt,
        maximum_penetration_m=max_penetration,
        maximum_speed_m_s=max_speed,
        maximum_angular_speed_rad_s=max_angular_speed,
        final_window_drift_m=drift,
        final_speed_m_s=last_speed,
        pose_writes_after_reset=0,
        full_robot_task_verified=False,
        robot_present=False,
        build_seconds=build_seconds,
        rollout_wall_seconds=time.monotonic() - start,
        genesis_version=version("genesis-world"),
        precision="64",
        backend=backend,
        geometry=task.geometry_report,
        geometric_reference=task.clearance_report,
    )
    save(output / "report.json", result)
    print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--case", choices=("gravity", "contact", "traverse"), required=True)
    p.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    p.add_argument("--dt", type=float, default=0.004)
    p.add_argument("--substeps", type=int, default=16)
    p.add_argument("--travel-seconds", type=float, default=60.0)
    p.add_argument("--config", type=Path)
    p.add_argument("--constraint-timeconst", type=float, default=0.001)
    args = p.parse_args()
    if (
        args.dt <= 0
        or args.substeps < 1
        or args.travel_seconds <= 0
        or args.constraint_timeconst <= 0
    ):
        p.error("Positive step and duration required")
    result = run(
        args.output,
        args.case,
        PhysicsSettings(
            dt=args.dt,
            substeps=args.substeps,
            travel_seconds=args.travel_seconds,
            constraint_timeconst=args.constraint_timeconst,
        ),
        args.backend,
        args.config,
    )
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
