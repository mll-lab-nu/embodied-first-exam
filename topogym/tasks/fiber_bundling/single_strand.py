"""Straighten one passive wire using only motion of the thick cable root.

The fixed ring never moves. The trunk root is an explicit kinematic grasp
fixture; this local demonstration does not claim executed robot grasping.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .geometry import FiberLayout, generate_assets, shape_in_root_frame, write_bundle
from .scene import as_numpy, cable_state


def default_plan(layout):
    tip = layout.fibers()[0][-1]
    return [
        dict(name="settle", seconds=.2, offset=[0., 0., 0.]),
        dict(name="align_tip", seconds=.3, offset=[0., .010-tip[1], -tip[2]]),
        dict(name="capture_tip", seconds=.55, offset=[.039, .010-tip[1], -tip[2]]),
        dict(name="feed_and_comb", seconds=.6, offset=[.062, -.0082, 0.]),
        dict(name="recenter", seconds=.45, offset=[.065, 0., 0.]),
        dict(name="draw_back", seconds=1., offset=[.020, .008, 0.]),
        dict(name="verify_feed", seconds=.6, offset=[.060, 0., 0.]),
        dict(name="trim_axis", seconds=.3, offset=[.060, 0., 0.], yaw_deg=-.75),
        dict(name="hold", seconds=.3, offset=[.060, 0., 0.]),
    ]


def strand_metrics(paths, ring_center, layout, target=0):
    strand = np.asarray(paths)[target]
    local = shape_in_root_frame(paths)[target]
    vectors = np.diff(strand, axis=0)
    angles = np.degrees(np.arccos(np.clip(vectors[:, 0]/np.linalg.norm(vectors, axis=1), -1, 1)))
    relative = strand-ring_center
    cross_radii = []
    for a, b in zip(relative[:-1], relative[1:]):
        if min(a[0], b[0]) <= 0 <= max(a[0], b[0]) and abs(b[0]-a[0]) > 1e-12:
            crossing = a+(b-a)*(-a[0]/(b[0]-a[0]))
            cross_radii.append(float(np.linalg.norm(crossing[1:])))
    envelope = float(np.linalg.norm(relative[:, 1:], axis=-1).max()+layout.fiber_radius_m)
    return dict(tip_angle_deg=float(angles[-1]), max_segment_angle_deg=float(angles.max()),
                root_frame_tip_angle_deg=float(np.degrees(np.arccos(np.clip(
                    (local[-1, 0]-local[-2, 0])/np.linalg.norm(local[-1]-local[-2]), -1, 1)))),
                axial_reach_m=float(strand[-1, 0]-strand[0, 0]),
                tip_beyond_ring_m=float(relative[-1, 0]-layout.ring_tube_radius_m-layout.fiber_radius_m),
                radial_envelope_m=envelope,
                fits_aperture_projection=bool(envelope < layout.minimum_aperture_radius),
                plane_crossing_radii_m=cross_radii,
                crosses_aperture=bool(cross_radii and max(cross_radii)+layout.fiber_radius_m < layout.minimum_aperture_radius))


def main():
    import genesis as gs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/environment_bootstrap/fiber_bundling/single_strand_demo"))
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--legacy-free", action="store_true", help="Explicitly run the historical detached-cable fixture")
    args = parser.parse_args()
    if not args.legacy_free:
        parser.error("The current task uses a fixed terminal. This historical free-cable fixture requires --legacy-free and cannot validate anchored_terminal_v2.")
    if not np.isfinite(args.dt) or args.dt <= 0:
        raise ValueError("dt must be positive and finite")
    args.output.mkdir(parents=True, exist_ok=True)
    layout, _ = generate_assets(args.output/"assets")
    plan = json.loads(args.plan.read_text()) if args.plan else default_plan(layout)
    if not plan or any(np.asarray(p["offset"]).shape != (3,) or
                       not np.isfinite(p["offset"]).all() or
                       not np.isfinite(p.get("yaw_deg", 0.)) or
                       not np.isfinite(p["seconds"]) or p["seconds"] < args.dt for p in plan):
        raise ValueError("Each phase needs a finite xyz offset and at least one simulation step")
    (args.output/"plan.json").write_text(json.dumps(plan, indent=2)+"\n")
    path = (args.output/"assets/bundle_fixture.xml").resolve()
    write_bundle(path, layout, layout.fibers(), fixture=True)
    gs.init(backend=gs.cuda, logging_level="warning", seed=layout.seed)
    scene = gs.Scene(show_viewer=False,
        sim_options=gs.options.SimOptions(dt=args.dt, substeps=4, gravity=(0, 0, -9.81)),
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            iterations=100, max_collision_pairs=4096, constraint_timeconst=.002))
    origin = np.array([0., 0., .5])
    ring_center = origin+[layout.trunk_length_m+.1, 0., 0.]
    cable = scene.add_entity(gs.morphs.MJCF(file=str(path), pos=origin, decimate=False),
        material=gs.materials.Rigid(friction=.35, gravity_compensation=1.))
    ring = scene.add_entity(gs.morphs.URDF(file=str((args.output/"assets/ring.urdf").resolve()),
        pos=ring_center, euler=(0, 90, 0), fixed=True, merge_fixed_links=False, decimate=False),
        material=gs.materials.Rigid(friction=.35))
    scene.build()
    target_links = {cable.get_link(f"fiber_00_{i:02d}").idx for i in range(layout.fiber_segments)}
    history, samples, qpos, root_positions, sample_times, sample_phases = [], [], [], [], [], []
    root_quaternions = []
    max_root_error, max_penetration, contact_steps, target_contact_steps = 0., 0., 0, 0
    step = 0

    def sample(phase):
        nonlocal max_root_error
        state = cable_state(cable, layout)
        max_root_error = max(max_root_error, state["max_root_error_m"])
        metric = strand_metrics(state["fibers_m"], ring_center, layout)
        samples.append(state["fibers_m"])
        qpos.append(as_numpy(cable.get_qpos()).copy())
        root_positions.append(as_numpy(cable.get_pos()).copy())
        root_quaternions.append(as_numpy(cable.get_quat()).copy())
        sample_times.append(step*args.dt)
        sample_phases.append(phase)
        return metric

    initial = sample("initial")
    offset = np.zeros(3)
    yaw = 0.
    for phase in plan:
        start, end = offset.copy(), np.asarray(phase["offset"])
        yaw_start, yaw_end = yaw, np.radians(phase.get("yaw_deg", np.degrees(yaw)))
        count = round(phase["seconds"]/args.dt)
        for k in range(count):
            t = (k+1)/count
            offset = start+(end-start)*(.5-.5*np.cos(np.pi*t))
            cable.set_pos(origin+offset, zero_velocity=False)
            yaw = yaw_start+(yaw_end-yaw_start)*(.5-.5*np.cos(np.pi*t))
            if yaw_start != 0. or yaw_end != 0.:
                cable.set_quat([np.cos(yaw/2), 0., 0., np.sin(yaw/2)], zero_velocity=False)
            scene.step()
            step += 1
            contacts = cable.get_contacts(with_entity=ring)
            ids = np.concatenate([as_numpy(contacts[key]).reshape(-1) for key in ("link_a", "link_b")])
            contact_steps += int(len(ids) > 0)
            target_contact_steps += int(any(int(i) in target_links for i in ids))
            native = scene.sim.rigid_solver.collider.get_contacts()
            penetration = as_numpy(native["penetration"])
            if penetration.size:
                max_penetration = max(max_penetration, float(penetration.max()))
            if step % 10 == 0:
                metric = sample(phase["name"])
            if k == count-1:
                metric = sample(phase["name"])
                history.append(dict(phase=phase["name"], time=step*args.dt, **metric))
                print(json.dumps(history[-1]), flush=True)
        # Save a recoverable diagnostic after every phase.
        np.savez_compressed(args.output/"trajectory.npz", fibers=np.asarray(samples), qpos=np.asarray(qpos),
            root_positions=np.asarray(root_positions), root_quaternions=np.asarray(root_quaternions),
            times=np.asarray(sample_times), phases=np.asarray(sample_phases))
        (args.output/"phase_metrics.json").write_text(json.dumps(history, indent=2)+"\n")
    final = history[-1]
    checks = dict(target_contact=target_contact_steps > 0,
        tip_through=final["tip_beyond_ring_m"] > .010,
        crosses_inside_aperture=final["crosses_aperture"],
        whole_wire_fits_aperture_projection=final["fits_aperture_projection"],
        tip_aligned=final["tip_angle_deg"] < 15.,
        shape_straightened=final["root_frame_tip_angle_deg"] < initial["root_frame_tip_angle_deg"]-15.,
        roots_preserved=max_root_error < 1e-5,
        bounded_penetration=max_penetration < .0006,
        finite_state=bool(np.isfinite(samples).all()))
    report = dict(scope="single_wire_alignment_by_kinematic_trunk_fixture", passed=all(checks.values()),
        checks=checks, layout=asdict(layout), dt=args.dt, substeps=4, simulation_steps=step,
        simulated_seconds=step*args.dt, target_fiber=0, target_color="red", initial=initial, final=final,
        ring_center_m=ring_center.tolist(), max_root_error_m=max_root_error,
        max_penetration_m=max_penetration, ring_contact_steps=contact_steps, target_contact_steps=target_contact_steps,
        controlled_body="trunk_00 only; kinematic grasp fixture", ring_pose_writes=0,
        fiber_pose_writes=0, fiber_force_commands=0, robot_grasp_executed=False,
        full_bundle_threading_verified=False, history=history)
    (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("history", "layout")}, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
