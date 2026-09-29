"""Small dual-gripper material fixture through the real Env and policy runner.

No alternate stepping/recording loop. Mechanical qualification is deliberately
separate from the full Panda/Robotiq and Nyx rollout.
"""
import hashlib
import json
import os
from pathlib import Path
import traceback
import numpy as np
import pytest
from topogym.simulator import Env, SimulatorConfig, SegmentRunner
from topogym.tasks.base import TaskDefinition, TaskSpec, EntitySpec, AttachmentSpec
from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
from topogym.utils.io import to_jsonable, write_json_atomic
from fixtures.soft_grasp import cloth_asset
from test_grasp_assist import fixture_robot

pytestmark = [pytest.mark.genesis]


class Actions:
    def __init__(self, actions): self.actions = iter(actions)
    def act(self, obs): return next(self.actions, None)


class MaterialTask(TaskDefinition):
    task_id = 'soft_mechanism'
    defaults = {'stable_duration_s': .2}
    goal_complete = False
    material_kind = 'pbd'
    pin_boundary = False

    def declare(self, asset_dir, table_height_m):
        folder = Path(asset_dir)
        if self.material_kind == 'pbd':
            path, mapping = cloth_asset(folder, (.1, 0, .287), length=.06, width=.38, spacing=.01)
            return TaskSpec((EntitySpec('soft', 'mesh', path, physics_model='pbd_cloth', material_map_path=mapping,
                morph_options=dict(decimate=False, convexify=False, file_meshes_are_zup=True)),),
                dict(pbd=dict(particle_size=.006, max_stretch_solver_iterations=12)))
        from topogym.assets.geometry.rope_volume import write_rope_volume
        from topogym.assets.materials import rope_fem_parameters
        from topogym.utils.geometry.rope import make_elastic_tube_mesh, write_obj
        # Stress-free straight rope; the FEM fixture wrists are collinear so
        # each jaw gap crosses a different material band transversely.
        line = np.column_stack((np.linspace(-.04, .24, 29), np.zeros(29), np.full(29, .287)))
        volume = write_rope_volume(folder/'rope.npz', line, .004, spacing=.012)
        v, f = make_elastic_tube_mesh(line, radius=.004, radial_segments=8)
        path = folder/'rope.obj'; write_obj(path, v, f)
        entities = (EntitySpec('soft', 'mesh', path, physics_model='fem_elastic', volume_path=volume,
            material=rope_fem_parameters(), morph_options=dict(decimate=False, convexify=False)),)
        attachments = ()
        if self.pin_boundary:
            entities += (EntitySpec('anchor', 'box', None, position_m=(-.06, 0., .287), fixed=True,
                material={'coup_type':'ipc_only'}, morph_options={'size':(.02,.02,.02)}),)
            attachments = (AttachmentSpec('permanent_end', 'soft', 'anchor', 'start', .004),)
        return TaskSpec(entities, dict(fem={}, ipc={}), attachments=attachments)

    def evaluate_state(self, state): return False, None, {}

    def bind(self, entities):
        super().bind(entities)
        if self.material_kind == 'pbd' and self.pin_boundary:
            from topogym.utils.arrays import to_numpy
            entity = entities['soft']
            x = to_numpy(entity.get_particles_pos()).reshape(-1,3)
            # A fixed boundary patch separated from both grasp regions.
            anchored = np.flatnonzero((x[:,0] < .08) & (np.abs(x[:,1]) < .006))
            assert len(anchored)
            entity.fix_particles(particles_idx_local=anchored)


