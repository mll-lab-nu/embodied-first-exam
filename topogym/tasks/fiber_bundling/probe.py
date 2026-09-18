"""Paired fixture experiment: move only the thick cable root toward a ring.

This is a kinematic fixture diagnostic, not a robot grasp or a threading oracle.
After loading, the ring alone is moved away to test retained deformation.
The no-ring control uses the identical motion; no fiber pose/force is commanded.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .geometry import FiberLayout, generate_assets, shape_in_root_frame, write_bundle
from .scene import as_numpy, cable_state


def main():
    import genesis as gs

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/environment_bootstrap/fiber_bundling/contact_probe"))
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--release-steps", type=int, default=750,
                        help="Passive relaxation steps after removing ring contact; at least 200")
    args = parser.parse_args()
    if args.dt <= 0 or args.steps < 100 or args.release_steps < 200:
        raise ValueError("Use a positive dt, at least 100 loading and 200 release steps")
    args.output.mkdir(parents=True, exist_ok=True)
    layout, _ = generate_assets(args.output/"assets")
    path = (args.output/"assets/bundle_fixture.xml").resolve()
    write_bundle(path, layout, layout.fibers(), fixture=True)
    gs.init(backend=gs.cuda, logging_level="warning", seed=layout.seed)
    scene = gs.Scene(show_viewer=False,
        sim_options=gs.options.SimOptions(dt=args.dt, substeps=4, gravity=(0, 0, -9.81)),
        rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
            iterations=100, max_collision_pairs=4096, constraint_timeconst=.002))
    cables = []
    for i in range(2):
        cables.append(scene.add_entity(gs.morphs.MJCF(file=str(path), pos=(0, i*.6, .5), decimate=False),
            material=gs.materials.Rigid(friction=.35, gravity_compensation=1.)))
    ring_distance = layout.fiber_length_m+.02
    stroke = ring_distance-.007
    ring = scene.add_entity(gs.morphs.URDF(file=str((args.output/"assets/ring.urdf").resolve()),
        pos=(layout.trunk_length_m+ring_distance, 0, .5), euler=(0, 90, 0), fixed=True,
        merge_fixed_links=False, decimate=False), material=gs.materials.Rigid(friction=.35))
    print("Building paired ring-contact and free-space controls", flush=True)
    scene.build()
    initial = [cable_state(c, layout)["fibers_m"].copy() for c in cables]
    contact_steps, max_force, max_penetration, max_root_error = 0, 0., 0., 0.
    trace = []
    settle_steps = 100
    for _ in range(settle_steps):
        scene.step()
    drift = [float(np.linalg.norm(cable_state(c, layout)["fibers_m"]-p, axis=-1).max())
             for c, p in zip(cables, initial)]
    for k in range(args.steps):
        # Ease in/out; stroke stops before the trunk reaches the aperture.
        t = (k+1)/args.steps
        dx = stroke*(.5-.5*np.cos(np.pi*t))
        for i, cable in enumerate(cables):
            cable.set_pos((dx, i*.6, .5), zero_velocity=False)
        scene.step()
        contacts = cables[0].get_contacts(with_entity=ring)
        forces = as_numpy(contacts["force_a"]).reshape(-1, 3)
        if len(forces):
            contact_steps += 1
            max_force = max(max_force, float(np.linalg.norm(forces, axis=1).max()))
        native = scene.sim.rigid_solver.collider.get_contacts()
        penetration = as_numpy(native["penetration"])
        if penetration.size:
            max_penetration = max(max_penetration, float(penetration.max()))
        if k % 50 == 0 or k == args.steps-1:
            states = [cable_state(c, layout) for c in cables]
            max_root_error = max(max_root_error, *(s["max_root_error_m"] for s in states))
            deflection = [float(np.linalg.norm(s["fibers_m"]-p-[dx, 0, 0], axis=-1).max())
                          for s, p in zip(states, initial)]
            trace.append(dict(step=k+1, dx_m=dx, max_deflection_m=deflection))
            print(f"Step {k+1}/{args.steps}: ring/control deflection {deflection}", flush=True)
    final = [cable_state(c, layout)["fibers_m"] for c in cables]
    contact_difference = float(np.linalg.norm(final[0]-(final[1]-[0, .6, 0]), axis=-1).max())
    bending_difference = float(np.linalg.norm(shape_in_root_frame(final[0])-shape_in_root_frame(final[1]), axis=-1).max())
    # Explicit test-only contact removal: relocate the fixture to empty space.
    # Do not reset, freeze, zero velocities or write any cable state at release.
    ring.set_pos((layout.trunk_length_m+ring_distance+.5, 0, .5))
    release_contact_steps = 0
    release_trace = []
    release_reference = None
    tail_start = args.release_steps-max(50, args.release_steps//5)
    max_late_shape_drift = 0.
    for k in range(args.release_steps):
        scene.step()
        release_contact_steps += int(len(cables[0].get_contacts(with_entity=ring)["force_a"]) > 0)
        if k >= tail_start or k % 100 == 0 or k == args.release_steps-1:
            states = [cable_state(c, layout) for c in cables]
            local = [shape_in_root_frame(s["fibers_m"]) for s in states]
            max_root_error = max(max_root_error, *(s["max_root_error_m"] for s in states))
            if k == tail_start:
                release_reference = local[0].copy()
            if release_reference is not None:
                max_late_shape_drift = max(max_late_shape_drift,
                    float(np.linalg.norm(local[0]-release_reference, axis=-1).max()))
            if k % 100 == 0 or k == args.release_steps-1:
                retained = float(np.linalg.norm(local[0]-local[1], axis=-1).max())
                release_trace.append(dict(step=k+1, retained_bending_m=retained))
                print(f"Release {k+1}/{args.release_steps}: retained bending {retained:.6f} m", flush=True)
    released = [cable_state(c, layout)["fibers_m"] for c in cables]
    residual = float(np.linalg.norm(shape_in_root_frame(released[0])-shape_in_root_frame(released[1]), axis=-1).max())
    retention = residual/max(bending_difference, 1e-12)
    checks = dict(no_gravity_sag=max(drift) < 1e-4,
        ring_contact_recorded=contact_steps > 0 and max_force > 1e-5,
        contact_changes_fiber_shape=bending_difference > .003,
        root_attachments_preserved=max_root_error < 1e-5,
        bounded_penetration=max_penetration < .0006,
        finite_state=bool(all(np.isfinite(p).all() for p in final+released)),
        external_contact_removed=release_contact_steps == 0,
        residual_deformation_retained=residual > .003 and retention > .7,
        released_shape_settled=max_late_shape_drift < .0002)
    report = dict(scope="local_kinematic_trunk_fixture_contact_and_release; not complete threading",
        passed=all(checks.values()), checks=checks, dt=args.dt, substeps=4, driven_steps=args.steps,
        settle_steps=settle_steps, release_steps=args.release_steps,
        simulated_seconds=(args.steps+settle_steps+args.release_steps)*args.dt,
        fiber_count=layout.fiber_count, fiber_length_m=layout.fiber_length_m,
        ring_distance_from_roots_m=ring_distance, fixture_stroke_m=stroke,
        max_free_settle_displacement_m=drift,
        contact_steps=contact_steps, max_ring_contact_force_N=max_force,
        max_penetration_m=max_penetration, max_root_error_m=max_root_error,
        ring_vs_control_max_shape_difference_m=contact_difference,
        ring_vs_control_fiber_bending_in_root_frame_m=bending_difference,
        release_seconds=args.release_steps*args.dt,
        release_ring_contact_steps=release_contact_steps,
        residual_bending_after_release_m=residual,
        retained_bending_ratio=retention,
        max_shape_drift_late_release_m=max_late_shape_drift,
        late_release_window_seconds=(args.release_steps-tail_start)*args.dt,
        release_method="only the ring is relocated 0.5 m in +x; no cable state writes or velocity resets",
        constitutive_scope="zero-stiffness damped-joint shape retention; not calibrated copper elastoplasticity",
        controlled_body="trunk_00 fixed fixture; kinematic position writes each step",
        fiber_pose_writes=0, fiber_force_commands=0, full_threading_verified=False,
        trace=trace, release_trace=release_trace)
    (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    np.savez_compressed(args.output/"states.npz", initial=np.asarray(initial), final=np.asarray(final),
                        released=np.asarray(released))
    from .review import write_review
    write_review(args.output)
    print(json.dumps({k: v for k, v in report.items() if k not in ("trace", "release_trace")}, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
