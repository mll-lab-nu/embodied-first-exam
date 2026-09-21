"""Record and audit continuous gravity settling of the physical reconstruction."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import mujoco
import numpy as np

from .physics import PhysicsSettings, build_model, contact_summary, node_positions
from .geometry import SlottedPostLayout


def settle(output, settings=PhysicsSettings(), seconds=12., robot=False, layout=SlottedPostLayout()):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model, data, spec = build_model(output/'model', settings, layout=layout, robot=robot)
    frames, velocities, timestamps, nodes = [], [], [], []
    depths, warnings = {}, {}
    max_endpoint_error = 0.
    max_length_error = 0.
    tail = []
    rigid_names = ['target_ring', 'disc_left', 'disc_right', 'bead_left', 'bead_right']
    rigid_ids = [model.body(n).id for n in rigid_names]
    previous = node_positions(model, data)
    starts = previous.copy()
    stride = max(1, round(.05/settings.dt))
    steps = round(seconds/settings.dt)
    clock = time.monotonic()
    for step in range(steps+1):
        mujoco.mj_forward(model, data)
        actual = node_positions(model, data)
        for key, value in contact_summary(model, data).items():
            depths[key] = max(depths.get(key, 0), value)
        for side, node in (('left', 0), ('right', -1)):
            err = np.linalg.norm(data.site_xpos[model.site(f'disc_{side}_anchor').id]-actual[node])
            max_endpoint_error = max(max_endpoint_error, float(err))
        max_length_error = max(max_length_error, float(np.max(np.abs(
            np.linalg.norm(np.diff(actual, axis=0), axis=1)-spec['cord_segment_lengths']))))
        if step and data.time >= seconds-2:
            rigid_v = []
            for body in rigid_ids:
                v = np.zeros(6)
                mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, v, 0)
                rigid_v.append([np.linalg.norm(v[3:]), np.linalg.norm(v[:3])])
            tail.append([np.max(np.linalg.norm(actual-previous, axis=1))/settings.dt, *np.asarray(rigid_v).ravel()])
        previous = actual.copy()
        if step % stride == 0:
            frames.append(data.qpos.copy()); velocities.append(data.qvel.copy())
            timestamps.append(data.time); nodes.append(actual)
        if step % max(1, round(1/settings.dt)) == 0:
            print(f'settle {data.time:.3f}/{seconds}s wall={time.monotonic()-clock:.1f}s depths={depths}', flush=True)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            break
        if step < steps:
            mujoco.mj_step(model, data)
    for i, warning in enumerate(data.warning):
        if warning.number:
            warnings[mujoco.mjtWarning(i).name] = int(warning.number)
    tail = np.asarray(tail)
    maximum_tail = tail.max(axis=0) if len(tail) else np.full(11, np.inf)
    tail_nodes = np.asarray(nodes)[np.asarray(timestamps) >= seconds-2-1e-8]
    tail_drift = float(np.max(np.linalg.norm(tail_nodes-tail_nodes[0], axis=2))) if len(tail_nodes) else float('inf')
    checks = dict(completed=bool(data.time >= seconds-settings.dt/2),
                  finite=bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()),
                  no_warnings=not warnings, contact_depth=all(v < .0005 for v in depths.values()),
                  endpoint_attachment=max_endpoint_error < .0005,
                  limited_extension=max_length_error < .005*min(spec['cord_segment_lengths']),
                  settled_speed=bool(maximum_tail[0] < .003 and max(maximum_tail[1::2]) < .002
                                     and max(maximum_tail[2::2]) < .03),
                  settled_drift=tail_drift < .002,
                  cord_above_table=bool(actual[:, 2].min() >= spec['layout']['rope_radius_m']-.0005))
    report = dict(scope='gravity_settling_only', passed=all(checks.values()), checks=checks,
                  engine='MuJoCo', engine_version=mujoco.__version__, settings=asdict(settings),
                  layout=asdict(layout),
                  simulated_seconds=float(data.time), pose_writes_after_initialization=False,
                  robot_present=robot, full_robot_demo=False, fps=20,
                  max_contact_depth_m=depths, max_endpoint_error_m=max_endpoint_error,
                  max_segment_length_error_m=max_length_error,
                  maximum_last_two_seconds_speeds=maximum_tail.tolist(),
                  maximum_last_two_seconds_node_drift_m=tail_drift, warnings=warnings,
                  initial_nodes=starts.tolist(), final_nodes=actual.tolist(),
                  final_rigid_positions={n:data.xpos[i].tolist() for n,i in zip(rigid_names, rigid_ids)},
                  wall_seconds=time.monotonic()-clock)
    np.savez_compressed(output/'states.npz', qpos=frames, qvel=velocities, time_s=timestamps, cord_nodes=nodes)
    np.savez_compressed(output/'final_state.npz', qpos=data.qpos, qvel=data.qvel, time_s=data.time)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('initial_nodes','final_nodes')}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dt', type=float, default=.000125)
    parser.add_argument('--segment', type=float, default=.008)
    parser.add_argument('--seconds', type=float, default=12)
    parser.add_argument('--robot', action='store_true')
    parser.add_argument('--slot-width',type=float,default=.028,help='Authored candidate aperture, recorded separately in the model specification')
    args = parser.parse_args()
    report = settle(args.output, PhysicsSettings(dt=args.dt, segment_m=args.segment), args.seconds, args.robot,
                    SlottedPostLayout(slot_width_m=args.slot_width))
    if not report['passed']:
        raise SystemExit(1)
