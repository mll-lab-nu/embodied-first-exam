"""Panda/Robotiq, standard Nyx segments and existing public cube policy."""
import os
from pathlib import Path
import traceback
import pytest

from topogym.simulator import Env, SimulatorConfig, SegmentRunner
from topogym.utils.grasp import GraspAssistConfig, GraspTarget
from topogym.utils.io import to_jsonable, write_json_atomic
from fixtures.cube_transfer import register_cube_transfer
from fixtures.cube_policy import cube_policy

pytestmark = [pytest.mark.genesis, pytest.mark.render]


def test_panda_assist_across_recorded_segments():
    output = Path(os.environ['TOPOGYM_TEST_OUTPUT'])
    output.mkdir(parents=True, exist_ok=True)
    config = SimulatorConfig(task_id='cube_transfer', robot_id='panda_robotiq',
        control_mode='EE_ABS', observation_mode='EE', enable_privileged=True,
        # Same accepted control/solver timing as segments_20260925_acceptance_02:
        # 25 ms control ticks, 0.625 ms solver substeps; all ticks still recorded.
        physics_dt_s=.025, solver_substeps=40, control_decimation=1, max_physics_steps=1200,
        grasp_assist=GraspAssistConfig('contact_weld_v1',
            (GraspTarget('cube', 'box_baselink', radius_m=.04),), stable_time_s=.05))
    report = dict(status='running', scope='real Panda/Robotiq cube fixture; not any of the 13 puzzle solves',
                  config=to_jsonable(config), events=[])
    write_json_atomic(output/'report.json', report)
    try:
        with register_cube_transfer(), Env(config) as env:
            env.reset(seed=0)
            def collect(row):
                report['events'].extend(to_jsonable(row['world']['grasp']['events']))
            env.add_state_sink(collect)
            with SegmentRunner(env, output/'trail') as runner:
                actor = runner.interaction()
                assert actor.action_spec['grasp_assist']['model'] == 'contact_weld_v1'
                with pytest.raises(PermissionError): env.interaction().get('world')
                segments = cube_policy(actor, split=True)
                report.update(segments=to_jsonable(segments), task_result=to_jsonable(env._task.result))
                assert any(e['event'] == 'acquired' for e in report['events']), 'Policy never acquired assisted grasp'
                assert any(e['event'] == 'released' for e in report['events']), 'Policy never released assisted grasp'
                assert not any(e['event'] == 'lost' for e in report['events']), report['events']
                assert len(segments) == 2 and segments[0]['end_state_ref'] == segments[1]['start_state_ref']
                assert env._task.result.task_success, env._task.result
                assert not env._world.read_state()['assist_active']
                report['status'] = 'passed'
    except BaseException:
        report.update(status='failed', traceback=traceback.format_exc())
        raise
    finally:
        write_json_atomic(output/'report.json', report)
