"""A quiet final frame cannot hide a short run or an earlier physical failure."""
from types import SimpleNamespace
import numpy as np
import pytest
from slotted_scene_stability import SlottedStabilityAudit


def audit(tmp_path):
    env = SimpleNamespace(config=SimpleNamespace(physics_dt_s=.5))
    obj = SlottedStabilityAudit(env, tmp_path, seconds=3., window_s=2.)
    obj.final_points = {'cord': np.zeros((2, 3))}
    for index in range(7):
        obj.samples.append(dict(time_s=index*.5, physics_step=index,
            finite=True, native_valid=True, native_frame_matches=True,
            attachment_names_valid=True, all_task_vertices_over_table=True, assist_active=False,
            attachment_residual_m=1e-7, rigid_penetration_m=0., minimum_volume_ratio=.9,
            table_clearance_m=0., fem_max_speed_m_s=0., fem_rms_speed_m_s=0.,
            rigid_speed_m_s=0., rigid_angular_speed_rad_s=0., settling_drift_m=0.,
            settling_window=index >= 2))
    return obj


def test_complete_quiet_window_passes(tmp_path):
    assert audit(tmp_path).finish()['passed']


@pytest.mark.parametrize('key,value,index', [
    ('fem_max_speed_m_s', .006, 3), ('fem_rms_speed_m_s', .002, 3),
    ('settling_drift_m', .003, 3), ('rigid_angular_speed_rad_s', .04, 3),
    ('attachment_residual_m', .002, 1), ('minimum_volume_ratio', .1, 1),
    ('table_clearance_m', -.001, 1), ('native_valid', False, 6),
    ('finite', False, 6), ('assist_active', True, 1)])
def test_brief_failure_cannot_be_hidden_by_quiet_final_frame(tmp_path, key, value, index):
    obj = audit(tmp_path)
    obj.samples[index][key] = value
    assert not obj.finish()['passed']


@pytest.mark.parametrize('index', [0, 2, 6])
def test_missing_ticks_or_incomplete_run_cannot_pass(tmp_path, index):
    obj = audit(tmp_path)
    obj.samples.pop(index)
    assert not obj.finish()['passed']
