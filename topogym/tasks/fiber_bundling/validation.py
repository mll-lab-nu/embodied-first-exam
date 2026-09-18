"""Numerical stability checks for the finite-radius passive cable model.

This qualifies a declared discretization and motion range, not copper material
accuracy or all possible loads. Thresholds are recorded before simulation.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np

from .geometry import FiberLayout, generate_assets, shape_in_root_frame, write_bundle
from .scene import as_numpy, cable_state
from .single_strand import default_plan, strand_metrics


LIMITS = dict(root_error_m=1e-5, segment_length_error_m=1e-5,
              contact_penetration_m=.0003, strand_penetration_m=.0003,
              max_point_displacement_per_step_m=.0012, free_drift_m=.0001,
              final_hold_shape_drift_m=.0001, final_hold_speed_m_s=.0001,
              timestep_max_shape_difference_m=.002, timestep_rms_shape_difference_m=.0005)


def pair_clearances(paths, radius):
    """Vectorized exact segment distances between different finite-radius wires.

    The first collision capsule is inset 2.5 radii from its attachment, matching
    write_bundle; visual roots themselves must not be mistaken for collisions.
    """
    paths = np.asarray(paths)
    a, b = paths[:, :-1].copy(), paths[:, 1:].copy()
    a[:, 0] += 2.5*radius*(b[:, 0]-a[:, 0])/np.linalg.norm(b[:, 0]-a[:, 0], axis=-1)[:, None]
    strands, segments = a.shape[:2]
    i, j = np.triu_indices(strands, 1)
    aa, bb = a[i, :, None], b[i, :, None]
    cc, dd = a[j, None, :], b[j, None, :]
    u, v, w = bb-aa, dd-cc, aa-cc
    dot = lambda x, y: np.sum(x*y, axis=-1)
    uu, uv, vv, uw, vw = dot(u, u), dot(u, v), dot(v, v), dot(u, w), dot(v, w)
    denom = uu*vv-uv*uv
    candidates = [(np.zeros_like(uv), np.clip(vw/vv, 0, 1)),
                  (np.ones_like(uv), np.clip((vw+uv)/vv, 0, 1)),
                  (np.clip(-uw/uu, 0, 1), np.zeros_like(uv)),
                  (np.clip((uv-uw)/uu, 0, 1), np.ones_like(uv))]
    safe = np.where(denom > 1e-18, denom, 1.)
    s, t = (uv*vw-vv*uw)/safe, (uu*vw-uv*uw)/safe
    interior = (denom > 1e-18) & (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
    distances = [np.linalg.norm(w+s[..., None]*u-t[..., None]*v, axis=-1) for s, t in candidates]
    distances.append(np.where(interior, np.linalg.norm(w+s[..., None]*u-t[..., None]*v, axis=-1), np.inf))
    clearance = np.minimum.reduce(distances).reshape(len(i), segments*segments).min(axis=1)-2*radius
    result = np.full((strands, strands), np.inf)
    result[i, j] = result[j, i] = clearance
    return result


class FixtureExperiment:
    """Reusable real simulation, with only the thick root exposed to commands."""
    def __init__(self, output, *, dt=.002, substeps=4, backend="cuda", free=False, iterations=100, stand=False):
        import genesis as gs
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.layout, _ = generate_assets(self.output/"assets")
        path = (self.output/"assets/bundle_fixture.xml").resolve()
        write_bundle(path, self.layout, self.layout.fibers(), fixture=not free)
        gs.init(backend=gs.cuda if backend == "cuda" else gs.cpu, logging_level="warning", seed=self.layout.seed)
        self.scene = gs.Scene(show_viewer=False,
            sim_options=gs.options.SimOptions(dt=dt, substeps=substeps, gravity=(0, 0, -9.81)),
            rigid_options=gs.options.RigidOptions(enable_collision=True, enable_self_collision=True,
                iterations=iterations, max_collision_pairs=4096, constraint_timeconst=.002))
        self.origin = np.array([0., 0., .5])
        self.ring_center = self.origin+[self.layout.trunk_length_m+.1, 0., 0.]
        self.cable = self.scene.add_entity(gs.morphs.MJCF(file=str(path), pos=self.origin, decimate=False),
            material=gs.materials.Rigid(friction=.35, gravity_compensation=1.))
        self.ring = self.scene.add_entity(gs.morphs.URDF(file=str((self.output/"assets/ring.urdf").resolve()),
            pos=self.ring_center, euler=(0, 90, 0), fixed=True, merge_fixed_links=False, decimate=False),
            material=gs.materials.Rigid(friction=.35))
        if stand:
            bottom = self.ring_center[2]-(self.layout.ring.radius_m+self.layout.ring.tube_radius_m)
            self.scene.add_entity(gs.morphs.Box(pos=(self.ring_center[0], 0., (.26+bottom)/2),
                size=(.012, .016, bottom-.26), fixed=True), material=gs.materials.Rigid(friction=.35))
        print(f"Building {backend} dt={dt} substeps={substeps} free={free}", flush=True)
        self.scene.build()
        self.dt, self.substeps, self.backend = dt, substeps, backend
        self.free, self.iterations = free, iterations
        self.step = 0
        self.offset, self.yaw = np.zeros(3), 0.
        self.roll = 0.
        self.records, self.history = [], []
        self.maxima = dict(root_error_m=0., segment_length_error_m=0., contact_penetration_m=0.,
                           strand_penetration_m=0., point_displacement_per_step_m=0., link_speed_m_s=0.)
        self.finite = True
        self.observer = None
        self.previous = self.state()["fibers_m"].copy()
        self.first = self.previous.copy()
        self.record("initial")

    def state(self):
        return cable_state(self.cable, self.layout)

    def record(self, phase, target=-1):
        state = self.state()
        self.records.append(dict(fibers=state["fibers_m"], qpos=as_numpy(self.cable.get_qpos()).copy(),
            velocities=as_numpy(self.cable.get_dofs_velocity()).copy(),
            root_positions=as_numpy(self.cable.get_pos()).copy(),
            root_quaternions=as_numpy(self.cable.get_quat()).copy(), times=self.step*self.dt,
            phases=phase, targets=target))
        return state

    def monitor(self):
        state = self.state()
        p = state["fibers_m"]
        vel = as_numpy(self.cable.get_links_vel())
        self.finite &= bool(np.isfinite(p).all() and np.isfinite(vel).all())
        values = dict(root_error_m=state["max_root_error_m"],
            segment_length_error_m=float(np.abs(np.linalg.norm(np.diff(p, axis=1), axis=-1)-
                                               self.layout.fiber_length_m/self.layout.fiber_segments).max()),
            strand_penetration_m=max(0., float(-pair_clearances(p, self.layout.fiber_radius_m).min())),
            point_displacement_per_step_m=float(np.linalg.norm(p-self.previous, axis=-1).max()),
            link_speed_m_s=float(np.linalg.norm(vel, axis=-1).max()))
        penetration = as_numpy(self.scene.sim.rigid_solver.collider.get_contacts()["penetration"])
        values["contact_penetration_m"] = float(penetration.max()) if penetration.size else 0.
        for name, value in values.items():
            self.maxima[name] = max(self.maxima[name], value)
        self.previous = p.copy()
        if self.observer is not None:
            self.observer(p)
        return values

    def phase(self, name, seconds, offset=None, yaw_deg=None, target=-1, track_tip=False, roll_deg=None,
              track_tip_z=False):
        start, end = self.offset.copy(), np.asarray(self.offset if offset is None else offset)
        yaw_start, yaw_end = self.yaw, self.yaw if yaw_deg is None else np.radians(yaw_deg)
        roll_start, roll_end = self.roll, self.roll if roll_deg is None else np.radians(roll_deg)
        count = round(seconds/self.dt)
        stamp = time.monotonic()
        for k in range(count):
            blend = .5-.5*np.cos(np.pi*(k+1)/count)
            old_offset = self.offset.copy()
            old_x = old_offset[0]
            self.offset = start+(end-start)*blend
            if track_tip:
                # Feedback commands the trunk only, keeping the chosen free tip
                # near the ring plane while the outer rim presses it inward.
                tip = self.state()["fibers_m"][target, -1]
                goal_x = old_x+self.ring_center[0]-tip[0]
                self.offset[0] = old_x+np.clip(goal_x-old_x, -.05*self.dt, .05*self.dt)
                if track_tip_z:
                    self.offset[2] = old_offset[2]+np.clip(self.ring_center[2]-tip[2],
                                                          -.05*self.dt, .05*self.dt)
            self.yaw = yaw_start+(yaw_end-yaw_start)*blend
            self.roll = roll_start+(roll_end-roll_start)*blend
            if not self.free and (offset is not None or yaw_deg is not None or roll_deg is not None):
                self.cable.set_pos(self.origin+self.offset, zero_velocity=False)
                cy, sy, cr, sr = np.cos(self.yaw/2), np.sin(self.yaw/2), np.cos(self.roll/2), np.sin(self.roll/2)
                self.cable.set_quat([cy*cr, cy*sr, sy*sr, sy*cr], zero_velocity=False)
            self.scene.step()
            self.step += 1
            self.monitor()
            if self.step % max(1, round(.02/self.dt)) == 0:
                self.record(name, target)
        state = self.record(name, target)
        metrics = [strand_metrics(state["fibers_m"], self.ring_center, self.layout, i)
                   for i in range(self.layout.fiber_count)]
        self.history.append(dict(phase=name, time=self.step*self.dt, metrics=metrics))
        self.save()
        print(json.dumps(dict(phase=name, time=self.step*self.dt, wall_seconds=time.monotonic()-stamp,
            tip_angles=[round(m["tip_angle_deg"], 2) for m in metrics],
            fits=[m["fits_aperture_projection"] for m in metrics], maxima=self.maxima)), flush=True)
        return state

    def save(self):
        np.savez_compressed(self.output/"trajectory.npz", **{
            key: np.asarray([r[key] for r in self.records]) for key in self.records[0]})
        (self.output/"phase_metrics.json").write_text(json.dumps(self.history, indent=2)+"\n")


def run_validation(args):
    spec = dict(scope="numerical_stability_of_declared_discrete_model", thresholds=LIMITS,
                dt=args.dt, substeps=args.substeps, iterations=args.iterations, free=args.free,
                initial_hold_seconds=10. if args.free else .2,
                final_hold_seconds=0. if args.free else 5.)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"validation_spec.json").write_text(json.dumps(spec, indent=2)+"\n")
    exp = FixtureExperiment(args.output, dt=args.dt, substeps=args.substeps, backend=args.backend,
                            free=args.free, iterations=args.iterations)
    if args.free:
        exp.phase("free_hold", 10.)
    else:
        for p in default_plan(exp.layout):
            exp.phase(**{k: v for k, v in p.items() if k in ("name", "seconds", "offset", "yaw_deg")})
        exp.phase("long_hold", 5.)
    final = exp.state()["fibers_m"]
    last_second = [r for r in exp.records if r["times"] >= exp.step*exp.dt-1.]
    reference = shape_in_root_frame(last_second[0]["fibers"])
    drift = max(float(np.linalg.norm(shape_in_root_frame(r["fibers"])-reference, axis=-1).max())
                for r in last_second)
    speed = float(np.linalg.norm(as_numpy(exp.cable.get_links_vel()), axis=-1).max())
    free_drift = float(np.linalg.norm(final-exp.first, axis=-1).max()) if args.free else None
    checks = dict(finite=exp.finite,
        root_constraints=exp.maxima["root_error_m"] < LIMITS["root_error_m"],
        segment_lengths=exp.maxima["segment_length_error_m"] < LIMITS["segment_length_error_m"],
        bounded_contact_penetration=exp.maxima["contact_penetration_m"] < LIMITS["contact_penetration_m"],
        independent_strand_clearance=exp.maxima["strand_penetration_m"] < LIMITS["strand_penetration_m"],
        bounded_motion_per_step=exp.maxima["point_displacement_per_step_m"] < LIMITS["max_point_displacement_per_step_m"],
        settled_shape=drift < LIMITS["final_hold_shape_drift_m"],
        settled_velocity=speed < LIMITS["final_hold_speed_m_s"])
    if args.free:
        checks["gravity_neutral_free_hold"] = free_drift < LIMITS["free_drift_m"]
    report = dict(**spec, layout=asdict(exp.layout), backend=args.backend, checks=checks,
        passed=all(checks.values()), maxima=exp.maxima, final_hold_shape_drift_m=drift,
        final_hold_speed_m_s=speed, free_hold_displacement_m=free_drift,
        simulated_seconds=exp.step*exp.dt, final_metrics=exp.history[-1]["metrics"],
        ring_center_m=exp.ring_center.tolist(), fiber_pose_writes=0, fiber_force_commands=0,
        ring_pose_writes=0, robot_grasp_executed=False,
        note="Kinematic trunk fixture for loading; free base for free_hold. No calibrated copper constitutive model.")
    (args.output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dt", type=float, default=.002)
    parser.add_argument("--substeps", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--free", action="store_true")
    run_validation(parser.parse_args())
