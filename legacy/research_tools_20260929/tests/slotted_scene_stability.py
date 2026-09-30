"""Every-Env-tick audit of unassisted Slotted Post Ring home holds.

Native IPC validity is not an independent collision/CCD certificate. Samples
cover physical ticks (four native substeps each), not every native substep.
"""
import json
import numpy as np
from scipy.spatial.transform import Rotation

from runtime_evidence import arrays


LIMITS = dict(fem_max_speed_m_s=.005, fem_rms_speed_m_s=.001,
              rigid_speed_m_s=.002, rigid_angular_speed_rad_s=.03,
              settling_drift_m=.002, attachment_residual_m=.0005,
              minimum_volume_ratio=.2, rigid_penetration_m=.001,
              table_clearance_m=-.0001)


def integrity_passed(row):
    return (all(row[key] for key in ('finite', 'native_valid', 'native_frame_matches',
            'attachment_names_valid', 'all_task_vertices_over_table'))
        and not row['assist_active']
        and all(row[key] <= LIMITS[key] for key in ('attachment_residual_m', 'rigid_penetration_m'))
        and all(row[key] >= LIMITS[key] for key in ('minimum_volume_ratio', 'table_clearance_m')))


class SlottedStabilityAudit:
    def __init__(self, env, folder, seconds, window_s=2.):
        self.env, self.folder = env, folder
        self.seconds, self.window_s = seconds, window_s
        self.samples = []
        self.window_origin = None
        self.rows = (folder / 'stability_ticks.jsonl').open('x')

    def sample(self, record):
        world = record['world']
        time = float(world['sim_time_s'])
        cord = world['fem']['cord']
        ipc = world['ipc']
        velocity = np.linalg.norm(cord['velocity_m_s'], axis=1)
        names = ('target_ring', 'bead_left', 'bead_right', 'disc_left', 'disc_right')
        points = {'cord': cord['position_m']}
        for name in names:
            body = world['bodies'][name]
            rotation = Rotation.from_quat(np.roll(body['quaternion_wxyz'], -1)).as_matrix()
            points[name] = self.env._task.placement_vertices[name] @ rotation.T + body['position_m']
        xyz = np.concatenate(list(points.values()))
        table = self.env._world.tabletop
        low, high = table.robot_footprint.table_min_xy, table.robot_footprint.table_max_xy
        inside = ((xyz[:, :2] >= low) & (xyz[:, :2] <= high)).all(axis=1)
        late = time >= self.seconds - self.window_s - 1e-9
        if late and self.window_origin is None:
            self.window_origin = {key: value.copy() for key, value in points.items()}
        drift = max(float(np.linalg.norm(value-self.window_origin[key], axis=1).max())
                    for key, value in points.items()) if late else 0.
        row = dict(time_s=time, physics_step=world['physics_step'],
            finite=all(np.isfinite(value).all() for _, value in arrays(world)),
            native_valid=ipc['native_valid'], assist_active=world['assist_active'],
            native_frame_matches=ipc['native_frame'] == world['physics_step'] * self.env.config.solver_substeps,
            attachment_names_valid=set(ipc['attachment_residual_m']) == {'cord_disc_left', 'cord_disc_right'},
            attachment_residual_m=max(ipc['attachment_residual_m'].values()),
            minimum_volume_ratio=ipc['volume_ratio']['cord']['minimum'],
            rigid_penetration_m=float(np.max(world['contacts']['penetration'], initial=0)),
            all_task_vertices_over_table=bool(inside.all()),
            table_clearance_m=float(xyz[:, 2].min()-table.frames.table_surface_origin[2]),
            fem_max_speed_m_s=float(velocity.max()),
            fem_rms_speed_m_s=float(np.sqrt(np.mean(velocity**2))),
            rigid_speed_m_s=max(float(np.linalg.norm(world['bodies'][n]['linear_velocity_m_s'])) for n in names),
            rigid_angular_speed_rad_s=max(float(np.linalg.norm(world['bodies'][n]['angular_velocity_rad_s'])) for n in names),
            settling_window=late, settling_drift_m=drift)
        self.samples.append(row)
        self.rows.write(json.dumps(row)+'\n')
        self.rows.flush()
        self.final_points = {key: value.copy() for key, value in points.items()}
        assert integrity_passed(row), row

    def finish(self):
        self.rows.close()
        late = [r for r in self.samples if r['settling_window']]
        completed = bool(self.samples and self.samples[-1]['time_s'] >= self.seconds-1e-9)
        complete_window = bool(late and late[-1]['time_s']-late[0]['time_s'] >= self.window_s-1e-8)
        keys = ('fem_max_speed_m_s', 'fem_rms_speed_m_s', 'rigid_speed_m_s',
                'rigid_angular_speed_rad_s', 'settling_drift_m')
        peaks = {key: max(r[key] for r in late) for key in keys} if late else {}
        checks = {key: value <= LIMITS[key] for key, value in peaks.items()}
        checks.update(duration_complete=completed, settling_window_complete=complete_window)
        checks['integrity_all_ticks'] = bool(self.samples and all(integrity_passed(row) for row in self.samples))
        checks['tick_coverage_complete'] = bool(self.samples and
            [r['physics_step'] for r in self.samples] == list(range(round(self.seconds/self.env.config.physics_dt_s)+1)))
        checks['time_matches_ticks'] = bool(self.samples and all(abs(row['time_s']-
            row['physics_step']*self.env.config.physics_dt_s) < 1e-9 for row in self.samples))
        if self.samples:
            np.savez_compressed(self.folder/'stability_final_points.npz', **self.final_points)
        return dict(passed=all(checks.values()), checks=checks, limits=LIMITS,
                    duration_s=self.seconds, settling_window_s=self.window_s,
                    observed_ticks=len(self.samples), settling_maxima=peaks,
                    maximum_attachment_residual_m=max((r['attachment_residual_m'] for r in self.samples), default=None),
                    minimum_volume_ratio=min((r['minimum_volume_ratio'] for r in self.samples), default=None),
                    minimum_table_clearance_m=min((r['table_clearance_m'] for r in self.samples), default=None),
                    scope='unassisted initial scene, every Env tick; not solution, grasp, material calibration or independent IPC CCD qualification')
