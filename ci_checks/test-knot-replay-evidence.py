#!/usr/bin/env python3
"""Evidence coverage, native-call preservation and failure propagation (CPU only)."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.knot_untying.replay_evidence import ReplayCapture, export_geometry, install_physics_capture


def row(tick, *, branch=0, parent=None):
    return dict(state=dict(physics_step=tick, branch_id=branch, episode_id='e', state_id=tick,
                          parent_state_id=tick-1 if parent is None else parent),
                world=dict(fem=dict(rope=dict(position_m=np.zeros((60, 3))))))


class ReplayEvidenceTests(unittest.TestCase):
    def test_geometry_export_uses_read_only_native_poses_and_authored_link_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            asset = folder/'assets'; asset.mkdir()
            destination = folder/'capture'; destination.mkdir()
            np.savez_compressed(asset/'rope_volume.npz', rest=np.zeros((4, 3)))
            vertices = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.], [0., 0., .1]])
            geom_turn, link_turn = Rotation.from_euler('x', .31), Rotation.from_euler('z', .73)
            geom_position, link_position = np.array([2., 3., 4.]), np.array([1.9, 2.8, 4.1])
            def forbidden(): raise AssertionError('Must not update live geometry caches')
            geom = SimpleNamespace(idx=5, init_verts=vertices, init_faces=[[0, 1, 2]],
                                   type=SimpleNamespace(name='MESH'), is_convex=True, get_verts=forbidden)
            link = SimpleNamespace(idx=2, name='hand', geoms=[geom])
            calls = []
            def get_pos(indices, *, relative):
                calls.append((indices, relative))
                return geom_position[None]
            def get_quat(indices, *, relative):
                calls.append((indices, relative))
                return geom_turn.as_quat()[[3, 0, 1, 2]][None]
            solver = SimpleNamespace(get_geoms_pos=get_pos, get_geoms_quat=get_quat,
                                     collider=SimpleNamespace(_valid_collision_pairs=[]))
            env = SimpleNamespace(_asset_build=SimpleNamespace(root=asset), _task=SimpleNamespace(table_height_m=.92),
                _world=SimpleNamespace(entities={'robot': SimpleNamespace(links=[link])},
                                      scene=SimpleNamespace(sim=SimpleNamespace(rigid_solver=solver))))
            pose = dict(position_m=link_position, quaternion_wxyz=link_turn.as_quat()[[3, 0, 1, 2]])
            initial = {'world': {'articulations': {'robot': {'links': {'hand': pose}}}}}
            export_geometry(env, destination, initial)
            with np.load(destination/'rigid_collision_meshes.npz') as data:
                np.testing.assert_allclose(link_turn.apply(data['geom_5_vertices'])+link_position,
                                           geom_turn.apply(vertices)+geom_position, atol=1e-14)
            self.assertEqual(calls, [([5], False), ([5], False)])

    def capture(self, directory, *, branch=0, **kwargs):
        env = SimpleNamespace(config={}, _asset_build=SimpleNamespace(sha256={}),
                              episode_metadata={}, timing_spec={}, tick_record=lambda: row(0, branch=branch))
        env.current = row(0, branch=branch)
        env.frame_callbacks = []
        def add_frame(callback):
            env.frame_callbacks.append(callback)
            return lambda: env.frame_callbacks.remove(callback)
        def sensor_frame():
            state = env.current['state']
            return SimpleNamespace(**{key: state[key] for key in ('episode_id', 'branch_id', 'state_id', 'physics_step')},
                sim_time_s=state['physics_step']*.0025, camera_metadata={},
                rgb={name: np.full((8, 8, 3), 40+i*30, np.uint8)
                     for i, name in enumerate(('cam_high', 'cam_low', 'cam_left_wrist', 'cam_right_wrist'))})
        env.add_frame_sink, env.sensor_frame = add_frame, sensor_frame
        callbacks = []
        def add(callback):
            callbacks.append(callback)
            return lambda: callbacks.remove(callback)
        env.add_state_sink = add
        session = SimpleNamespace(env=env, physics_steps=0, instance_sha='synthetic-test-state')
        capture = ReplayCapture(session, Path(directory)/'pass', geometry_exporter=lambda *args: None, **kwargs)
        return session, capture, callbacks

    def test_initial_and_every_tick_are_written_by_shared_evidence_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            session, capture, callbacks = self.capture(directory)
            for tick in (1, 2):
                callbacks[0](row(tick))
            session.physics_steps = 2
            capture.close(dict(success=True))
            report = json.loads((capture.folder/'capture.json').read_text())
            self.assertTrue(report['complete'])
            self.assertFalse(report['physical_collision_audit_passed'])
            self.assertEqual(report['tick_records'], 3)
            self.assertFalse(callbacks)
            recorded = [json.loads(line) for line in (capture.folder/'private/physics_states.jsonl').read_text().splitlines()]
            self.assertEqual([r['state']['physics_step'] for r in recorded], [0, 1, 2])
            ref = recorded[-1]['world']['fem']['rope']['position_m']
            self.assertTrue((capture.folder/'private'/ref['array_file']).is_file())

    def test_gap_rewind_and_broken_lineage_fail_closed(self):
        for broken in (row(2), row(1, branch=1), row(1, parent=100)):
            with self.subTest(state=broken['state']), tempfile.TemporaryDirectory() as directory:
                session, capture, callbacks = self.capture(directory)
                with self.assertRaises(ValueError): callbacks[0](broken)
                capture.close(dict(success=True))
                report = json.loads((capture.folder/'capture.json').read_text())
                self.assertFalse(report['complete'])
                self.assertIsNotNone(report['error'])
                self.assertFalse(callbacks)

    def test_missing_ticks_cannot_be_sealed_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            session, capture, _ = self.capture(directory)
            session.physics_steps = 2
            capture.close(dict(success=True))
            self.assertFalse(json.loads((capture.folder/'capture.json').read_text())['complete'])

    def test_replay_reset_may_start_on_new_branch_with_unreused_state_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            session, capture, callbacks = self.capture(directory, branch=7)
            first = row(1, branch=7, parent=0)
            first['state']['state_id'] = 503
            second = row(2, branch=7, parent=503)
            second['state']['state_id'] = 504
            for state in (first, second): callbacks[0](state)
            session.physics_steps = 2
            capture.close(dict(success=True))
            self.assertTrue(json.loads((capture.folder/'capture.json').read_text())['complete'])

    def test_disk_exhaustion_stops_capture_and_cannot_be_sealed_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(OSError, 'free disk'):
                self.capture(directory, disk_usage=lambda path: SimpleNamespace(free=0))
            report = json.loads((Path(directory)/'pass/capture.json').read_text())
            self.assertFalse(report['complete'])
            self.assertIn('OSError', report['error'])

    def test_four_view_shared_video_and_numeric_capture_have_the_same_state_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            session, capture, callbacks = self.capture(directory, branch=7, record_video=True)
            session.env.current = row(1, branch=7)
            callbacks[0](session.env.current)
            session.env.frame_callbacks[0](session.env.sensor_frame())
            session.physics_steps = 1
            capture.close(dict(success=True))
            report = json.loads((capture.folder/'capture.json').read_text())
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['video_validation']), 4)
            self.assertEqual({check['frames'] for check in report['video_validation'].values()}, {2})
            video = json.loads((capture.folder/'recording/recording_manifest.json').read_text())
            self.assertEqual(video['recording_status'], 'complete')
            self.assertEqual(video['branch_id'], 7)
            frames = [json.loads(line) for line in (capture.folder/'recording/frame_map.jsonl').read_text().splitlines()]
            self.assertEqual([frame['source_state_id'] for frame in frames], [0, 1])
            self.assertFalse(session.env.frame_callbacks)

    def test_video_cannot_refer_to_a_different_physics_state(self):
        with tempfile.TemporaryDirectory() as directory:
            session, capture, _ = self.capture(directory, record_video=True)
            session.env.current = row(1)
            with self.assertRaisesRegex(ValueError, 'different physical states'):
                session.env.frame_callbacks[0](session.env.sensor_frame())
            capture.close(error='frame identity mismatch')
            self.assertFalse(json.loads((capture.folder/'capture.json').read_text())['complete'])

    def test_wrapper_preserves_native_actions_ticks_and_return_on_each_pass(self):
        calls, captures = [], []
        class Session:
            def reset(self): calls.append(('reset',))
            def step(self, action, **kwargs):
                calls.append(('step', action, kwargs))
                return False
            def replay(self, actions, *, physics_steps):
                self.reset()
                for action, tick in zip(actions, physics_steps):
                    self.step(action, _physics_steps=tick)
                return {'success': False}
        class Capture:
            def __init__(self, session, folder):
                self.folder, self.actions, self.closed = folder, [], None
                captures.append(self)
            def action(self, action, ticks, result): self.actions.append((action, ticks, result))
            def close(self, result, error): self.closed = result, error
        install_physics_capture(SimpleNamespace(Session=Session), '/tmp/unused-knot-evidence', capture_factory=Capture)
        s = Session()
        for _ in range(2):
            self.assertEqual(s.replay([11, 12], physics_steps=[10, 3]), {'success': False})
        self.assertEqual(calls, [('reset',), ('step', 11, {'_physics_steps': 10}), ('step', 12, {'_physics_steps': 3})]*2)
        self.assertEqual([c.folder.name for c in captures], ['physics_replay_01', 'physics_replay_02'])
        for capture in captures:
            self.assertEqual(capture.actions, [(11, 10, False), (12, 3, False)])
            self.assertEqual(capture.closed, ({'success': False}, None))
        self.assertFalse(hasattr(s, '_knot_capture'))

    def test_native_failure_is_not_swallowed_and_capture_is_closed(self):
        closed = []
        class Session:
            def reset(self): pass
            def step(self, action): raise RuntimeError('native solver failure')
            def replay(self, actions):
                self.reset()
                self.step(actions[0])
        class Capture:
            def __init__(self, *args): pass
            def close(self, result, error): closed.append((result, error))
        install_physics_capture(SimpleNamespace(Session=Session), '/tmp/unused-knot-evidence', capture_factory=Capture)
        with self.assertRaisesRegex(RuntimeError, 'native solver failure'):
            Session().replay([1])
        self.assertEqual(closed, [(None, 'RuntimeError: native solver failure')])

    def test_capture_pass_limit_does_not_skip_native_repeats(self):
        resets, captures = [], []
        class Session:
            def reset(self): resets.append(True)
            def step(self, action): return False
            def replay(self, actions):
                self.reset()
                self.step(actions[0])
                return dict(success=False)
        class Capture:
            def __init__(self, session, folder): captures.append(folder)
            def action(self, *args): pass
            def close(self, *args): pass
        install_physics_capture(SimpleNamespace(Session=Session), '/tmp/unused-knot-evidence',
                                capture_factory=Capture, max_passes=1)
        s = Session()
        s.replay([1]); s.replay([1])
        self.assertEqual(len(resets), 2)
        self.assertEqual(len(captures), 1)


if __name__ == '__main__':
    unittest.main()
