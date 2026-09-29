"""Real PBD cloth in the shared simulator; report failures before asserting."""
import os
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
import pytest
from topogym.simulator import Env, SimulatorConfig, SegmentRunner
from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
from topogym.utils.io import to_jsonable, write_json_atomic
from fixtures.soft_grasp import register_soft_grasp
from fixtures.soft_grasp_policy import SoftGraspPolicy

pytestmark = [pytest.mark.genesis, pytest.mark.pbd]


def run_material_policy(output, material, *, rgb=False):
    device = os.environ.get('TOPOGYM_TEST_DEVICE', 'cuda')
    lift_height_m = float(os.environ.get('TOPOGYM_TEST_LIFT_HEIGHT_M', '.055'))
    output.mkdir(parents=True, exist_ok=True)
    config = SimulatorConfig(task_id=f'{material}_grasp_fixture', robot_id=os.environ.get('TOPOGYM_TEST_ROBOT','panda_robotiq'),
        task_parameters={'rope_profile': os.environ.get('TOPOGYM_TEST_FEM_ROPE_PROFILE', 'v13_material_mesh')} if material == 'fem' else {},
        control_mode='EE_ABS', observation_mode='EE', enable_privileged=True,
        work_dir=output/'episodes',
        compute_backend=device, enable_rgb=rgb, physics_dt_s=.025, solver_substeps=10 if material == 'fem' else 25,
        control_decimation=1, max_physics_steps=1000,
        grasp_assist=GraspAssistConfig('pbd_local_patch_v1' if material=='pbd' else 'ipc_soft_band_v1',
            (SoftGraspTarget('soft', **(dict(spatial_radius_m=.006, material_radius_m=.009)
                if material == 'pbd' else {})),), stable_time_s=.03))
    report = dict(status='running', config=to_jsonable(config), scope='independent material fixture', events=[],
                  policy_parameters=dict(lift_height_m=lift_height_m))
    import fixtures.soft_grasp_policy as policy_module
    def submission(part):
        return hashlib.sha256(Path(policy_module.__file__).read_bytes() + json.dumps(
            dict(config=to_jsonable(config), part=part, lift_height_m=lift_height_m), sort_keys=True).encode()).hexdigest()
    write_json_atomic(output/'report.json', report)
    try:
        with register_soft_grasp(), Env(config) as env:
            env.reset(seed=17)
            def collect(row):
                report['events'].extend(to_jsonable(row['world']['grasp']['events']))
            env.add_state_sink(collect)
            initial = env.state_history[-1].ref
            birth = env._world._grasp_manager.capture()
            with SegmentRunner(env, output/'rollout') as runner:
                policy = SoftGraspPolicy(material=material, part='pickup', lift_height_m=lift_height_m)
                first = runner.run_policy(request_id='pickup', policy=policy, submission_hash=submission('pickup'),
                                          mode='unlimited', state_fields=('world',))
                report['pickup'] = to_jsonable(first)
                write_json_atomic(output/'report.json', report)
                assert first['reason'] == 'policy_done', first
                assert env._world.read_state()['assist_active'], report
                held = env.state_history[-1].ref
                holding = env._world._grasp_manager.capture()
                second = runner.run_policy(request_id='release', policy=SoftGraspPolicy(material=material, part='transfer',
                    pickup_position_world_m=policy.pickup_position, lift_height_m=lift_height_m), submission_hash=submission('release'),
                    mode='unlimited', state_fields=('world',))
                report['release'] = to_jsonable(second)
                assert second['reason'] == 'policy_done', second
                assert not env._world.read_state()['assist_active'], report
                state = env._world.read_state()['particles' if material == 'pbd' else 'fem']['soft']
                x, v = np.asarray(state['position_m']), np.asarray(state['velocity_m_s'])
                report['released_material'] = dict(min_height_above_table_m=float(x[:,2].min()-env._task.table_z),
                    max_speed_m_s=float(np.linalg.norm(v, axis=1).max()), centroid_world_m=x.mean(axis=0).tolist())
                assert np.isfinite(x).all() and np.isfinite(v).all()
                assert report['released_material']['min_height_above_table_m'] > -.002
                assert report['released_material']['max_speed_m_s'] < .1
            env.privileged.rewind_to(held)
            assert env._world._grasp_manager.capture() == holding
            env.interaction().step({policy.arm: {policy.gripper_field: policy.opened}})
            assert not env._world.read_state()['assist_active']
            env.privileged.rewind_to(initial)
            assert env._world._grasp_manager.capture() == birth
            assert not any(e['event']=='lost' for e in report['events']), report['events']
            report.update(status='passed', rewind_held_and_birth=True)
    except BaseException:
        report.update(status='failed', traceback=traceback.format_exc())
        raise
    finally:
        write_json_atomic(output/'report.json', report)


def test_pbd_policy_grasp(tmp_path):
    run_material_policy(Path(os.environ.get('TOPOGYM_TEST_OUTPUT', tmp_path)), 'pbd',
                        rgb=os.environ.get('TOPOGYM_TEST_RGB') == '1')