@pytest.mark.parametrize('assist', [False, True], ids=['unassisted', 'assisted'])
def test_real_dual_material_grasp(tmp_path, monkeypatch, assist):
    import genesis as gs
    from topogym.world.genesis_world import GenesisWorld
    import topogym.robot.joint_position as robot_module
    output = Path(os.environ.get('TOPOGYM_TEST_OUTPUT', tmp_path)); output.mkdir(parents=True, exist_ok=True)
    if not assist:
        output = output/'unassisted'
        output.mkdir(parents=True, exist_ok=True)
    material = os.environ.get('TOPOGYM_TEST_MATERIAL', 'pbd')
    description = fixture_robot(output/'fixture.urdf')
    if material == 'fem':
        # IPC external articulation requires a collision surface for every link,
        # including fixture wrists/base which the rigid-only test leaves empty.
        import xml.etree.ElementTree as ET
        tree = ET.parse(output/'fixture.urdf')
        for side, x in (('left', -.1), ('right', .1)):
            tree.find(f"joint[@name='{side}/lift']/origin").set('xyz', f'{x} 0 .3')
        for link in tree.getroot().findall('link'):
            if link.find('collision') is None:
                collision = ET.SubElement(link, 'collision')
                geometry = ET.SubElement(collision, 'geometry')
                ET.SubElement(geometry, 'box', size='.008 .008 .008')
        tree.write(output/'fixture.urdf')
    monkeypatch.setattr(robot_module, 'describe_robot', lambda _: description)
    monkeypatch.setattr(MaterialTask, 'material_kind', material)
    device = os.environ.get('TOPOGYM_TEST_DEVICE', 'cpu')
    def build(cls, *args, **kwargs):
        if not getattr(gs, '_initialized', False):
            gs.init(backend=getattr(gs, device), precision='64', seed=17, logging_level='warning')
        options = kwargs['physics_options']
        from topogym.world.physics.ipc import scene_options
        extra = dict(pbd_options=gs.options.PBDOptions(**options['pbd'])) if material == 'pbd' else dict(
            fem_options=gs.options.FEMOptions(), coupler_options=scene_options(options['ipc']))
        scene = gs.Scene(sim_options=gs.options.SimOptions(dt=.01, substeps=10),
            rigid_options=gs.options.RigidOptions(enable_neutral_collision=True), show_viewer=False, **extra)
        robot = scene.add_entity(gs.morphs.URDF(file=str(output/'fixture.urdf'), fixed=True, merge_fixed_links=False),
            material=gs.materials.Rigid(gravity_compensation=1., friction=.5,
                **({'coup_type':'external_articulation'} if material=='fem' else {})), name='robot')
        table = scene.add_entity(gs.morphs.Box(size=(.4, .6, .04), pos=(.1, 0, .26), fixed=True),
            material=gs.materials.Rigid(**({'coup_type':'ipc_only'} if material=='fem' else {})), name='table')
        ground = scene.add_entity(gs.morphs.Plane(),
            material=gs.materials.Rigid(**({'coup_type':'ipc_only'} if material=='fem' else {})), name='ground')
        if material == 'fem':
            from topogym.world.physics.ipc import install_for_scene
            home = {n: v for g in description.groups for n, v in zip(g.arm_joints+g.finger_joints, g.home)}
            install_for_scene(scene, initial_robot_positions=home)
        return cls(scene, entities=dict(robot=robot, table=table, ground=ground), seed=17)
    monkeypatch.setattr(GenesisWorld, 'from_tabletop', classmethod(build))
    config = SimulatorConfig(task_id='cast_coil', robot_id='aloha', enable_rgb=False, enable_privileged=True,
        work_dir=output/'episodes',
        compute_backend=device, physics_dt_s=.01, solver_substeps=10, control_decimation=1, max_physics_steps=1000,
        grasp_assist=GraspAssistConfig('pbd_local_patch_v1' if material=='pbd' else 'ipc_soft_band_v1',
            (SoftGraspTarget('soft', **(dict(spatial_radius_m=.006, material_radius_m=.009)
                if material == 'pbd' else {})),), stable_time_s=.02) if assist else GraspAssistConfig())
    report = dict(status='running', scope='dual mechanical gripper, native material, shared simulator and run_policy',
                  config=to_jsonable(config), checks={}, events=[])
    write_json_atomic(output/'report.json', report)
    try:
        with Env(config) as env:
            env._task_class = MaterialTask
            env.reset(seed=17)
            if not assist:
                from topogym.utils.arrays import to_numpy
                entity = env._world.entities['soft']
                def positions():
                    if material == 'pbd':
                        return to_numpy(entity.get_particles_pos()).reshape(-1,3)
                    from topogym.world.physics.fem import read_vertices
                    return read_vertices(entity)['position_m']
                before = positions().copy()
                with SegmentRunner(env, output/'settle') as runner:
                    result = runner.run_policy(request_id='unassisted_settle', policy=Actions([{}]*8),
                        submission_hash=hashlib.sha256(b'unassisted_settle_8_ticks').hexdigest())
                assert result['reason'] == 'policy_done', result
                displacement = float(np.linalg.norm(positions()-before, axis=1).max())
                report['max_settle_displacement_m'] = displacement
                assert displacement < .01, displacement
                report.update(status='passed', unassisted_initial_stability=True)
                return
            manager = env._world._grasp_manager
            report['constraint_switches'] = []
            for method in ('attach_native', 'detach_native'):
                original = getattr(manager.backend, method)
                def checked_switch(binding, operation=original, label=method):
                    entity = manager.backend.entities['soft']
                    def state():
                        from topogym.utils.arrays import to_numpy
                        if material == 'pbd':
                            return manager.backend.positions('soft'), to_numpy(entity.get_particles_vel()).reshape(-1,3)
                        from topogym.world.physics.fem import read_vertices
                        data = read_vertices(entity)
                        return data['position_m'], data['velocity_m_s']
                    before_x, before_v = state()
                    operation(binding)
                    after_x, after_v = state()
                    np.testing.assert_array_equal(after_x, before_x)
                    np.testing.assert_array_equal(after_v, before_v)
                    report['constraint_switches'].append(dict(operation=label, hand=binding['hand'],
                        position_jump_m=0., velocity_jump_m_s=0., physics_step=env._world.physics_step))
                monkeypatch.setattr(manager.backend, method, checked_switch)
            env.add_state_sink(lambda row: report['events'].extend(to_jsonable(row['world']['grasp']['events'])))
            birth = env.state_history[-1].ref
            def execute(label, action, ticks):
                commands = action if isinstance(action, list) else [action]+[{}]*(ticks-1)
                folder = output/label
                with SegmentRunner(env, folder) as runner:
                    result = runner.run_policy(request_id=label, policy=Actions(commands),
                        submission_hash=hashlib.sha256(json.dumps(commands, sort_keys=True).encode()).hexdigest())
                report['checks'][label] = to_jsonable(result)
                write_json_atomic(output/'report.json', report)
                assert result['reason'] == 'policy_done', result
            execute('open', {}, 8)
            assert not manager.read()['active']
            execute('close', {s:{'gripper_position_m':.006} for s in ('left','right')}, 40)
            assert all(s['binding'] for s in manager.hands.values()), manager.read()
            bindings = [s['binding'] for s in manager.hands.values()]
            assert not np.intersect1d(bindings[0]['indices'], bindings[1]['indices']).size
            held = env.state_history[-1].ref; saved = manager.capture()
            with pytest.raises(ValueError):
                env.interaction().step({'left':{'gripper_position_m':float('nan')}})
            assert env.state_history[-1].ref == held and manager.capture() == saved
            report['invalid_action_atomic'] = True
            lift = [{s:{'joint_position_rad':[-.2*(3*t*t-2*t*t*t)]} for s in ('left','right')}
                    for t in np.linspace(0., 1., 61)[1:]] + [{}]*15
            execute('lift', lift, len(lift))
            x = manager.backend.positions('soft')
            report['checks']['max_height_m'] = float(x[:,2].max())
            assert min(x[b['indices'],2].mean() for b in bindings) > .30
            assert all(s['binding'] for s in manager.hands.values()), manager.read()
            before_release = x.copy()
            execute('release_left', {'left':{'gripper_position_m':.035}}, 1)
            assert manager.hands['left']['binding'] is None and manager.hands['right']['binding']
            execute('release_right', {'right':{'gripper_position_m':.035}}, 5)
            assert not manager.read()['active']
            manager.backend.verify_bindings([])
            env.privileged.rewind_to(held)
            assert manager.capture() == saved
            execute('rewind_lift', lift, len(lift))
            np.testing.assert_allclose(manager.backend.positions('soft'), before_release, atol=2e-6, rtol=0)
            execute('reverse_release', {'right':{'gripper_position_m':.035}}, 1)
            assert manager.hands['left']['binding'] and manager.hands['right']['binding'] is None
            env.privileged.rewind_to(held)
            obstructed = [{'left':{'joint_position_rad':[.25*(3*t*t-2*t*t*t)]}}
                          for t in np.linspace(0.,1.,61)[1:]] + [{}]*10
            execute('table_obstruction', obstructed, len(obstructed))
            reason = manager.hands['left']['rejection']
            if manager.hands['left']['phase'] == 'lost':
                assert reason in {'material_obstacle_penetration','material_follow_error','material_strain'}, reason
                response = 'protective_release'
            else:
                binding = manager.hands['left']['binding']
                assert binding and manager.backend.positions('soft')[binding['indices'],2].min() >= .278
                actual = env._world.read_state()['articulations']['robot']['joints']['left/lift']['position'][0]
                assert abs(actual-.25) > .1
                response = 'physically_blocked_at_table'
            manager.backend.verify_bindings([s['binding'] for s in manager.hands.values() if s['binding']])
            report['obstacle_response'] = dict(outcome=response, reason=reason,
                scope='gripper and material against table; not continuous collision or force qualification')
            env.privileged.rewind_to(birth)
            assert not manager.read()['active']
            # Real native constraint is created before the injected failure.
            original_acquire = manager.backend.acquire
            def fail_after_acquire(hand, key):
                original_acquire(hand, key)
                raise RuntimeError('injected after native soft attachment')
            monkeypatch.setattr(manager.backend, 'acquire', fail_after_acquire)
            with pytest.raises(RuntimeError):
                env.interaction().step({s:{'gripper_position_m':.006} for s in ('left','right')})
                for _ in range(40): env.interaction().step({})
            assert env._world._faulted
            env.privileged.rewind_to(birth)
            assert not manager.read()['active']
            manager.backend.verify_bindings([])
            monkeypatch.setattr(manager.backend, 'acquire', original_acquire)
            old_handle = env.interaction()
            monkeypatch.setattr(MaterialTask, 'pin_boundary', True)
            env.reset(seed=17)
            assert not env._world.read_state()['assist_active']
            with pytest.raises(RuntimeError): old_handle.step({})
            if material == 'pbd':
                manager = env._world._grasp_manager
                fixed = ~manager.backend._birth_free['soft'].astype(bool)
                assert fixed.any()
                execute('permanent_boundary_close', {s:{'gripper_position_m':.006} for s in ('left','right')}, 40)
                # The fixed boundary makes closure overstrain this fixture.
                # Protection must release only temporary bindings and preserve
                # permanent particles; this is a controlled failure, not a lift.
                assert all(s['phase'] == 'lost' and s['rejection'] == 'material_strain'
                           for s in manager.hands.values()), manager.read()
                manager.backend.verify_bindings([])
                assert not manager.backend._free('soft')[fixed].any()
                report['permanent_boundary_protective_release'] = True
            else:
                manager = env._world._grasp_manager
                permanent = env._world.scene.sim.coupler.attachment_pairs[0][2]
                execute('permanent_endpoint_close', {s:{'gripper_position_m':.006} for s in ('left','right')}, 40)
                assert all(s['binding'] for s in manager.hands.values()), manager.read()
                assert not any(np.intersect1d(permanent, s['binding']['indices']).size for s in manager.hands.values())
                execute('permanent_endpoint_release', {s:{'gripper_position_m':.035} for s in ('left','right')}, 5)
                manager.backend.verify_bindings([])
                residual = env._world.scene.sim.coupler.diagnostics()['attachment_residual_m']['permanent_end']
                assert residual < .001, residual
                report['permanent_endpoint_preserved'] = True
                report['permanent_endpoint_residual_m'] = residual
            report.update(status='passed', disjoint_same_entity=True, independent_release_both_orders=True,
                          rewind_held_dynamics=True, rewind_birth=True, partial_failure_recovered=True,
                          reset_clears_and_expires=True)
    except BaseException:
        report.update(status='failed', traceback=traceback.format_exc())
        raise
    finally:
        write_json_atomic(output/'report.json', report)
