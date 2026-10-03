#!/usr/bin/env python3
"""Post-merge boundary regressions. Synthetic physics is explicitly not GPU qualification."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'scripts/eai_standard'),
               str(ROOT / 'harbor_templates/topogym/common')]
import rcb_topogym as tool
import rcb_limited as protocol
from difficulty_eval import DifficultyEvaluation


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def server_function(name, namespace):
    """Load the real boundary without the server's module-level GPU startup."""
    import ast
    path = ROOT / 'harbor_templates/topogym/limited/environment/sim/server.py'
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class Repairs(unittest.TestCase):
    def test_zip_edge_cases_are_invalid_submissions_and_queue_continues(self):
        import collect_batch_results as collector
        grade = module('zip_grade', 'harbor_templates/topogym/unlimited/tests/grade.py')
        # Exercise both the early header read and a later NumPy member read.
        for member in ('actions.npy', 'task.npy'):
            for encrypted in (False, True):
                with self.subTest(member=member, encrypted=encrypted), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    path = root / 'bad.npz'
                    np.savez(path, task='fixture', actions=np.zeros((1, 2)))
                    raw = bytearray(path.read_bytes())
                    with zipfile.ZipFile(path) as archive:
                        local = archive.getinfo(member).header_offset
                        central = archive.start_dir
                        for info in archive.infolist():
                            if info.filename == member:
                                break
                            central += 46 + sum(struct.unpack_from('<HHH', raw, central + 28))
                    for offset in (local + (6 if encrypted else 8), central + (8 if encrypted else 10)):
                        struct.pack_into('<H', raw, offset, (struct.unpack_from('<H', raw, offset)[0] | 1) if encrypted else 99)
                    path.write_bytes(raw)
                    (root / 'instance.json').write_text('{"action_dim":2}')
                    row = dict(task_id='fixture', task_number=1, difficulty='easy', sample_id='s00',
                               scene_seed=0, slug='topogym-fixture-easy-s00', evaluable_for_task_success=True)
                    ev = DifficultyEvaluation.__new__(DifficultyEvaluation)
                    ev.run = root; ev.jobs = root / 'jobs'; ev.harbor = Path(sys.executable)
                    ev.args = SimpleNamespace(rerun_incomplete=False)
                    ev.manifest = dict(instances=[row], trial_count=2)
                    ev.collector = collector
                    ev.task_dir = lambda row, mode: root / mode
                    for name in ('verify_image', 'verify_packages', 'require_phase_complete', 'canary', 'gpu_ready', 'collect'):
                        setattr(ev, name, Mock())
                    launched = []
                    def launch(task, job):
                        mode = task.name; launched.append(mode)
                        trial = ev.jobs / job / 'trial'; logs = trial / 'verifier'; logs.mkdir(parents=True)
                        if mode == 'unlimited':
                            args = ['grade', '--family', 'fixture', '--instance', str(root / 'instance.json'), '--traj', str(path)]
                            with patch.object(grade, 'LOG_DIR', str(logs)), patch.object(sys, 'argv', args), patch.object(tool, 'Session') as scene:
                                self.assertEqual(grade.main(), 0); scene.assert_not_called()
                            reward = json.loads((logs / 'reward.json').read_text())
                            self.assertEqual((reward['success'], reward['bad_trajectory'], reward['grader_error']), (0, 1, 0))
                            self.assertTrue((logs / 'submission_error.json').is_file())
                        else:
                            reward = dict(success=0, finalized=1, grader_error=0)
                            (logs / 'reward.json').write_text(json.dumps(reward))
                        (trial / 'result.json').write_text(json.dumps(dict(task_name=row['slug'] +
                            ('-privileged' if mode == 'unlimited' else '-standard'), finished_at='fixture',
                            verifier_result=dict(rewards=reward))))
                        self.assertEqual(collector.classify_trial(trial.parent, row, mode)[0],
                                         'invalid_submission' if mode == 'unlimited' else 'unsolved')
                        return 0
                    ev.launch_job = launch
                    ev.run_trials()
                    self.assertEqual(launched, ['unlimited', 'limited'])

    def test_valid_npz_and_physics_runtime_error_keep_their_meaning(self):
        grade = module('runtime_grade', 'harbor_templates/topogym/unlimited/tests/grade.py')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); path = root / 'good.npz'
            for save in (np.savez, np.savez_compressed):
                save(path, task='fixture', actions=np.zeros((1, 2)))
                np.testing.assert_array_equal(tool.load_trajectory(path, 'fixture', 2)[0], np.zeros((1, 2)))
            (root / 'instance.json').write_text('{"action_dim":2}')
            args = ['grade', '--family', 'fixture', '--instance', str(root / 'instance.json'), '--traj', str(path)]
            with patch.object(grade, 'LOG_DIR', d), patch.object(sys, 'argv', args), \
                    patch.object(tool, 'Session', side_effect=RuntimeError('physics startup failure')):
                self.assertEqual(grade.main(), 0)
            reward = json.loads((root / 'reward.json').read_text())
            self.assertEqual(reward['grader_error'], 1)
            self.assertNotIn('bad_trajectory', reward)

    def test_standard_startup_mismatch_is_not_an_infrastructure_crash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'instance.json').write_text('{"action_dim":2}')
            code = '''import os,sys,runpy
from unittest.mock import patch
sys.path.insert(0, sys.argv[1] + '/harbor_templates/topogym/common')
import rcb_topogym as tool
with patch.object(tool, 'Session', side_effect=tool.InstanceMismatch('wrong nodes')):
    runpy.run_path(sys.argv[1] + '/harbor_templates/topogym/limited/environment/sim/server.py', run_name='__main__')
'''
            env = {**os.environ, 'RCB_DATA': d, 'RCB_INSTANCE': str(root / 'instance.json')}
            child = subprocess.run([sys.executable, '-c', code, str(ROOT)], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            final = json.loads((root / 'final.json').read_text())
            self.assertTrue(final['finalized'] and final['instance_mismatch'])
            self.assertEqual(final['infra_error'], 0)
            source = (ROOT / 'harbor_templates/topogym/limited/tests/grade.py').read_text()
            # Replace container data paths before inserting a host path, which
            # can itself live under /data when TMPDIR points to the data drive.
            source = source.replace('/data/', d + '/').replace('/logs/verifier', str(root / 'verifier'))
            exec(compile(source, 'standard_grade', 'exec'), {})
            reward = json.loads((root / 'verifier/reward.json').read_text())
            self.assertEqual((reward['success'], reward['instance_mismatch'], reward['infra_error'], reward['grader_error']), (0, 1, 0, 0))

    def test_invalid_trajectories_are_input_errors(self):
        cases = [dict(task='fixture'), dict(task='wrong', actions=np.zeros((1, 2))),
                 dict(task='fixture', actions=np.zeros((2, 3))), dict(task='fixture', actions=np.zeros((0, 2))),
                 dict(task='fixture', actions=[['1', '2']]), dict(task='fixture', actions=[[np.nan, 0]]),
                 dict(task='fixture', actions=[[1e100, 0]])]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bad.npz'
            for fields in cases:
                np.savez(path, **fields)
                with self.subTest(fields=list(fields)), self.assertRaises(tool.InvalidTrajectory):
                    tool.load_trajectory(path, 'fixture', 2)
            path.write_bytes(b'PK\x03\x04broken')
            with self.assertRaises(tool.InvalidTrajectory):
                tool.load_trajectory(path, 'fixture', 2)
            with self.assertRaises(FileNotFoundError):
                tool.load_trajectory(Path(d) / 'absent', 'fixture', 2)

    def test_grader_invalid_input_never_constructs_simulator(self):
        grade = module('repair_grade', 'harbor_templates/topogym/unlimited/tests/grade.py')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'instance.json').write_text('{"action_dim":2}')
            np.savez(root / 'bad.npz', task='fixture')
            args = ['grade', '--family', 'fixture', '--instance', str(root / 'instance.json'), '--traj', str(root / 'bad.npz')]
            with patch.object(grade, 'LOG_DIR', d), patch.object(sys, 'argv', args), patch.object(tool, 'Session') as session:
                self.assertEqual(grade.main(), 0)
                session.assert_not_called()
            reward = json.loads((root / 'reward.json').read_text())
            self.assertEqual((reward['success'], reward['bad_trajectory'], reward['grader_error']), (0, 1, 0))

    def test_verdict_survives_real_process_kill_during_media_close(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'instance.json').write_text('{"action_dim":2}')
            np.savez(root / 'trajectory.npz', task='fixture', actions=np.zeros((1, 2)))
            code = '''import sys, os, signal, runpy
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1] + '/harbor_templates/topogym/common')
import rcb_topogym as t
n = [0]
def replay(a):
 n[0] += 1
 return dict(success=True, state_sha='s', sim_steps=1, physics_steps=3, sim_time_s=.0075)
def stop():
 assert n[0] == 2
 os.kill(os.getpid(), signal.SIGKILL)
t.Session = lambda *a, **kw: SimpleNamespace(instance_matches=True, instance_exact=True, replay=replay,
 start_video=lambda *a, **kw:None, stop_video=stop, close=lambda:None)
root, data = sys.argv[1:3]
os.environ['RCB_VERIFIER_LOG_DIR'] = data
sys.argv = ['grade', '--family', 'fixture', '--instance', data+'/instance.json', '--traj', data+'/trajectory.npz']
runpy.run_path(root+'/harbor_templates/topogym/unlimited/tests/grade.py', run_name='__main__')
'''
            child = subprocess.run([sys.executable, '-c', code, str(ROOT), d], capture_output=True, text=True)
            self.assertEqual(child.returncode, -9, child.stderr)
            self.assertEqual(json.loads((root / 'verdict.json').read_text())['reward']['success'], 1)
            self.assertEqual((root / 'reward.txt').read_text(), '1\n')
            self.assertEqual(json.loads((root / 'reward.json').read_text())['replays'], 2)

    def session(self):
        s = tool.Session.__new__(tool.Session)
        s.robot = SimpleNamespace(action_dim=2, clip=lambda a: np.clip(a, -1, 1), command=lambda a: a)
        s.env = SimpleNamespace(step=Mock(return_value=(None, 1, True, False,
            dict(task_success=True, physics_steps=3, action_duration_s=.0075))))
        s.episode_done = False; s.episode_end = None; s.n_steps = 0; s.max_steps = 100
        s.physics_steps = 0; s.sim_time_s = 0.; s._video = None; s._recording = []; s._recorded_ticks = []
        s.table_guard = SimpleNamespace(apply=lambda target, previous: target)   # rules 2026-10-03
        s._targets = None
        return s

    def test_standard_verdict_survives_media_process_kill(self):
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'instance.json').write_text('{"action_dim":2}')
            (root / 'episode.json').write_text(json.dumps(dict(live_rows=1, success=True, live_sha='s')))
            np.savez(root / 'trajectory.npz', task='fixture', actions=np.zeros((1, 2)))
            code = '''import sys, os, signal, runpy
from types import SimpleNamespace
root, data = sys.argv[1:3]
sys.path.insert(0, root + '/harbor_templates/topogym/common')
import rcb_topogym as t
t.Session = lambda *a, **kw: SimpleNamespace(instance_matches=True, instance_exact=True, instance_sha='s',
 replay=lambda *a, **kw:dict(success=True,state_sha='s',sim_steps=1), start_video=lambda *a, **kw:None,
 stop_video=lambda:os.kill(os.getpid(), signal.SIGKILL), close=lambda:None)
sys.argv=['replay', '--data', data, '--task', 'fixture', '--instance', data+'/instance.json', '--video', data+'/replay.mp4']
runpy.run_path(root+'/harbor_templates/topogym/limited/environment/sim/replay.py', run_name='__main__')
'''
            child = subprocess.run([sys.executable, '-c', code, str(ROOT), d], capture_output=True, text=True)
            self.assertEqual(child.returncode, -9, child.stderr)
            shell = (ROOT / 'harbor_templates/topogym/limited/environment/sim/finalize.sh').read_text()
            finalize = shell.split("python - <<'PY'\n")[-1].split('\nPY')[0]
            with patch.dict(os.environ, RCB_DATA=d), redirect_stdout(io.StringIO()):
                exec(compile(finalize, 'finalize.sh:merge', 'exec'), {})
            final = json.loads((root / 'final.json').read_text())
            self.assertTrue(final['finalized'] and final['success'] and final['replay_success'])
            self.assertFalse(final['video'])
            self.assertEqual(final['media_status'], 'pending')

    def test_rejected_action_does_not_change_ledger(self):
        s = self.session()
        s.robot.command = Mock(side_effect=ValueError('rejected'))
        with self.assertRaises(ValueError):
            s.step([0, 0])
        self.assertEqual(s._recording, [])
        self.assertEqual(s.n_steps, 0)
        s.env.step.assert_not_called()

    def test_terminal_and_partial_tick_counts(self):
        s = self.session()
        for _ in range(5):
            self.assertTrue(s.step([2, 0]))
        s.env.step.assert_called_once()
        self.assertEqual((s.n_steps, s.physics_steps, s.sim_time_s), (1, 3, .0075))
        np.testing.assert_array_equal(s._recording, [[1, 0]])
        self.assertEqual(s._recorded_ticks, [3])

    def test_dt_validation_and_float_tolerance(self):
        for value in (.0375, float('nan'), float('inf'), 0, -.025, .5001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                protocol.control_periods(value, 40)
        for count in (1, 2, 20):
            self.assertEqual(protocol.control_periods(np.nextafter(count / 40, np.inf), 40), count)

    def test_standard_reports_actual_partial_time(self):
        import time
        fn = server_function('meta_common', dict(ctrl_steps=lambda: 1,
            E=dict(step=1, calls=1, t0=time.time(), done=True, reason='time_limit'),
            S=SimpleNamespace(physics_steps=3, sim_time_s=.0075, safety=lambda: {}), CTRL_HZ=40, time=time,
            SPEC=dict(budget=dict(wall_clock_s=30), proprio_layout=[]), proprio_row=lambda: np.zeros(0), OBS_CALIBRATION=False))
        meta = fn([])
        self.assertEqual((meta['physics_steps'], meta['sim_time_s']), (3, .0075))

    def test_standard_rejects_fractional_dt_before_recording(self):
        recorder = Mock()
        fn = server_function('do_submit', dict(np=np, L=protocol, CTRL_HZ=40, CAMS=['cam'],
            SPEC=dict(action_types=dict(joint_position=dict(dim=2), not_yet=[])), recorder=recorder))
        with self.assertRaisesRegex(ValueError, 'integer multiple'):
            fn(dict(type='joint_position', dt=.0375), np.zeros((2, 2)))
        recorder.assert_not_called()

    def test_trusted_trajectory_prefix_and_ticks(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'trajectory.npz'
            np.savez(p, task='f', actions=np.zeros((5, 2)), meta=json.dumps(dict(live_rows=1)),
                     physics_steps_per_action=np.array([3, 10, 10, 10, 10]))
            actions, ticks = tool.load_trajectory(p, 'f', 2, trusted=True)
            self.assertEqual(len(actions), 1)
            np.testing.assert_array_equal(ticks, [3])
            submitted, submitted_ticks = tool.load_trajectory(p, 'f', 2)
            self.assertEqual(len(submitted), 5)
            self.assertIsNone(submitted_ticks)

    def test_equal_centroid_deformation_is_not_same_instance(self):
        s = tool.Session.__new__(tool.Session)
        s.objects = lambda: {'cloth': dict(position=[0, 0, 0])}
        s._soft_state = lambda: {'cloth': dict(position_m=[[-2, 0, 0], [2, 0, 0]])}
        inst = dict(objects=s.objects(), soft_state={'cloth': dict(position_m=[[-1, 0, 0], [1, 0, 0]])})
        self.assertFalse(s._poses_match(inst))
        inst['soft_state'] = s._soft_state()
        self.assertTrue(s._poses_match(inst))

    def test_asset_identity_normalizes_location_but_detects_content(self):
        with tempfile.TemporaryDirectory() as d:
            identities = []
            s = tool.Session.__new__(tool.Session)
            for name in ('first', 'second'):
                root = Path(d) / name; root.mkdir()
                (root / 'model.urdf').write_text(f'<mesh filename="{root}/mesh.obj"/>')
                (root / 'mesh.obj').write_text('v 0 0 0\nv 1 0 0\n')
                s.env = SimpleNamespace(_asset_build=SimpleNamespace(root=root, files=['model.urdf', 'mesh.obj']))
                identities.append(s._asset_identity())
            self.assertEqual(*identities)
            (root / 'mesh.obj').write_text('v 0 0 0\nv 2 0 0\n')
            self.assertNotEqual(s._asset_identity(), identities[-1])

    def test_shared_recording_initial_final_and_timestamps(self):
        from topogym.sensors.observation import SensorFrame
        import imageio.v2 as imageio
        with tempfile.TemporaryDirectory() as d:
            s = tool.Session.__new__(tool.Session)
            s._video = None; s.control_hz = 40.; s.task = 'fixture'; s.instance_sha = 's'
            current = [0]
            s.env = SimpleNamespace(sensor_frame=lambda: SensorFrame('episode', 1, current[0], current[0] * 10,
                current[0] / 40, {'cam': np.full((32, 32, 3), current[0] * 30, np.uint8)}, {}))
            s.status = lambda: dict(success=False)
            path = Path(d) / 'replay.mp4'
            s.start_video(path, fps=15)
            self.assertFalse(list(Path(d).glob('*.recording-*')))
            s._video_begin()
            for i in range(1, 6):
                current[0] = i; s._video_add()
            s.stop_video()
            recording = next(Path(d).glob('*.recording-*/recording'))
            frames = [json.loads(x) for x in (recording / 'frame_map.jsonl').read_text().splitlines()]
            self.assertEqual(frames[0]['source_state_id'], 0)
            self.assertEqual(frames[-1]['source_state_id'], 5)
            self.assertTrue(all(abs(f['target_video_time_s'] - f['source_sim_time_s']) <= 1 / 15 for f in frames))
            with imageio.get_reader(path) as reader:
                self.assertEqual(len(list(reader.iter_data())), len(frames))
            np.testing.assert_array_equal(imageio.imread(path.with_suffix('.last.png')), np.full((32, 32, 3), 150, np.uint8))

    def test_call_deadline_before_physics(self):
        with tempfile.TemporaryDirectory() as d:
            ep = protocol.Episode(d, dim=2, resume='approx')
            with patch.object(protocol.faulthandler, 'dump_traceback_later'), patch.object(protocol.faulthandler, 'cancel_dump_traceback_later'):
                cid = ep.call_begin('/observe', deadline=protocol.time.time() - 1)
                self.assertTrue(ep.poll_stop())
                self.assertEqual(ep.rows, 0)
                ep.call_end(cid, '/observe')

    def test_resume_preserves_partial_tick_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            ep = protocol.Episode(d, dim=2, resume='approx')
            state = dict(calls=1, step=1, success=False, done=False)
            kwargs = dict(state=state, step=lambda row: None, state_sha=lambda: 'same',
                          proprio=lambda: np.zeros(2), spec={})
            with patch.object(ep, '_arm'):
                self.assertFalse(ep.begin(**kwargs))
            ep.journal([.1, .2], physics_steps=3)
            ep.checkpoint(state, kwargs['state_sha'], kwargs['proprio'])
            ep._jf.close(); ep._tf.close()
            resumed = protocol.Episode(d, dim=2, resume='approx')
            replay = Mock()
            with patch.object(resumed, '_arm'):
                self.assertTrue(resumed.begin(**kwargs, step_ticks=replay))
            self.assertEqual(replay.call_args.args[1], 3)
            self.assertEqual(resumed.rows, 1)

    def test_watchdog_is_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as d:
            ep = protocol.Episode(d, dim=2, resume='approx')
            ep.log(dict(ev='start'))
            protocol._write_json(ep.f_call_watchdog, dict(deadline=0))
            with patch.object(ep, 'give_up', side_effect=RuntimeError('captured')) as failed:
                with self.assertRaisesRegex(RuntimeError, 'captured'):
                    ep.begin(state={}, step=lambda _: None, state_sha=lambda: 's', proprio=lambda: [], spec={})
            self.assertTrue(failed.call_args.kwargs['infra'])

    def test_reward_compatibility_can_be_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            tool.atomic_json(Path(d) / 'verdict.json', dict(schema_version=2, reward=dict(success=1, grader_error=0)))
            self.assertTrue(tool.recover_reward(d))
            self.assertEqual((Path(d) / 'reward.txt').read_text(), '1\n')

    def test_oversized_npy_header_rejected_before_allocation(self):
        import io
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            header = io.BytesIO()
            np.lib.format.write_array_header_1_0(header, dict(descr='<f8', fortran_order=False, shape=(10**12, 2)))
            path = Path(d) / 'oversized.npz'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('actions.npy', header.getvalue())
            with self.assertRaises(tool.InvalidTrajectory):
                tool.load_trajectory(path, 'f', 2)

    def test_cleanup_rechecks_workspace_owner(self):
        a = DifficultyEvaluation.__new__(DifficultyEvaluation)
        a.work = ROOT; a.run = ROOT / 'runs/example'; a.args = SimpleNamespace(run_id='same')
        a.delivery = None; a.owns_gpu_lock = True
        own = a.resource_labels(); other = dict(own, **{'topogym.workspace': 'other'})
        calls = []
        def command(argv, **kw):
            calls.append(argv)
            if argv[1] == 'ps': return 0, 'a' * 12 + '\n' + 'b' * 12
            if argv[1] == 'inspect':
                return 0, json.dumps([dict(Id=argv[2], Config=dict(Labels=own if argv[2][0] == 'a' else other))])
            return 0, ''
        a.commands = SimpleNamespace(run_command=command)
        a.cleanup_containers()
        self.assertEqual([c for c in calls if c[1] == 'rm'], [['docker', 'rm', '-f', 'a' * 12]])

    def test_incomplete_blanket_attempt_is_preserved_and_retried(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            build = Path(d); (build / 'blanket').mkdir(); (build / 'blanket/partial').write_text('evidence')
            a = DifficultyEvaluation.__new__(DifficultyEvaluation)
            a.source = ROOT; a.source_sha = 'source'; a.docker_sim = lambda *args: list(args)
            def command(argv, **kw):
                output = Path(argv[-1]); state = output / 'state'; state.mkdir(parents=True)
                (state / 'arrays.npz').write_bytes(b'fixture')
                (state / 'manifest.json').write_text(json.dumps(dict(arrays=dict(path='arrays.npz',
                    sha256=hashlib.sha256(b'fixture').hexdigest()))))
                return 0, ''
            a.commands = SimpleNamespace(run_command=Mock(side_effect=command))
            state = a.prepare_blanket(dict(scene_seed=7), build)
            self.assertIn('blanket-attempt-001', str(state))
            self.assertEqual((build / 'blanket/partial').read_text(), 'evidence')
            self.assertEqual(a.prepare_blanket(dict(scene_seed=7), build), state)
            self.assertEqual(a.commands.run_command.call_count, 1)

    def test_substep_violation_and_missing_coverage(self):
        contact = module('repair_contacts', 'ci_checks/test-rigid-grasp-contact.py')
        task, _, _ = contact.fixture()
        final = contact.state()
        final['terminal_contract_version'] = 2
        final['contact_events'] = dict(substeps_complete=True, contact_snapshots=[
            dict(contacts=contact.state([(1, 2, .002)])['contacts'], grasp={}),
            dict(contacts=contact.state()['contacts'], grasp={})])
        self.assertIn('1 mm', task.rigid_measurements(final)[-1])
        final['terminal_contract_version'] = 1
        self.assertIsNone(task.rigid_measurements(final)[-1])
        final['terminal_contract_version'] = 2
        final['contact_events']['substeps_complete'] = False
        with self.assertRaises(RuntimeError):
            task.rigid_measurements(final)


if __name__ == '__main__':
    unittest.main(verbosity=2)
