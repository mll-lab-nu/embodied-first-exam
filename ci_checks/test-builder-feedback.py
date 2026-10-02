#!/usr/bin/env python3
"""Builder feedback contract regressions. Physical evidence is recorded separately."""
from copy import deepcopy
import ast
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
spec = importlib.util.spec_from_file_location('feedback_tool', ROOT/'harbor_templates/topogym/common/rcb_topogym.py')
tool = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tool
spec.loader.exec_module(tool)
from topogym.utils.io import write_json_atomic, make_asset_tree_readable, sha256_file
from topogym.world.initial_state import save_numeric_archive, load_numeric_archive, require_same_layout
from topogym.world.physics.initial_state_compatibility import layout, require_compatible, built_geometry
from topogym.world.state import BufferState, pack_buffer
from cuda_profiles import image_tag
from topogym.world.physics import pbd_initial_state as codec


class FeedbackTests(unittest.TestCase):
    def robot(self, native=.002):
        adapter = tool._Robot.__new__(tool._Robot)
        adapter.groups = {'left': SimpleNamespace(gripper_field='gripper_position_m')}
        adapter.arm_slice = {'left': slice(0, 2)}
        adapter.grip_index = {'left': 2}
        adapter.width_table = {'left': (np.array([0., .058]), np.array([.00746875, .037]))}
        accepted = {'left': dict(joint_position_rad=[0., 0.], gripper_position_m=native)}
        adapter.robot = SimpleNamespace(capture_state=lambda: SimpleNamespace(targets=deepcopy(accepted)),
                                        validate_action=lambda command: command)
        return adapter, accepted

    def test_hold_does_not_need_prior_query(self):
        adapter, accepted = self.robot()
        for value in (.002, .005, .00746875, .020, .037):
            accepted['left']['gripper_position_m'] = value
            width = adapter.native_to_width('left', value)
            command = adapter.command(np.array([.1, .2, width], dtype=np.float32))
            self.assertEqual(command['left']['gripper_position_m'], value)
            self.assertAlmostEqual(command['left']['joint_position_rad'][0], .1, places=6)

    def test_open_close_and_restore_follow_accepted_target(self):
        adapter, accepted = self.robot()
        opened = adapter.command([0, 0, .058])
        self.assertEqual(opened['left']['gripper_position_m'], .037)
        accepted.update(opened)
        closed = adapter.command([0, 0, 0])
        self.assertEqual(closed['left']['gripper_position_m'], .00746875)
        accepted['left']['gripper_position_m'] = .002  # reset/rewind
        self.assertEqual(adapter.command([0, 0, 0])['left']['gripper_position_m'], .002)

    def test_rejected_command_cannot_poison_hold(self):
        adapter, _ = self.robot()
        with patch.object(adapter.robot, 'validate_action', side_effect=ValueError('invalid joint')):
            with self.assertRaises(ValueError):
                adapter.command([999, 0, .058])
        self.assertEqual(adapter.command([0, 0, 0])['left']['gripper_position_m'], .002)

    def test_limited_smoke_holds_command_instead_of_measured_grip(self):
        from difficulty_eval import LIMITED_SMOKE
        measured = np.array([.1, .036])  # Fingers stop on an object above width zero.
        command = np.array([.2, 0.])     # The accepted closing target remains zero.
        observation = SimpleNamespace(last={'camera':np.zeros((1,1,3))},
            meta={'ok':True,'proprio':{'now':np.r_[measured,command].tolist()}})
        case = self
        class Robot:
            def __init__(self, **kwargs): pass
            def spec(self):
                return {'action_types':{'joint_position':{'dim':2}},'control_hz':40,
                        'proprio_groups':{'joint_cmd':[2,2,'accepted targets']}}
            def get_obs(self): return observation
            def submit(self, kind, actions, **kwargs):
                case.assertEqual(kind,'joint_position')
                np.testing.assert_array_equal(actions,np.asarray(command[None,:],dtype=np.float32))
                return observation
        with patch.dict(sys.modules, {'rcb_client':SimpleNamespace(Robot=Robot)}):
            exec(LIMITED_SMOKE, {})

    def test_standard_replay_only_executes_live_rows(self):
        from unittest.mock import Mock
        from contextlib import redirect_stdout
        import io
        path=ROOT/'harbor_templates/topogym/limited/environment/sim/replay.py'
        spec=importlib.util.spec_from_file_location('standard_replay_test', path)
        replay=importlib.util.module_from_spec(spec); spec.loader.exec_module(replay)
        actions=np.arange(24,dtype=np.float32).reshape(6,4)
        session=SimpleNamespace(replay=Mock(return_value={'success':False,'state_sha':'replay'}),
            start_video=Mock(),stop_video=Mock(),close=Mock(),instance_sha='fixture',
            instance_exact=True,instance_matches=True)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'episode.json').write_text(json.dumps(dict(live_rows=3)))
            np.savez(root/'trajectory.npz',actions=actions,task='fixture',instance_sha='fixture')
            (root/'instance.json').write_text(json.dumps(dict(action_dim=4)))
            argv=['replay.py','--task','fixture','--instance',str(root/'instance.json'),'--data',d]
            with patch.dict(sys.modules, {'rcb_topogym':SimpleNamespace(Session=lambda *a,**kw:session, load_trajectory=tool.load_trajectory, atomic_json=tool.atomic_json, InstanceMismatch=tool.InstanceMismatch)}), \
                 patch.object(sys,'argv',argv), patch.object(sys,'path',list(sys.path)), redirect_stdout(io.StringIO()):
                self.assertEqual(replay.main(),0)
        session.replay.assert_called_once()
        np.testing.assert_array_equal(session.replay.call_args.args[0],actions[:3])
        session.close.assert_called_once()

    def test_limited_preflight_runs_real_client_in_its_own_image(self):
        import difficulty_eval as evaluation
        from itertools import product
        failures = ({}, {'infra_error':1}, {'gpu_lost':1}, {'error':'replay failed'},
                    {'video':False}, {'replay_success':None}, {'finalized':False})
        for delivered, failure in product((True, False), failures):
            with self.subTest(delivered=delivered, failure=failure), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); calls=[]
                def command(argv, **kwargs):
                    calls.append((list(map(str,argv)),kwargs))
                    if '/srv/finalize.sh' in argv:
                        (root/'build/limited/replay.mp4').write_bytes(b'synthetic contract fixture')
                    return 0, 'sha256:client\n'
                runner=evaluation.DifficultyEvaluation.__new__(evaluation.DifficultyEvaluation)
                runner.args=SimpleNamespace(run_id='client-dependency-contract')
                runner.work=root; runner.run=root/'run'
                runner.source_sha='abc123';runner.gpu_device='0';runner.image='physics-only:test'
                runner.delivery=(SimpleNamespace(workspace='fixture',images={'client':{'image':'client-only:test'}},
                    labels=lambda:{'test':'client-boundary','topogym.owner':'fixture-controller'}) if delivered else None)
                runner.commands=SimpleNamespace(env={},run_command=command,check_resources=lambda:None)
                final = dict(done=True,video=True,finalized=True,replay_success=False,reason='timeout')
                final.update(failure)
                runner.collector=SimpleNamespace(load_json=lambda _:final)
                runner.build_dir=lambda _:root/'build'
                runner.task_dir=lambda _,mode:root/'task'
                self.assertEqual(runner.limited_preflight({'slug':'topogym-test-i00','task_id':'interlocked_claws'}), not failure)
                client, _=next((a,k) for a,k in calls if k.get('input_text')==evaluation.LIMITED_SMOKE)
                self.assertEqual(client[:2],['docker','run'])
                self.assertNotIn(runner.image,client)
                self.assertNotIn('--gpus',client)
                self.assertTrue(client[client.index('--network')+1].startswith('container:'))
                self.assertFalse(any('/sim:' in part for part in client))
                self.assertTrue(any('/rcb_client.py:/check/rcb_client.py:ro' in part for part in client))
                self.assertEqual(json.loads((root/'build/limited-client-image.json').read_text())['id'],'sha256:client')
                self.assertTrue(any(a[:2]==['docker','build'] and a[-1]==str(root/'task/environment') for a,_ in calls))
                self.assertTrue(any(a[-2:]==['sh','/srv/finalize.sh'] for a,_ in calls))
                self.assertTrue(any(a[-2:]==['sh','/srv/run.sh'] for a,_ in calls))

    def test_explicit_public_mode_survives_replacement_and_umask(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'public.json'
            old = os.umask(0o077)
            try:
                for value in (1, 2):
                    write_json_atomic(path, {'value': value}, mode=0o644)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                    self.assertEqual(json.loads(path.read_text())['value'], value)
                private = Path(d)/'private.json'
                write_json_atomic(private, {})
                self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
                manifest = save_numeric_archive(Path(d)/'asset', {'x': np.arange(12)}, {'test': True})
                for p in manifest.parent.iterdir():
                    self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o644)
                self.assertEqual(stat.S_IMODE(manifest.parent.stat().st_mode), 0o755)
                np.testing.assert_array_equal(load_numeric_archive(manifest)[0]['x'], np.arange(12))
            finally:
                os.umask(old)

    def test_asset_normalization_preserves_content_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/'assets'; root.mkdir(mode=0o700)
            path = root/'file'; path.write_text('immutable'); path.chmod(0o600)
            before = sha256_file(path)
            make_asset_tree_readable(root)
            self.assertEqual(sha256_file(path), before)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            (root/'escape').symlink_to(Path(d))
            with self.assertRaisesRegex(ValueError, 'symlink'):
                make_asset_tree_readable(root)

    def test_layout_error_explains_actual_hardware_sized_buffer(self):
        with self.assertRaisesRegex(ValueError, r'collider.*16384.*24064'):
            require_same_layout(np.zeros((4, 16384, 3)), np.zeros((4, 24064, 3)), 'collider')

    def test_compatibility_ignores_no_actual_differences(self):
        source = dict(device=dict(multiprocessor_count=128), codec='v2', geometry='a', options={'dt': .01})
        require_compatible(source, deepcopy(source))
        for field, value in [('codec', 'v3'), ('geometry', 'b'), ('options', {'dt': .02}),
                             ('device', {'multiprocessor_count': 188})]:
            target = deepcopy(source); target[field] = value
            with self.assertRaisesRegex(ValueError, f'backend/{field}'):
                require_compatible(source, target)

    def test_geometry_hash_detects_same_shape_different_mesh(self):
        def state(value):
            return SimpleNamespace(buffers=[BufferState(None, np.array(value), 'numpy',
                            'RigidSolver/data_manager/verts_info/init_pos')])
        self.assertNotEqual(built_geometry(state([0., 1.])), built_geometry(state([0., 2.])))

    def test_packed_and_decoded_layout_match(self):
        value = np.arange(100000, dtype=np.float32)
        self.assertEqual(layout(value), layout(pack_buffer(value)))
        self.assertNotEqual(layout(value), layout(value.astype(np.float64)))

    def test_profile_image_tags(self):
        with patch.dict(os.environ, {'RCB_IMAGE_REGISTRY': 'local/test'}):
            self.assertEqual(image_tag(ROOT, 'cu128'), 'local/test/rcb-topogym:0.2.6-cu128')
            self.assertTrue(image_tag(ROOT, 'cu130').endswith(':0.2.6-cu130'))
            with self.assertRaises(ValueError):
                image_tag(ROOT, 'auto')

    def test_actual_build_command_uses_same_profile_tag_as_generator(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); fake=root/'docker'; calls=root/'calls.jsonl'
            fake.write_text('#!'+sys.executable+'\nimport json,sys,os\n'
                            'with open(os.environ["TEST_DOCKER_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
            fake.chmod(0o755)
            env=dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'], TEST_DOCKER_CALLS=str(calls),
                     TOPOGYM_CUDA_FLAVOR='cu130',RCB_IMAGE_REGISTRY='local/test')
            result=subprocess.run(['bash',str(ROOT/'scripts/build_images.sh'),'topogym'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            command=[json.loads(line) for line in calls.read_text().splitlines() if json.loads(line)[0]=='build'][0]
            with patch.dict(os.environ,env):
                self.assertIn(image_tag(ROOT),command)
            self.assertIn('CUDA_FLAVOR=cu130',command)
            self.assertIn('UIPC_CONFIG=uipc-build-cu130.json',command)
            self.assertIn('RUNTIME_LOCK=difficulty-eval-runtime-cu130.lock',command)

    def test_world_source_is_provenance_in_v2_but_strict_in_v1(self):
        import genesis as gs
        world = SimpleNamespace(physics_dt_s=.005, entities={}, scene=SimpleNamespace(sim=SimpleNamespace(
            _active_solvers=[type('PBDSolver', (), {})()], coupler=type('LegacyCoupler', (), {})())))
        state = SimpleNamespace(buffers=[BufferState(None, np.arange(3.), 'numpy',
                       'RigidSolver/data_manager/verts_info/init_pos')])
        original = codec.sha256_file
        with patch.object(codec, 'device_identity', return_value={'type':'cpu'}), patch.object(gs, 'np_float', np.float64, create=True):
            first_v2 = codec.backend_identity(world, state=state)
            first_v1 = codec.backend_identity(world, codec='rigid_pbd_numeric_v1')
            with patch.object(codec, 'sha256_file', side_effect=lambda p: 'comment-only-change' if Path(p).name=='genesis_world.py' else original(p)):
                self.assertEqual(first_v2, codec.backend_identity(world, state=state))
                self.assertNotEqual(first_v1, codec.backend_identity(world, codec='rigid_pbd_numeric_v1'))

    def test_incompatible_archive_never_calls_world_restore(self):
        from unittest.mock import Mock
        from topogym.utils.io import canonical_hash
        payload = {'sentinel': np.arange(3.)}
        source = {'codec':'rigid_pbd_numeric_v2', 'device':{'multiprocessor_count':128},
                  'payload_layout_sha256':canonical_hash(layout(payload))}
        metadata = dict(identity={'seed':0}, identity_sha256=canonical_hash({'seed':0}),
                        includes_robot=False, backend=source)
        world = SimpleNamespace(capture_state=lambda: SimpleNamespace(grasp_state=None), restore_state=Mock())
        with patch.object(codec, 'load_numeric_archive', return_value=(payload, metadata)), patch.object(
                codec, 'backend_identity', return_value={'codec':'rigid_pbd_numeric_v2','device':{'multiprocessor_count':188}}):
            with self.assertRaisesRegex(ValueError, 'multiprocessor_count'):
                codec.restore_initial_state(world, 'unused', identity={'seed':0})
        world.restore_state.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
