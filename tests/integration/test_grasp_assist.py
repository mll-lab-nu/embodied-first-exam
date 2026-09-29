"""Real Genesis + standard Env action/rewind, using an explicit small fixture.

Two revolute lift arms with opposing prismatic fingers qualify the mechanism;
this is not an ALOHA/Panda task solve or a production grasp-point qualification.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import traceback
import numpy as np
import pytest

from topogym.simulator import Env, SimulatorConfig
from topogym.utils.grasp import GraspAssistConfig, GraspTarget
from topogym.utils.io import to_jsonable, write_json_atomic
from topogym.robot.description import JointGroup, RobotDescription, GraspDescription
from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec

pytestmark = [pytest.mark.genesis, pytest.mark.rigid]


def fixture_robot(path):
    inertia = '<inertial><origin xyz="0 0 0"/><mass value="0.1"/><inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/></inertial>'
    links = ['<robot name="assist_fixture"><link name="base"/>']
    groups = []
    for side, y in (("left", -.15), ("right", .15)):
        links += [f'<link name="{side}/hand">{inertia}</link>',
            f'<joint name="{side}/lift" type="revolute"><parent link="base"/><child link="{side}/hand"/>'
            f'<origin xyz="0 {y} .3"/><axis xyz="0 1 0"/><limit lower="-1" upper="1" effort="10" velocity="2"/></joint>']
        fingers = []
        for finger, sign in (("a", -1), ("b", 1)):
            name = f'{side}/{finger}'
            fingers.append(name)
            links += [f'<link name="{name}">{inertia}<collision><geometry><box size=".04 .01 .03"/></geometry></collision></link>',
                f'<joint name="{name}" type="prismatic"><parent link="{side}/hand"/><child link="{name}"/>'
                f'<origin xyz=".1 0 0"/><axis xyz="0 {sign} 0"/><limit lower=".002" upper=".04" effort="20" velocity=".1"/></joint>']
        groups.append(JointGroup(side, (f'{side}/lift',), tuple(fingers), tuple(fingers), f'{side}/hand',
            ((-1., 1.),), 'gripper_position_m', (.002, .04), (0., .035, .035),
            (100., 200., 200.), (10., 5., 5.), (10., 20., 20.),
            tcp_position_in_hand_m=(.1, 0., 0.), grasp=GraspDescription(tuple(fingers), .035, .002)))
    path.write_text(''.join(links)+ '</robot>')
    return RobotDescription('assist_fixture', tuple(groups))


class FixtureTask(TaskDefinition):
    task_id = 'assist_fixture'
    defaults = {'stable_duration_s': .5}
    goal_complete = False

    def declare(self, asset_dir, table_height_m):
        return TaskSpec(tuple(EntitySpec(f'cube_{side}', 'box', None,
            position_m=(.1, y, .3), morph_options={'size': (.04, .04, .04)},
            material={'rho': 500., 'friction': .5}) for side, y in (('left', -.15), ('right', .15))))

    def evaluate_state(self, state):
        return False, None, {}


def test_real_automatic_grasp_and_independent_release(tmp_path, monkeypatch):
    import genesis as gs
    from topogym.world.genesis_world import GenesisWorld
    import topogym.robot.joint_position as robot_module
    output = Path(os.environ.get('TOPOGYM_TEST_OUTPUT', tmp_path))
    output.mkdir(parents=True, exist_ok=True)
    description = fixture_robot(output/'fixture.urdf')
    monkeypatch.setattr(robot_module, 'describe_robot', lambda _: description)
    device = os.environ.get('TOPOGYM_TEST_DEVICE', 'cpu')
    def build(cls, *args, **kwargs):
        if not getattr(gs, '_initialized', False):
            gs.init(backend=getattr(gs, device), precision='64', seed=17, logging_level='warning')
        scene = gs.Scene(sim_options=gs.options.SimOptions(dt=.005, substeps=4),
            rigid_options=gs.options.RigidOptions(max_dynamic_constraints=4, enable_neutral_collision=True), show_viewer=False)
        robot = scene.add_entity(gs.morphs.URDF(file=str(output/'fixture.urdf'), fixed=True, merge_fixed_links=False),
            material=gs.materials.Rigid(gravity_compensation=1., friction=.5))
        table = scene.add_entity(gs.morphs.Box(size=(.5, .6, .04), pos=(.1, 0, .26), fixed=True))
        ceiling = scene.add_entity(gs.morphs.Box(size=(.4, .15, .02), pos=(.1, -.15, .37), fixed=True))
        return cls(scene, entities={'robot': robot, 'table': table, 'ceiling': ceiling}, seed=17)
    monkeypatch.setattr(GenesisWorld, 'from_tabletop', classmethod(build))
    # Box morphology gives a single named link; inspect name from Genesis after
    # build in configure_grasp, with test declarations assigned before reset.
    assist = GraspAssistConfig('contact_weld_v1', tuple(GraspTarget(f'cube_{s}', 'box_baselink', radius_m=.04) for s in ('left', 'right')))
    config = SimulatorConfig(task_id='cast_coil', robot_id='aloha', enable_rgb=False,
        compute_backend=device, physics_dt_s=.005, control_decimation=5,
        max_physics_steps=2000, enable_privileged=True, grasp_assist=assist)
    report = dict(scope='Genesis mechanical fixture via ordinary Interaction; no task solve or production robot qualification',
                  status='running', rgb=False, config=to_jsonable(config), checks={})
    write_json_atomic(output/'report.json', report)
    rows = (output/'ticks.jsonl').open('w')
    try:
        with Env(config) as env:
            env._task_class = FixtureTask
            env.add_state_sink(lambda row: rows.write(json.dumps(to_jsonable(row))+'\n'))
            env.reset(seed=17)
            operator = env.interaction()
            with pytest.raises(PermissionError): operator.get('world')
            initial = env.state_history[0].ref
            assert not env._world.read_state()['assist_active']
            for _ in range(5): operator.step({})
            assert not env._world.read_state()['assist_active']
            report['checks']['open_contacts_do_not_acquire'] = True
            operator.step({s: {'gripper_position_m': .018} for s in ('left', 'right')})
            for _ in range(35):
                operator.step({})
                if all(s['phase'] == 'holding' for s in env._world._grasp_manager.hands.values()): break
            manager = env._world._grasp_manager
            assert all(s['binding'] for s in manager.hands.values()), manager.read()
            held = env.state_history[-1].ref
            held_grasp = manager.capture()
            report['checks']['bilateral_acquisition'] = to_jsonable(held_grasp)
            before = env.state_history[-1].state_id
            with pytest.raises(ValueError): operator.step({'left': {'gripper_position_m': float('nan')}})
            assert env.state_history[-1].state_id == before and manager.capture() == held_grasp
            report['checks']['invalid_action_is_atomic'] = True
            operator.step({s: {'joint_position_rad': [-.2]} for s in ('left', 'right')})
            for _ in range(20): operator.step({})
            lifted = env._world.read_state()
            assert all(lifted['bodies'][f'cube_{s}']['position_m'][2] > .311 for s in ('left', 'right'))
            assert all(s['phase'] == 'holding' for s in manager.hands.values()), manager.read()
            report['checks']['lift_under_gravity'] = {s: lifted['bodies'][f'cube_{s}']['position_m'].tolist() for s in ('left', 'right')}
            # The first acquired constraint is non-tail. Only it is released.
            peer = manager.hands['right']['binding']
            operator.step({'left': {'gripper_position_m': .035}})
            assert manager.hands['left']['binding'] is None and manager.hands['right']['binding'] == peer
            assert manager.backend.exists(peer)
            report['checks']['non_tail_independent_release'] = True
            final_positions = env._world.read_state()['bodies']['cube_right']['position_m'].copy()
            env.privileged.rewind_to(held)
            assert manager.capture() == held_grasp
            operator.step({s: {'joint_position_rad': [-.2]} for s in ('left', 'right')})
            for _ in range(20): operator.step({})
            operator.step({'left': {'gripper_position_m': .035}})
            np.testing.assert_allclose(env._world.read_state()['bodies']['cube_right']['position_m'], final_positions, atol=2e-7, rtol=0)
            report['checks']['held_rewind_continuation'] = True
            operator.step({'right': {'gripper_position_m': .035}})
            assert not env._world.read_state()['assist_active'] and not manager.backend.pairs()
            report['checks']['full_release'] = True
            # Rewind into held state and press against an actual fixture ceiling.
            env.privileged.rewind_to(held)
            operator.step({'left': {'joint_position_rad': [-.8]}})
            for _ in range(20): operator.step({})
            blocked = env._world.read_state()
            assert blocked['bodies']['cube_left']['position_m'][2] <= .346
            assert manager.hands['left']['phase'] == 'holding'
            assert manager.backend.exists(manager.hands['left']['binding'])
            report['checks']['obstacle_blocks_held_object'] = to_jsonable(blocked['bodies']['cube_left'])
            env.privileged.rewind_to(initial)
            assert not env._world.read_state()['assist_active'] and not manager.backend.pairs()
            assert all(s['intent'] == 'open' for s in manager.hands.values())
            report['checks']['before_grasp_rewind'] = True
            old = operator
            env.reset(seed=17)
            assert not env._world.read_state()['assist_active']
            with pytest.raises(RuntimeError): old.step({})
            report['checks']['reset_clears_and_invalidates_handle'] = True
            # Deliberately fail after a real creation to exercise partial writes.
            operator = env.interaction()
            birth = env.state_history[-1].ref
            manager = env._world._grasp_manager
            acquire = manager.backend.acquire
            def fail_after_creation(*args):
                acquire(*args)
                raise RuntimeError('injected post-creation failure')
            monkeypatch.setattr(manager.backend, 'acquire', fail_after_creation)
            with pytest.raises(RuntimeError, match='Environment execution failed'):
                operator.step({s: {'gripper_position_m': .018} for s in ('left', 'right')})
                for _ in range(35): operator.step({})
            assert env._faulted and env._world._faulted
            failed_tick = env._world.physics_step
            assert failed_tick == env.state_history[-1].physics_step+1
            env.privileged.rewind_to(birth)
            assert not manager.backend.pairs() and not env._faulted
            assert all(s['binding'] is None for s in manager.hands.values())
            report['checks']['partial_backend_failure_and_rewind'] = dict(failed_tick=failed_tick, restored_tick=0)
            report['status'] = 'passed'
    except BaseException:
        report['status'], report['traceback'] = 'failed', traceback.format_exc()
        raise
    finally:
        rows.close()
        write_json_atomic(output/'report.json', report)
