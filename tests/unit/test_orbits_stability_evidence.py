"""Negative controls for passive-scene acceptance; these are not physics tests."""

import numpy as np
import pytest

from orbits_stability_evidence import measure, summarize
from topogym.assets.geometry.orbits import OrbitsLayout, cord_centerline


def fixture():
    layout = OrbitsLayout(ring_count=2)
    points = cord_centerline(layout)
    origin = np.array([0., 0., .75])
    world = dict(fem={'cord': dict(position_m=points+origin, velocity_m_s=np.zeros_like(points))},
                 bodies={'handle': dict(position_m=origin.copy(), quaternion_wxyz=[1., 0., 0., 0.],
                                         linear_velocity_m_s=np.zeros(3), angular_velocity_rad_s=np.zeros(3)),
                         'base': dict(position_m=origin.copy())},
                 ipc=dict(native_valid=True, volume_ratio={'cord': dict(minimum=1., maximum=1.)},
                          attachment_residual_m={'cord_handle_start': 0., 'cord_handle_end': 0.}))
    context = dict(layout=layout, origin=origin, yaw_deg=0.,
                   surface_rings=np.arange(len(points))[:, None],
                   initial_lengths=np.linalg.norm(np.diff(points, axis=0), axis=1),
                   handle_vertices=np.array([[layout.handle_x_m, 0., layout.clearance_m]]),
                   fixed_positions={'base': origin.copy()})
    return world, context


def test_quiet_is_not_enough_if_endpoints_or_elements_fail():
    state, context = fixture()
    assert measure(state, **context)['integrity_passed']
    state['ipc']['attachment_residual_m']['cord_handle_end'] = .01
    result = measure(state, **context)
    assert result['quiet'] and not result['integrity_passed']
    assert not result['checks']['attachments']
    state, context = fixture()
    state['ipc']['volume_ratio']['cord']['minimum'] = -.1
    assert not measure(state, **context)['checks']['volume']


def test_nonfinite_or_missing_evidence_cannot_pass():
    state, context = fixture()
    state['fem']['cord']['velocity_m_s'][0, 0] = np.nan
    assert not measure(state, **context)['integrity_passed']
    state, context = fixture()
    del state['ipc']['attachment_residual_m']['cord_handle_end']
    with pytest.raises(KeyError):
        measure(state, **context)


def test_lost_encirclement_and_table_penetration_fail():
    state, context = fixture()
    state['fem']['cord']['position_m'][:, 0] += 1.
    assert not measure(state, **context)['checks']['trapped_initial_state']
    state, context = fixture()
    state['fem']['cord']['position_m'][:, 2] -= .1
    assert not measure(state, **context)['checks']['tabletop']


def test_stability_requires_the_whole_final_window_and_completed_run():
    state, context = fixture()
    measurement = measure(state, **context)
    rows = [dict(measurement, sim_time_s=t) for t in np.arange(0., 4.01, .1)]
    assert summarize(rows, 4., 1., dt_s=.1)['passed']
    assert not summarize(rows[:-1], 4., 1., dt_s=.1)['passed']
    assert not summarize(rows[::2], 4., 1., dt_s=.1)['passed']
    rows[-2] = dict(rows[-2], quiet=False)
    assert not summarize(rows, 4., 1., dt_s=.1)['passed']
    rows[-2] = dict(rows[-2], quiet=True)
    rows[1] = dict(rows[1], integrity_passed=False)
    assert not summarize(rows, 4., 1., dt_s=.1)['passed']
