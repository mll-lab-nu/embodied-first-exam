#!/usr/bin/env python3
"""Synthetic geometry/history regressions, explicitly not robot-solution proof."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.config.registry import task_definition
from topogym.assets.geometry.rope_threading import ThreadingLayout
from topogym.tasks.rope_threading.measurements import drape_measurements, rope_grips, world_ring


def fixture(variant):
    task = task_definition('rope_threading', variant)()
    task.layout = ThreadingLayout(**task.config['geometry'])
    material = np.linspace(0., 1.1, 81)
    task.centerline_map = (np.arange(81), material)
    ring = task.layout.rings()[0]
    center = np.asarray(ring['center_m'])
    points = center + np.column_stack([np.linspace(.2, .05, 81), np.zeros((81, 2))])
    world = dict(physics_step=0, sim_time_s=0.,
        fem={'rope': dict(position_m=points, velocity_m_s=np.zeros_like(points), material_s_m=material)},
        bodies={'R1': dict(position_m=[0., 0., 0.], quaternion_wxyz=[1., 0., 0., 0.])},
        ipc=dict(native_valid=True, volume_ratio={'rope': dict(minimum=1., maximum=1.)}, attachment_residual_m={}),
        assist_model='ipc_soft_band_v1', grasp={'hands': {}})
    return task, world


def cross(task, world, *, height=0.):
    center = np.asarray(task.layout.rings()[0]['center_m'])
    world['fem']['rope']['position_m'] = center + np.column_stack([
        np.linspace(.2, -.15, 81), np.zeros(81), np.full(81, height)])


def grip(world, hand, index):
    soft = world['fem']['rope']
    world['grasp']['hands'][hand] = dict(phase='holding', solved_ticks=1,
        binding=dict(hand=hand, target=['rope', index], indices=[index],
                     material_identity=hashlib.sha256(soft['material_s_m'][:, None].tobytes()).hexdigest()))


def tick(task, world, dt=.025):
    world['physics_step'] += 1
    world['sim_time_s'] += dt
    return task.update(world, dt)


def transfer(task, world):
    grip(world, 'right', 76)
    tick(task, world)
    tick(task, world)
    cross(task, world)
    grip(world, 'left', 80)
    tick(task, world)
    tick(task, world)
    world['grasp']['hands'].pop('right')
    return tick(task, world)


class DrapeTerminal(unittest.TestCase):
    def test_supported_span_needs_stability_and_rewind_discards_success(self):
        task, world = fixture('very_easy')
        task.initialize(world)
        birth = task.get_state()
        cross(task, world, height=-.0647)
        for i in range(7):
            result = tick(task, world, .1)
            self.assertEqual(result.task_success, i >= 5)
        self.assertTrue(result.metrics['draped'])
        task.set_state(birth)
        self.assertFalse(task.result.task_success)
        self.assertEqual(task.stable_time_s, 0.)

    def test_hover_wrong_side_penetration_tip_and_tangent_rejected(self):
        for case in ('hover', 'upper', 'penetration', 'tip', 'tangent'):
            with self.subTest(case=case):
                task, world = fixture('very_easy')
                cross(task, world, height={'hover': -.04, 'upper': .0647,
                    'penetration': -.07}.get(case, -.0647))
                p = world['fem']['rope']['position_m']
                center = np.asarray(task.layout.rings()[0]['center_m'])
                if case == 'tip':
                    p[:, 0] = center[0]+np.linspace(.2, -.005, 81)
                if case == 'tangent':
                    p[:, 0] = center[0]+np.abs(np.linspace(.2, -.2, 81))
                self.assertFalse(task.evaluate_state(world)[0])

    def test_rotated_translated_scene_and_missing_or_invalid_ipc(self):
        task, world = fixture('very_easy')
        cross(task, world, height=-.0647)
        turn = Rotation.from_euler('xyz', [12., -8., 39.], degrees=True)
        offset = np.array([.31, -.17, .84])
        world['fem']['rope']['position_m'] = turn.apply(world['fem']['rope']['position_m'])+offset
        world['bodies']['R1'] = dict(position_m=offset, quaternion_wxyz=turn.as_quat()[[3, 0, 1, 2]])
        self.assertTrue(task.evaluate_state(world)[0])
        world.pop('ipc')
        reached, failure, metrics = task.evaluate_state(world)
        self.assertFalse(reached)
        self.assertIsNone(failure)
        self.assertEqual(metrics['evaluation_status'], 'unavailable')
        world['ipc'] = dict(native_valid=False)
        self.assertEqual(task.evaluate_state(world)[1], 'rope_volume_invalid')

    def test_motion_resets_confirmation(self):
        task, world = fixture('very_easy')
        task.initialize(world)
        cross(task, world, height=-.0647)
        for _ in range(4):
            tick(task, world, .1)
        world['fem']['rope']['velocity_m_s'][0, 0] = .002
        self.assertEqual(tick(task, world, .1).metrics['stable_time_s'], 0.)
        world['fem']['rope']['velocity_m_s'][:] = 0.
        self.assertFalse(tick(task, world, .1).task_success)


class HandoffTerminal(unittest.TestCase):
    def test_direct_query_does_not_bypass_handoff_or_mutate_history(self):
        task, world = fixture('easier')
        task.initialize(world)
        before = task.get_state()
        cross(task, world)
        self.assertFalse(task.evaluate_state(world)[0])
        self.assertEqual(task.get_state(), before)

    def test_unassisted_grip_requires_both_real_finger_surfaces(self):
        task, world = fixture('easier')
        world['assist_model'] = 'none'
        center = world['fem']['rope']['position_m'][80].copy()
        world['fem']['rope']['position_m'][79] = center+[0., .004, 0.]
        world['fem']['rope']['position_m'][80] = center+[0., -.004, 0.]
        mesh = trimesh.creation.box(extents=(.02, .01, .02))
        fingers = {'right': [(name, mesh.vertices, mesh.faces) for name in ('a', 'b')]}
        links = {name: dict(position_m=center+[0., sign*.009, 0.], quaternion_wxyz=[1., 0., 0., 0.])
                 for name, sign in (('a', 1.), ('b', -1.))}
        world['articulations'] = {'robot': dict(links=links)}
        ring = world_ring(task.layout.rings()[0], world)
        measure = lambda: rope_grips(world, np.arange(81), fingers, ring, task.config['terminal'])
        self.assertEqual(measure()['right']['evidence'], 'bilateral_finger_surface_contact')
        links['b']['position_m'][1] -= .002
        self.assertEqual(measure(), {})

    def test_complete_transfer_stability_and_restore(self):
        task, world = fixture('easier')
        task.initialize(world)
        birth = task.get_state()
        result = transfer(task, world)
        self.assertTrue(result.metrics['bimanual_handoff_complete'])
        self.assertFalse(result.task_success)
        for _ in range(5):
            result = tick(task, world, .1)
        self.assertTrue(result.task_success)
        task.set_state(birth)
        world['physics_step'], world['sim_time_s'] = 0, 0.
        world['grasp']['hands'] = {}
        for _ in range(10):
            self.assertFalse(tick(task, world, .1).task_success)

    def test_static_crossing_one_hand_wrong_end_and_no_overlap_rejected(self):
        for case in ('static', 'one_hand', 'wrong_end', 'no_overlap', 'same_side', 'stale_feed'):
            with self.subTest(case=case):
                task, world = fixture('easier')
                task.initialize(world)
                if case != 'static':
                    grip(world, 'right', 76)
                    tick(task, world)
                    tick(task, world)
                if case == 'stale_feed':
                    world['grasp']['hands'] = {}
                    tick(task, world)
                    grip(world, 'right', 76)
                cross(task, world)
                if case not in ('static', 'one_hand'):
                    grip(world, 'left', 0 if case == 'wrong_end' else 80)
                if case == 'no_overlap':
                    world['grasp']['hands'].pop('right')
                if case == 'same_side':
                    world['fem']['rope']['position_m'][80, 0] += .3
                tick(task, world)
                tick(task, world)
                world['grasp']['hands'].pop('right', None)
                for _ in range(10):
                    self.assertFalse(tick(task, world, .1).task_success)

    def test_unthread_invalidates_handoff(self):
        task, world = fixture('easier')
        task.initialize(world)
        transfer(task, world)
        world['fem']['rope']['position_m'][:, 0] += .5
        self.assertFalse(tick(task, world).metrics['bimanual_handoff_complete'])
        cross(task, world)
        for _ in range(10):
            self.assertFalse(tick(task, world, .1).task_success)

    def test_missing_integrity_cannot_bridge_transfer_credit(self):
        task, world = fixture('easier')
        task.initialize(world)
        transfer(task, world)
        ipc = world.pop('ipc')
        result = tick(task, world)
        self.assertEqual(result.evaluation_status, 'unavailable')
        self.assertIsNone(result.metrics['handoff'])
        world['ipc'] = ipc
        for _ in range(10):
            self.assertFalse(tick(task, world, .1).task_success)

    def test_grip_evidence_is_material_specific_and_native_solved(self):
        task, world = fixture('easier')
        ring = world_ring(task.layout.rings()[0], world)
        grip(world, 'right', 80)
        measure = lambda: rope_grips(world, np.arange(81), {}, ring, task.config['terminal'])
        self.assertIn('right', measure())
        world['grasp']['hands']['right']['solved_ticks'] = 0
        self.assertEqual(measure(), {})
        world['grasp']['hands']['right']['solved_ticks'] = 1
        world['grasp']['hands']['right']['binding']['material_identity'] = 'wrong'
        self.assertEqual(measure(), {})
        grip(world, 'right', 40)
        self.assertEqual(measure(), {})

    def test_forged_or_nonfinite_restored_intervals_rejected(self):
        task, world = fixture('easier')
        task.initialize(world)
        state = task.get_state()
        for invalid in (-1., 2., float('nan')):
            corrupted = deepcopy(state)
            corrupted['task_state']['grip_started_s']['right'] = invalid
            corrupted['task_state']['grip_endpoint']['right'] = 'end'
            with self.assertRaises(ValueError):
                task.set_state(corrupted)


if __name__ == '__main__':
    unittest.main()
