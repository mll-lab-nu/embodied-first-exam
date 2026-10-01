#!/usr/bin/env python3
"""Authored geometry and trials configuration checks; no physics qualification."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts'), str(ROOT/'harbor_templates/topogym/common')]
import rcb_topogym
from topogym.config.registry import task_definition
from topogym.evaluation.task_metrics import rigid_asset_vertices
from topogym.simulator.config import SimulatorConfig
from topogym.tasks.scene_variation import draw
from topogym.tasks.goal_description import describe_goal
from topogym_mk_task import validate_goal_instance

NEW_TASKS = ('buzz_wire_3d', 'cast_coil', 'cast_keyhole', 'hedgehog_in_cage', 'horseshoe_ring')
TARGETS = {
    'buzz_wire_3d': {('wand', 'wand')},
    'cast_coil': {('coil_gold', 'coil_gold'), ('coil_silver', 'coil_silver')},
    'cast_keyhole': {('keyhole_gold', 'keyhole_gold'), ('keyhole_silver', 'keyhole_silver')},
    'hedgehog_in_cage': {('hedgehog_ball', 'hedgehog')},
    'horseshoe_ring': {(name, name) for name in ('horseshoe_left', 'horseshoe_right', 'target_ring')},
}


class TrialAssistTests(unittest.TestCase):
    def test_regions_match_actual_authored_links_in_every_tier(self):
        for name in NEW_TASKS:
            for tier in ('easy', 'medium', 'hard'):
                with self.subTest(task=name, tier=tier), tempfile.TemporaryDirectory() as folder:
                    task = task_definition(name, tier)(seed=0)
                    spec = task.declare(Path(folder), .75)
                    cfg = SimulatorConfig(**rcb_topogym.simulator_config(name, variation_id=tier, seed=0))
                    assist = cfg.grasp_assist
                    self.assertEqual(assist.model, 'contact_weld_v1')
                    self.assertEqual({t.key for t in assist.targets}, TARGETS[name])
                    entities = {e.name: e for e in spec.entities}
                    self.assertNotIn('ipc', spec.physics_options)
                    for target in assist.targets:
                        entity = entities[target.entity]
                        self.assertFalse(entity.fixed)
                        links = {e.get('name') for e in ET.parse(entity.asset_path).getroot().findall('link')}
                        self.assertIn(target.link, links)
                        vertices = rigid_asset_vertices(entity)
                        distance = np.linalg.norm(vertices-np.asarray(target.center_m), axis=1)
                        self.assertLess(distance.min(), target.radius_m)
                        if name in ('hedgehog_in_cage', 'horseshoe_ring'):
                            self.assertLessEqual(distance.max(), target.radius_m)
                            self.assertGreaterEqual(assist.max_tcp_distance_m, target.radius_m+.029)
                    # Compare against independent existing policy frame definitions.
                    actual = {t.entity: np.asarray(t.center_m) for t in assist.targets}
                    if name == 'cast_coil':
                        from topogym.planning.cast_coil.baseline import GRASP_POINTS, PARTS
                        for hand, part in PARTS.items():
                            np.testing.assert_allclose(actual[part], GRASP_POINTS[hand]-task.body_origins[part], atol=1e-12)
                    if name == 'cast_keyhole':
                        from topogym.planning.cast_keyhole.policy import (
                            GRASP_POINTS, REGRASP_POINTS, PARTS, ASSEMBLY_ROTATIONS, canonical_offsets)
                        origins = {b['name']: np.asarray(b['origin_m']) for b in spec.metadata['asset_report']['bodies']}
                        offsets = canonical_offsets(origins)
                        for hand, part in PARTS.items():
                            expected = ASSEMBLY_ROTATIONS[hand].apply((GRASP_POINTS[hand]+REGRASP_POINTS[hand])/2-offsets[hand])
                            np.testing.assert_allclose(actual[part], expected, atol=1e-12)

    def test_seeded_pose_draw_preserves_local_regions(self):
        for name in NEW_TASKS:
            for seed in (0, 1, 2):
                with self.subTest(task=name, seed=seed):
                    cls = task_definition(name, 'seeded', seed)
                    nominal = rcb_topogym.simulator_config(name, variation_id=cls.variation_id, seed=seed)
                    random = rcb_topogym.simulator_config(name, variation_id='seeded', seed=seed,
                                                        task_parameters=draw(cls, seed))
                    self.assertEqual(random['grasp_assist'], nominal['grasp_assist'])

    def test_stale_description_cannot_publish_wrong_grasp_rules(self):
        name = 'cast_coil'
        task = task_definition(name, 'easy')()
        cfg = rcb_topogym.simulator_config(name, variation_id='easy', seed=0)
        instance = dict(variation_id=task.variation_id, seed=0, simulator=cfg)
        d = dict(public_goal=describe_goal(task), stable_duration_s=task.config['stable_duration_s'],
                 grasp_assist=cfg['grasp_assist'])
        validate_goal_instance(name, d, instance)
        for stale in (None, {'model': 'none'}):
            with self.subTest(stale=stale), self.assertRaisesRegex(ValueError, 'Grasp assistance differs'):
                validate_goal_instance(name, dict(d, grasp_assist=stale), instance)
        changed = deepcopy(d)
        changed['grasp_assist']['targets'][0]['radius_m'] *= .5
        with self.assertRaisesRegex(ValueError, 'Grasp assistance differs'):
            validate_goal_instance(name, changed, instance)

    def test_public_rules_describe_passive_contact_and_release(self):
        for name in (*NEW_TASKS, 'lock_picking', 'interlocked_claws'):
            cfg = SimulatorConfig(**rcb_topogym.simulator_config(name, 0))
            session = SimpleNamespace(env=SimpleNamespace(config=cfg))
            words = rcb_topogym.Session.grasp_rules(session)
            self.assertIn('assisted grasping (contact_weld_v1)', words)
            self.assertIn('both fingers touch the same part', words)
            self.assertIn('lets it go', words)
            for target in cfg.grasp_assist.targets:
                self.assertIn(target.entity, words)
            self.assertNotIn('already hold them from the first tick', words)


if __name__ == '__main__':
    unittest.main()
