#!/usr/bin/env python3
"""Adversarial complete shared-writer captures; CPU contracts, not native physics."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.knot_untying.physics_audit import audit_capture
from topogym.planning.knot_untying.replay_evidence import ReplayCapture
from topogym.utils.io import sha256_file, write_json_atomic


REST = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.], [0., 0., .1]])
FACES = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
BOX = np.array([[x, y, z] for x in (-.2, .2) for y in (-.2, .2) for z in (-.2, .2)])


def row(tick):
    return dict(state=dict(physics_step=tick, branch_id=3, episode_id='e', state_id=tick*10,
        parent_state_id=(tick-1)*10, sim_time_s=tick*.0025),
        world=dict(physics_step=tick, fem=dict(rope=dict(position_m=REST+[0., 0., 1.])),
                   ipc=dict(native_valid=True), contacts={},
                   articulations={entity: dict(links={entity: dict(position_m=position, quaternion_wxyz=[1., 0., 0., 0.])})
                                  for entity, position in (('table', [0., 0., 0.]), ('robot', [2., 0., 1.]))}))


def geometry(env, folder, initial):
    np.savez_compressed(folder/'rope_volume.npz', rest=REST, elements=np.array([[0, 1, 2, 3]]), surface_faces=FACES)
    np.savez_compressed(folder/'rigid_collision_meshes.npz', geom_0_vertices=BOX, geom_1_vertices=BOX,
                        geom_0_cover_vertices=BOX, geom_1_cover_vertices=BOX)
    write_json_atomic(folder/'collision_model.json', dict(schema_version=2,
        meshes=[dict(key=f'geom_{i}', geom_index=i, link_index=i, entity=name, link=name,
                     native_type='BOX', cover_kind='analytic_box_corners') for i, name in enumerate(('table', 'robot'))],
        native_valid_geometry_pairs=[[0, 1]],
        rope_volume_sha256=sha256_file(folder/'rope_volume.npz'),
        rigid_meshes_sha256=sha256_file(folder/'rigid_collision_meshes.npz')))


class PhysicsAuditTests(unittest.TestCase):
    def capture(self, directory, *, change=lambda r: None, success=True, last_tick=1):
        callbacks = []
        env = SimpleNamespace(config=dict(physics_dt_s=.0025), _asset_build=SimpleNamespace(sha256={}),
                              episode_metadata={}, timing_spec={}, tick_record=lambda: row(0))
        def add(callback):
            callbacks.append(callback)
            return lambda: callbacks.remove(callback)
        env.add_state_sink = add
        session = SimpleNamespace(env=env, physics_steps=0)
        folder = Path(directory)/'capture'
        capture = ReplayCapture(session, folder, geometry_exporter=geometry)
        for tick in range(1, last_tick+1):
            last = row(tick)
            change(last)
            callbacks[0](last)
        session.physics_steps = last_tick
        capture.close(dict(success=success, physics_steps=last_tick))
        return folder

    def test_parallel_measurements_preserve_findings_hashes_and_volume_streaks(self):
        for kind in ('separated', 'penetration', 'volume_streak'):
            def change(r):
                tick = r['state']['physics_step']
                if kind == 'penetration' and tick == 6:
                    r['world']['fem']['rope']['position_m'] = REST+[0., 0., .2-1e-6]
                elif kind == 'volume_streak' and 3 <= tick <= 5:
                    r['world']['fem']['rope']['position_m'][3, 2] = .99
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                folder = self.capture(d, change=change, last_tick=6)
                serial = audit_capture(folder, Path(d)/'serial')
                parallel = audit_capture(folder, Path(d)/'parallel', workers=2)
                self.assertTrue(serial['complete'], serial['error'])
                self.assertEqual({k: v for k, v in serial.items() if k != 'workers'},
                                 {k: v for k, v in parallel.items() if k != 'workers'})
                self.assertEqual((Path(d)/'serial/findings.jsonl').read_bytes(),
                                 (Path(d)/'parallel/findings.jsonl').read_bytes())
                if kind == 'volume_streak':
                    self.assertEqual(parallel['maximum_nonpositive_volume_streak_ticks'], 3)
                if kind == 'penetration':
                    self.assertFalse(parallel['qualified'])

    def test_parallel_rewind_is_rejected_and_invalid_worker_budget_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            folder = self.capture(d)
            path = folder/'private/physics_states.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[-1]['state']['branch_id'] = 7
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            result = audit_capture(folder, Path(d)/'audit', workers=2)
            self.assertFalse(result['qualified'])
            self.assertFalse(result['complete'])
            self.assertIn('Broken tick lineage', result['error'])
            for workers in (0, -1, True, 1.5):
                with self.assertRaises(ValueError):
                    audit_capture(folder, Path(d)/'invalid', workers=workers)
            self.assertFalse((Path(d)/'invalid').exists())

    def test_complete_separated_filled_meshes_pass_and_native_failure_stays_failure(self):
        for success in (True, False):
            with self.subTest(success=success), tempfile.TemporaryDirectory() as d:
                folder = self.capture(d, success=success)
                result = audit_capture(folder, Path(d)/'audit')
                self.assertTrue(result['complete'], result['error'])
                self.assertTrue(result['physical_checks_passed'])
                self.assertEqual(result['qualified'], success)
                self.assertEqual(result['ticks_checked'], 2)

    def test_last_tick_containment_is_found_without_surface_crossing(self):
        def change(r): r['world']['articulations']['robot']['links']['robot']['position_m'] = [0., 0., 1.]
        with tempfile.TemporaryDirectory() as d:
            result = audit_capture(self.capture(d, change=change), Path(d)/'audit')
            self.assertTrue(result['complete'])
            self.assertFalse(result['qualified'])
            self.assertEqual(result['ticks_with_findings'], 1)
            rows = (Path(d)/'audit/findings.jsonl').read_text()
            self.assertIn('rope_collider_interior_overlap', rows)

    def test_native_accepted_transient_volume_anomaly_is_retained_without_extra_failure(self):
        def change(r): r['world']['fem']['rope']['position_m'][3, 2] = .99
        with tempfile.TemporaryDirectory() as d:
            result = audit_capture(self.capture(d, change=change), Path(d)/'audit')
            self.assertTrue(result['native_success'])
            self.assertTrue(result['physical_checks_passed'])
            self.assertEqual(result['nonpositive_volume_ticks'], 1)
            self.assertLess(result['minimum_volume_ratio'], 0.)

    def test_rigid_overlap_and_native_penetration_are_reported(self):
        def change(r):
            r['world']['articulations']['robot']['links']['robot']['position_m'] = [0., 0., 0.]
            r['world']['contacts'] = dict(link_a=[0], link_b=[1], penetration=[.00001])
        with tempfile.TemporaryDirectory() as d:
            result = audit_capture(self.capture(d, change=change), Path(d)/'audit')
            self.assertFalse(result['qualified'])
            rows = (Path(d)/'audit/findings.jsonl').read_text()
            self.assertIn('rigid_interior_overlap', rows)
            self.assertIn('native_rigid_contact_penetration_reported', rows)

    def test_table_boundary_contact_is_allowed_but_micrometre_overlap_is_not(self):
        for offset, expected in ((0., True), (-1e-6, False)):
            def change(r): r['world']['fem']['rope']['position_m'] = REST+[0., 0., .2+offset]
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as d:
                result = audit_capture(self.capture(d, change=change), Path(d)/'audit')
                self.assertEqual(result['qualified'], expected)
                if expected:
                    self.assertEqual(result['contact_ticks'], 1)

    def test_truncated_history_and_midpass_rewind_cannot_pass(self):
        for mode in ('truncate', 'branch', 'parent'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                folder = self.capture(d)
                path = folder/'private/physics_states.jsonl'
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                if mode == 'truncate': rows.pop()
                elif mode == 'branch': rows[-1]['state']['branch_id'] = 7
                else: rows[-1]['state']['parent_state_id'] = 999
                path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                result = audit_capture(folder, Path(d)/'audit')
                self.assertFalse(result['complete'])
                self.assertFalse(result['qualified'])
                self.assertIsNotNone(result['error'])

    def test_geometry_tamper_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            folder = self.capture(d)
            with (folder/'rope_volume.npz').open('ab') as stream: stream.write(b'tamper')
            result = audit_capture(folder, Path(d)/'audit')
            self.assertFalse(result['qualified'])
            self.assertIn('hash mismatch', result['error'])


if __name__ == '__main__':
    unittest.main()
