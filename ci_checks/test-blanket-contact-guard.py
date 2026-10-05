#!/usr/bin/env python3
"""Simulator-instability guard (the blanket PBD blow-up, 2026-10-03): the tooling ends the episode as
"simulator_instability" before a task predicate can grade it, and the standard service and its collect hook report it as
an infrastructure error. The bounded PBD-rigid contact itself needs the GPU (lab replays of trials mCa9CZt / r42VtjE)."""
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import ast
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'harbor_templates/topogym/common')]
import rcb_topogym as tool

SIM = ROOT / 'harbor_templates/topogym/limited/environment/sim'


class FakeTask:
    def evaluate_state(self, state):
        return True, None, {'coverage_ratio': 1.0}


def state(speed, step=7):
    v = np.zeros((4, 3)); v[2, 0] = speed
    return {'physics_step': step, 'sim_time_s': step * .0025,
            'particles': {'blanket': {'position_m': np.arange(12.).reshape(4, 3), 'velocity_m_s': v}}}


class Guard(unittest.TestCase):
    def guarded(self):
        task, trips = FakeTask(), []
        self.assertTrue(tool._guard_particle_speeds(task, trips.append))
        return task, trips

    def test_plausible_speeds_reach_the_task(self):
        task, trips = self.guarded()
        # 9.2 m/s: the fastest validation run that did not blow up (substep-scale oscillation of a pinched cloth)
        self.assertEqual(task.evaluate_state(state(9.2)), (True, None, {'coverage_ratio': 1.0}))
        self.assertEqual(task.evaluate_state(state(tool.PARTICLE_SPEED_LIMIT_M_S)), (True, None, {'coverage_ratio': 1.0}))
        self.assertEqual(task.evaluate_state({'physics_step': 1}), (True, None, {'coverage_ratio': 1.0}))
        self.assertEqual(trips, [])

    def test_fast_particle_is_a_simulator_instability(self):
        task, trips = self.guarded()
        self.assertEqual(task.evaluate_state(state(21.4)), (False, tool.SIMULATOR_INSTABILITY, {}))
        self.assertEqual((trips[0]['particle'], trips[0]['physics_step'], trips[0]['entity']), (2, 7, 'blanket'))
        self.assertAlmostEqual(trips[0]['max_speed_m_s'], 21.4)
        self.assertEqual(trips[0]['position_m'], [6.0, 7.0, 8.0])

    def test_non_finite_particle_is_a_simulator_instability(self):
        task, trips = self.guarded()
        self.assertEqual(task.evaluate_state(state(float('nan')))[1], tool.SIMULATOR_INSTABILITY)
        self.assertIs(trips[0]['finite'], False)
        self.assertIsNone(trips[0]['max_speed_m_s'])


class InfrastructureReporting(unittest.TestCase):
    def merge(self, episode, replay_end):
        """finalize.sh's merge into final.json, on the given live episode.json and replay verdict."""
        shell = (SIM / 'finalize.sh').read_text()
        code = shell.split("python - <<'PY'\n")[-1].split('\nPY')[0]
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'episode.json').write_text(json.dumps(episode))
            Path(d, 'replay.verdict.json').write_text(json.dumps({'replays': [
                {'success': False, 'state_sha': 'r', 'episode_end': replay_end,
                 'instability': {'max_speed_m_s': 21.4} if replay_end == tool.SIMULATOR_INSTABILITY else None}]}))
            with patch.dict(os.environ, RCB_DATA=d), redirect_stdout(io.StringIO()):
                exec(compile(code, 'finalize.sh:merge', 'exec'), {})
            return json.loads(Path(d, 'final.json').read_text())

    def test_live_instability_is_infrastructure(self):
        final = self.merge({'success': False, 'infra_error': 1, 'reason': 'simulator_instability',
                            'simulator_instability': True}, None)
        self.assertEqual((final['infra_error'], final['simulator_instability']), (1, True))

    def test_replay_instability_is_infrastructure(self):
        final = self.merge({'success': True, 'infra_error': 0, 'reason': 'success'}, tool.SIMULATOR_INSTABILITY)
        self.assertEqual((final['infra_error'], final['simulator_instability']), (1, True))
        self.assertEqual(final['replay_instability'], {'max_speed_m_s': 21.4})

    def test_task_failure_stays_the_agents(self):
        final = self.merge({'success': False, 'infra_error': 0, 'reason': 'Cloth fell below the table'},
                           'Cloth fell below the table')
        self.assertEqual(final['infra_error'], 0)
        self.assertNotIn('simulator_instability', final)

    def test_service_marks_the_reason_infrastructure(self):
        tree = ast.parse((SIM / 'server.py').read_text())
        nodes = [n for n in tree.body if (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') == 'INFRA_REASONS' for t in n.targets))
                 or (isinstance(n, ast.FunctionDef) and n.name == 'instability_fields')]
        review, forcing = {'pending': True, 'count': 1}, {'count': 2}
        monitor = type('Monitor', (), {'review': lambda self: review, 'forcing': lambda self: forcing})()
        ns = {'E': {'reason': 'simulator_instability'},
              'S': type('S', (), {'instability': {'max_speed_m_s': 21.4}, 'monitor': monitor})()}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'server.py', 'exec'), ns)
        self.assertIn('simulator_instability', ns['INFRA_REASONS'])
        self.assertEqual(ns['instability_fields'](), {'simulator_instability': True, 'instability': {'max_speed_m_s': 21.4},
                                                      'review': None, 'forcing': None})   # before the scene is ready
        ns['E']['ready'] = True                                              # the live episode's evidence goes along
        self.assertEqual((ns['instability_fields']()['review'], ns['instability_fields']()['forcing']), (review, forcing))


if __name__ == '__main__':
    unittest.main(verbosity=2)
