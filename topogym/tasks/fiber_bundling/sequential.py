"""Use the outside of the fixed ring to prepare wires, then feed the bundle.

The trunk alone is translated/rolled. A chosen tip is read for trunk feedback,
never commanded. Previously prepared wires must preserve their local shape.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from .geometry import FiberLayout, shape_in_root_frame
from .scene import as_numpy
from .single_strand import strand_metrics
from .validation import FixtureExperiment, LIMITS


def local_metrics(paths, layout):
    local = shape_in_root_frame(paths)
    radii = np.linalg.norm(local[:, :, 1:], axis=-1).max(axis=1)+layout.fiber_radius_m
    vectors = np.diff(local, axis=1)
    forward = (vectors[:, :, 0] > 0).all(axis=1)
    return local, radii, forward


def execute(args):
    if sorted(args.order) != list(range(FiberLayout().fiber_count)):
        raise ValueError("order must contain each wire exactly once")
    if not np.isfinite(args.dt) or not 0 < args.dt <= .002:
        raise ValueError("Use a finite positive dt no larger than 2 ms")
    if not np.isfinite(args.press_radius) or not .025 < args.press_radius < .060:
        raise ValueError("press-radius must be between 25 and 60 mm")
    gate = json.loads(args.stability.read_text())
    if not gate["stability_passed"]:
        raise RuntimeError("Stability gate has not passed; full-bundle execution is disabled")
    spec = dict(strategy="outer_rim_side_press_each_wire_then_one_axial_feed",
        order=args.order, press_radius_m=args.press_radius, initial_lateral_radius_m=.060,
        protected_shape_tolerance_m=.0005, preparation_margin_m=.0003,
        stability_gate=str(args.stability), backend=args.backend, dt=args.dt,
        controlled_body="trunk_00 only", tip_feedback="read chosen tip x/z; translate trunk to keep tip in ring mid-plane and avoid lateral slip")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"plan.json").write_text(json.dumps(spec, indent=2)+"\n")
    exp = FixtureExperiment(args.output, dt=args.dt, backend=args.backend, stand=True)
    initial = exp.first.copy()
    protected, changes, events = {}, {}, []
    passage_seen = np.zeros(exp.layout.fiber_count, dtype=bool)
    passage_outside = np.zeros(exp.layout.fiber_count, dtype=bool)
    pushing = False

    def observe(paths):
        local = shape_in_root_frame(paths)
        for i, reference in protected.items():
            changes[i] = max(changes.get(i, 0.), float(np.linalg.norm(local[i]-reference, axis=-1).max()))
        if pushing:
            for i in range(exp.layout.fiber_count):
                metric = strand_metrics(paths, exp.ring_center, exp.layout, i)
                passage_seen[i] |= metric["crosses_aperture"]
                passage_outside[i] |= any(r+exp.layout.fiber_radius_m >
                    exp.layout.minimum_aperture_radius+LIMITS["contact_penetration_m"]
                    for r in metric["plane_crossing_radii_m"])

    exp.observer = observe
    failure = None

    def check_physics():
        bad = {k:v for k,v in exp.maxima.items() if k in LIMITS and v >= LIMITS[k]}
        if not exp.finite or bad:
            raise RuntimeError(f"Physical bound exceeded: {bad}")
        if exp.maxima["point_displacement_per_step_m"] >= LIMITS["max_point_displacement_per_step_m"]:
            raise RuntimeError("Per-step displacement bound exceeded")
        if changes and max(changes.values()) > spec["protected_shape_tolerance_m"]:
            raise RuntimeError(f"Prepared wire disturbed: {changes}")

    def phase(name, seconds, **kwargs):
        exp.phase(name, seconds, **kwargs)
        check_physics()

    try:
        phase("initial_hold", .2)
        for i in args.order:
            before = shape_in_root_frame(exp.state()["fibers_m"])
            phase(f"wire_{i}_park", .4, offset=[-.020, *exp.offset[1:]], target=i)
            direction = before[i,-1]-before[i,0]
            roll = -np.arctan2(direction[2], direction[1])
            # Use the nearest equivalent turn, keeping the exposed bend plane
            # parallel to the applied contact force instead of amplifying curl.
            roll += 2*np.pi*round((exp.roll-roll)/(2*np.pi))
            phase(f"wire_{i}_select", .45, offset=[-.020, -.060, 0.], roll_deg=np.degrees(roll), target=i)
            tip = exp.state()["fibers_m"][i,-1]
            x = exp.offset[0]+exp.ring_center[0]-tip[0]
            z = exp.offset[2]+exp.ring_center[2]-tip[2]
            phase(f"wire_{i}_approach", .45, offset=[x, -.060, z], target=i)
            phase(f"wire_{i}_press", 1.0, offset=[x, -args.press_radius, z], target=i,
                  track_tip=True, track_tip_z=True)
            phase(f"wire_{i}_settle", .3, target=i)
            phase(f"wire_{i}_release", .45, offset=[exp.offset[0], -.060, exp.offset[2]], target=i)
            phase(f"wire_{i}_inspect", .3, target=i)
            local, radii, forward = local_metrics(exp.state()["fibers_m"], exp.layout)
            ready = bool(radii[i] < exp.layout.minimum_aperture_radius-spec["preparation_margin_m"] and forward[i])
            events.append(dict(target=i, prepared=ready, envelope_radius_m=float(radii[i]),
                other_shape_changes_m=np.linalg.norm(local-before, axis=-1).max(axis=1).tolist(),
                protected_shape_changes_m=dict(changes), simulation_time=exp.step*exp.dt))
            (args.output/"preparation_events.json").write_text(json.dumps(events, indent=2)+"\n")
            print("PREPARATION "+json.dumps(events[-1]), flush=True)
            if not ready:
                raise RuntimeError(f"Wire {i} remains outside the prepared envelope ({radii[i]*1000:.2f} mm)")
            protected[i] = local[i].copy()
            changes[i] = 0.
        phase("bundle_retreat", .45, offset=[-.020, *exp.offset[1:]])
        phase("bundle_unroll", .8, roll_deg=0.)
        roots = exp.state()["roots_m"].mean(axis=0)
        lateral = exp.offset[1:]+exp.ring_center[1:]-roots[1:]
        phase("bundle_align", .7, offset=[-.020, *lateral])
        phase("before_push", .3)
        prepared_metrics = [strand_metrics(exp.state()["fibers_m"], exp.ring_center, exp.layout, i)
                            for i in range(exp.layout.fiber_count)]
        if not all(m["fits_aperture_projection"] for m in prepared_metrics):
            raise RuntimeError("The prepared bundle does not fit the aperture in the final world pose")
        pushing = True
        phase("whole_bundle_push", 4., offset=[.370, *lateral])
        phase("final_hold", .7)
    except RuntimeError as error:
        failure = str(error)
        exp.save()
        print("ATTEMPT STOPPED: "+failure, flush=True)
    final = exp.state()["fibers_m"]
    exit_plane = exp.ring_center[0]+exp.layout.ring_tube_radius_m
    whole_fibers = final[:, :, 0].min(axis=1)-exp.layout.fiber_radius_m > exit_plane
    trunk_links = [exp.cable.get_link(f"trunk_{i:02d}").idx_local for i in range(exp.layout.trunk_segments)]
    # The cylinder/sphere trunk geometry lies within a radius-r tube of its axis.
    trunk_positions = as_numpy(exp.cable.get_links_pos())[trunk_links]
    trunk_beyond = bool(trunk_positions[:,0].min()-exp.layout.trunk_radius_m > exit_plane)
    checks = dict(all_eight_prepared=len(protected) == exp.layout.fiber_count,
        prepared_wires_preserved=max(changes.values(), default=0.) <= spec["protected_shape_tolerance_m"],
        all_fibers_crossed_inside_aperture=bool(passage_seen.all() and not passage_outside.any()),
        all_fibers_fully_beyond_ring=bool(whole_fibers.all()), trunk_fully_beyond_ring=trunk_beyond,
        finite_state=exp.finite, no_abort=failure is None)
    report = dict(scope="sequential_full_bundle_by_trunk_fixture", passed=all(checks.values()), checks=checks,
        layout=asdict(exp.layout), dt=exp.dt, substeps=exp.substeps, backend=args.backend,
        simulated_seconds=exp.step*exp.dt, ring_center_m=exp.ring_center.tolist(),
        initial=strand_metrics(initial, exp.ring_center, exp.layout),
        final=strand_metrics(final, exp.ring_center, exp.layout),
        prepared_wires=list(protected), protected_shape_changes_m=changes, preparation_events=events,
        fibers_fully_beyond_ring=whole_fibers.tolist(), passage_seen=passage_seen.tolist(),
        passage_outside=passage_outside.tolist(), maxima=exp.maxima, failure=failure,
        full_bundle_threading_verified=all(checks.values()), robot_grasp_executed=False,
        ring_pose_writes=0, fiber_pose_writes=0, fiber_force_commands=0,
        controlled_body="trunk_00 explicit position/orientation fixture; tip tracking reads only",
        ring_stand_collision_enabled=True, stability_gate=str(args.stability), plan=spec)
    (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stability", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--press-radius", type=float, default=.0353)
    parser.add_argument("--order", type=int, nargs="+", default=list(range(8)))
    parser.add_argument("--legacy-free", action="store_true", help="Historical detached-cable fixture; not valid for the anchored task")
    args=parser.parse_args()
    if not args.legacy_free:
        parser.error("The current task uses a fixed terminal. This historical free-cable fixture requires --legacy-free and cannot validate anchored_terminal_v2.")
    execute(args)
