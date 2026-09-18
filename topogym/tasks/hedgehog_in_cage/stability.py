"""Headless dynamics checks; forces act on a free body through the solver."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import ROOT


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="runs/environment_bootstrap/hedgehog_in_cage/classic_wood")
    parser.add_argument("--substeps", type=int, default=10)
    parser.add_argument("--dt", type=float, default=.005)
    parser.add_argument("--timeconst", type=float, default=.0012)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--initial-path", help="Use the first pose of a verified escape path at reset")
    parser.add_argument("--duration", type=float, default=10.)
    parser.add_argument("--settle-only", action="store_true")
    parser.add_argument("--noslip", type=int, default=5)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg = OmegaConf.load(output / "config.yaml")
    cfg.env.cameras = {}
    cfg.env.renderer.type = "rasterizer"
    cfg.env.sim.dt, cfg.env.sim.substeps = args.dt, args.substeps
    cfg.task.physics = dict(constraint_timeconst=args.timeconst, friction=.3, iterations=100,
        noslip_iterations=args.noslip)
    if args.initial_path:
        path = json.loads(Path(args.initial_path).read_text())
        if not path["found"]:
            raise ValueError("Initial path is not verified")
        q = np.asarray(path["path"][0])
        cfg.task.initial_pose = dict(position_m=q[:3].tolist(), quaternion_wxyz=q[[6,3,4,5]].tolist())
    import genesis as gs
    from .scene import HedgehogSceneBuilder
    from topogym.utils.franka import initialize_franka_controller
    gs.init(backend=gs.cuda, logging_level="warning", seed=0)
    task = HedgehogSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output / "assets", reuse_assets=True)
    controller = initialize_franka_controller(scene=task.scene, manifest=task.manifest,
        robot_cfg=cfg.robot_control, settle_steps=0)
    initial_state = task.scene.get_state()
    ball = task.hedgehog
    link = ball.links[0].idx
    cage_rotation = Rotation.from_euler("z", float(cfg.task.yaw_deg), degrees=True)
    cases = [(f"settle_{i}", None) for i in range(args.trials)]
    if not args.settle_only:
        cases += [("push_x_release", "x"), ("push_y_release", "y"), ("twist_release", "rz")]
    results = []
    initial_label = Path(args.initial_path).stem + "_" if args.initial_path else ""
    prefix = f"stability_v2_{initial_label}h{args.dt / args.substeps:.7f}"
    if args.duration != 10 or args.noslip:
        prefix += f"_t{args.duration:g}_noslip{args.noslip}"
    with (output / f"{prefix}_states.jsonl").open("w") as trace:
        for label, action in cases:
            task.scene.reset(initial_state)
            # Reset robot coordinates without advancing unrecorded physics.
            controller.reset_home(settle_steps=0)
            rows = []
            for step in range(round(args.duration / args.dt)):
                time = (step + 1) * args.dt
                force, torque = np.zeros(3), np.zeros(3)
                if action and 3 < time < 4:
                    envelope = np.sin(np.pi * (time - 3)) ** 2
                    if action == "rz":
                        torque[2] = .015 * envelope
                    else:
                        force[0 if action == "x" else 1] = 1.0 * envelope
                        force = cage_rotation.apply(force)
                    task.scene.sim.rigid_solver.apply_links_external_force(force[None], [link], ref="link_com")
                    task.scene.sim.rigid_solver.apply_links_external_torque(torque[None], [link])
                task.scene.step()
                pos, quat = array(ball.get_pos()), array(ball.get_quat())
                vel, ang = array(ball.get_vel()), array(ball.get_ang())
                contacts = ball.get_contacts()
                penetrations = array(contacts["penetration"])
                contact_forces = array(contacts["force_a"])
                row = dict(case=label, time_s=time, position_m=pos.tolist(), quaternion_wxyz=quat.tolist(),
                    linear_speed_m_s=float(np.linalg.norm(vel)), angular_speed_rad_s=float(np.linalg.norm(ang)),
                    penetration_m=float(max(0, penetrations.max(initial=0))),
                    contact_force_n=float(np.linalg.norm(contact_forces, axis=-1).max(initial=0)),
                    external_force_n=force.tolist(), external_torque_nm=torque.tolist())
                if not np.all(np.isfinite(np.r_[pos, quat, vel, ang])):
                    raise RuntimeError(f"Non-finite state in {label}")
                rows.append(row)
                if step % 4 == 0:
                    trace.write(json.dumps(row) + "\n")
            tail = [r for r in rows if r["time_s"] >= args.duration-2]
            positions = np.asarray([r["position_m"] for r in tail])
            result = dict(case=label, duration_s=args.duration,
                max_penetration_m=max(r["penetration_m"] for r in rows),
                max_contact_force_n=max(r["contact_force_n"] for r in rows),
                final_2s_max_speed_m_s=max(r["linear_speed_m_s"] for r in tail),
                final_2s_max_angular_speed_rad_s=max(r["angular_speed_rad_s"] for r in tail),
                final_2s_drift_m=float(np.max(np.linalg.norm(positions-positions[0], axis=1))),
                final_position_m=rows[-1]["position_m"], final_quaternion_wxyz=rows[-1]["quaternion_wxyz"])
            result["passed"] = bool(result["max_penetration_m"] < .0001 and
                result["final_2s_max_speed_m_s"] < .001 and
                result["final_2s_max_angular_speed_rad_s"] < np.deg2rad(.5) and
                result["final_2s_drift_m"] < .0002)
            results.append(result)
            print(json.dumps(result), flush=True)
            report = dict(scope="gravity_settling_and_finite_force_release_only", dt=args.dt,
                substeps=args.substeps, constraint_timeconst=args.timeconst, friction=.3,
                noslip_iterations=args.noslip,
                actual_hedgehog_sol_params=array(task.scene.sim.rigid_solver.get_sol_params(
                    geoms_idx=np.arange(ball.geom_start, ball.geom_end))).tolist(),
                density_kg_m3=2700, mass_kg=task.asset_report["hedgehog"]["mass_kg"],
                live_object_pose_overwrites=False, grasp_assistance=False,
                contact_sampling_interval_s=args.dt, cases=results,
                initial_pose_source=args.initial_path or "asset_report",
                asset_manifest_sha256=hashlib.sha256((output/"assets/sha256.json").read_bytes()).hexdigest(),
                unrecorded_reset_warmup_steps=0, initial_impact_covered=True,
                all_passed=all(r["passed"] for r in results), complete=len(results)==len(cases),
                extraction_verified=False, full_physics_qualification=False)
            (output / f"{prefix}.json").write_text(json.dumps(report, indent=2)+"\n")
    print(f"Report: {output / (prefix + '.json')}", flush=True)


if __name__ == "__main__":
    main()
