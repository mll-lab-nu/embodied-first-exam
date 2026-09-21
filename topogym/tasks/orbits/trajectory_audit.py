"""Audit recorded native states; finite sampling is not continuous certification."""
import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from omegaconf import OmegaConf

from .verification import threading_signature
from .workspace import WorkspaceAudit


def audit(folder):
    folder = Path(folder)
    checker = WorkspaceAudit(OmegaConf.load(folder/'config.yaml'))
    checker.fixture = [part for part in checker.fixture if part[0] not in ('cord', 'handle')]
    model = mujoco.MjModel.from_xml_path(str(folder/'model.xml'))
    data = mujoco.MjData(model)
    node_ids = [model.site(f'node_{i}').id for i in range(model.nflexvert)]
    terminal_ids = [model.equality(name).id for name in ('terminal_0', 'terminal_1')]
    max_terminal_error = 0.
    max_recording_error = 0.
    max_linking = 0
    violations = []
    with np.load(folder/'trajectory.npz') as saved:
        times, qs, points = saved['time_s'], saved['qpos'], saved['points']
        if not (np.isfinite(qs).all() and np.isfinite(points).all() and
                np.isfinite(times).all() and np.all(np.diff(times) > 0)):
            raise ValueError('Invalid recorded states or non-monotone timestamps')
        for index, (t, q, recorded) in enumerate(zip(times, qs, points)):
            bad = checker.violations(q[:16])
            if bad:
                violations.append(dict(frame=index, time_s=float(t), violations=bad))
            data.qpos[:] = q
            mujoco.mj_kinematics(model, data)
            measured = data.site_xpos[node_ids]
            max_recording_error = max(max_recording_error, float(np.max(np.abs(measured-recorded))))
            for eid in terminal_ids:
                max_terminal_error = max(max_terminal_error, float(np.linalg.norm(
                    data.site_xpos[model.eq_obj1id[eid]]-data.site_xpos[model.eq_obj2id[eid]])))
            signature = threading_signature(measured, checker.layout)
            max_linking = max(max_linking, max(abs(n) for n in signature['ring_linking_numbers']))
        result = dict(scope='all_recorded_native_frames', full_task_success=False,
                      continuous_collision_proof=False, frames=len(times),
                      start_time_s=float(times[0]), final_time_s=float(times[-1]),
                      maximum_frame_interval_s=float(np.max(np.diff(times))),
                      robot_fixture_or_self_violations=violations,
                      maximum_terminal_attachment_error_m=max_terminal_error,
                      maximum_recorded_point_error_m=max_recording_error,
                      maximum_absolute_ring_linking_number=max_linking,
                      final_threading=signature,
                      trajectory_sha256=hashlib.sha256((folder/'trajectory.npz').read_bytes()).hexdigest(),
                      limitations=['Checks sampled configurations and terminal attachment geometry.',
                                   'Ring linking invariance does not certify untangling or exclude every crossing.',
                                   'Dynamics contact depths are reported separately by the native runtime.'])
    (folder/'trajectory_audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('final_threading', 'limitations', 'robot_fixture_or_self_violations')}
                     | {'violation_frames':len(violations)}, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    audit(parser.parse_args().folder)
