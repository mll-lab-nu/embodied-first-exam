"""Passive Orbits measurements, independent of task success and rendering."""

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.orbits import winding_numbers
from topogym.evaluation.task_metrics import body_points


LIMITS = dict(soft_speed_m_s=.001, handle_speed_m_s=.001,
              handle_angular_speed_rad_s=.02, attachment_residual_m=.001,
              table_penetration_m=.0001, fixed_drift_m=.000001,
              volume_ratio_min=.5, volume_ratio_max=1.5,
              segment_length_ratio_min=.8, segment_length_ratio_max=1.2)


def measure(world, *, layout, origin, yaw_deg, surface_rings, initial_lengths,
            handle_vertices, fixed_positions):
    """Measure each committed physics tick; projection winding is diagnostic only."""
    cord = world['fem']['cord']
    positions, velocities = np.asarray(cord['position_m']), np.asarray(cord['velocity_m_s'])
    handle = world['bodies']['handle']
    ipc = world['ipc']
    volume = ipc['volume_ratio']['cord']
    residuals = [ipc['attachment_residual_m'][f'cord_handle_{end}'] for end in ('start', 'end')]
    arrays = [positions, velocities, *[handle[k] for k in
              ('position_m', 'quaternion_wxyz', 'linear_velocity_m_s', 'angular_velocity_rad_s')],
              *[world['bodies'][name]['position_m'] for name in fixed_positions],
              list(volume.values()), residuals]
    if not all(np.isfinite(value).all() for value in arrays):
        return dict(finite=False, integrity_passed=False, quiet=False)
    centers = positions[surface_rings].mean(axis=1)
    local = Rotation.from_euler('z', yaw_deg, degrees=True).inv().apply(centers-origin)
    windings = np.abs(winding_numbers(local, layout.post_x))
    handle_points = body_points(handle, handle_vertices)
    ratios = np.linalg.norm(np.diff(centers, axis=0), axis=1)/initial_lengths
    metrics = dict(
        finite=True, native_valid=bool(ipc['native_valid']),
        soft_speed_m_s=float(np.linalg.norm(velocities, axis=1).max()),
        handle_speed_m_s=float(np.linalg.norm(handle['linear_velocity_m_s'])),
        handle_angular_speed_rad_s=float(np.linalg.norm(handle['angular_velocity_rad_s'])),
        attachment_residual_m=float(max(residuals)),
        volume_ratio_min=float(volume['minimum']), volume_ratio_max=float(volume['maximum']),
        segment_length_ratio_min=float(ratios.min()), segment_length_ratio_max=float(ratios.max()),
        table_clearance_m=float(min(positions[:, 2].min(), handle_points[:, 2].min())-origin[2]),
        fixed_drift_m=max(float(np.linalg.norm(world['bodies'][name]['position_m']-point))
                          for name, point in fixed_positions.items()),
        winding_absolute=windings.tolist(),
        last_post_still_encircled=bool(np.allclose(windings, [0]*layout.ring_count+[1], atol=1e-5)),
        cord_below_lowest_ring=bool(local[:, 2].max()+layout.cord_radius_m <
                                    layout.ring_z[-1]-layout.ring_tube_radius_m),
        handle_position_m=np.asarray(handle['position_m']).tolist(),
    )
    checks = dict(
        native_valid=metrics['native_valid'],
        attachments=metrics['attachment_residual_m'] <= LIMITS['attachment_residual_m'],
        # An authored bent spawn is not stress-free. During initial relaxation
        # require finite positive volumes; apply the tighter envelope after settling.
        volume=0 < metrics['volume_ratio_min'] <= metrics['volume_ratio_max'],
        material_lengths=LIMITS['segment_length_ratio_min'] <= metrics['segment_length_ratio_min'] <=
                         metrics['segment_length_ratio_max'] <= LIMITS['segment_length_ratio_max'],
        tabletop=metrics['table_clearance_m'] >= -LIMITS['table_penetration_m'],
        fixed_fixture=metrics['fixed_drift_m'] <= LIMITS['fixed_drift_m'],
        trapped_initial_state=metrics['last_post_still_encircled'] and metrics['cord_below_lowest_ring'],
    )
    metrics.update(checks=checks, integrity_passed=all(checks.values()),
                   quiet=(all(metrics[key] <= LIMITS[key] for key in
                              ('soft_speed_m_s', 'handle_speed_m_s', 'handle_angular_speed_rad_s'))
                          and LIMITS['volume_ratio_min'] <= metrics['volume_ratio_min']
                          and metrics['volume_ratio_max'] <= LIMITS['volume_ratio_max']))
    return metrics


def summarize(rows, duration_s, window_s, *, dt_s):
    """Require a complete final interval, not a single quiet frame or a short run."""
    times = np.array([row['sim_time_s'] for row in rows])
    if not len(times) or duration_s <= window_s or window_s <= 0 or dt_s <= 0:
        raise ValueError('A positive hold window shorter than the run is required')
    tail = [row for row in rows if row['sim_time_s'] >= duration_s-window_s-1e-9]
    complete = bool(abs(times[0]) < 1e-9 and abs(times[-1]-duration_s) < 1e-8
                    and np.allclose(np.diff(times), dt_s, rtol=0, atol=1e-9)
                    and len(rows) == round(duration_s/dt_s)+1 and len(tail) > 1
                    and tail[0]['sim_time_s'] <= duration_s-window_s+1e-8)
    integrity = all(row['integrity_passed'] for row in rows)
    stable = complete and integrity and all(row['quiet'] for row in tail)
    finite_tail = [row for row in tail if row['finite']]
    return dict(
        passed=bool(stable), complete=complete, integrity_passed=integrity,
        settled=bool(complete and all(row['quiet'] for row in tail)),
        duration_s=duration_s, window_s=window_s, ticks=len(rows)-1,
        limits=LIMITS,
        tail_maxima={key: max(row[key] for row in finite_tail) for key in
                     ('soft_speed_m_s', 'handle_speed_m_s', 'handle_angular_speed_rad_s',
                      'attachment_residual_m')} if finite_tail else {},
        failed_checks=sorted({name for row in rows for name, ok in row.get('checks', {}).items() if not ok}
                             | ({'finite'} if not all(row['finite'] for row in rows) else set())),
        scope='Passive initial-scene stability only; no grasp, solution, difficulty or full contact qualification',
        full_ipc_contact_coverage=False, solution_verified=False, difficulty_qualified=False,
    )
