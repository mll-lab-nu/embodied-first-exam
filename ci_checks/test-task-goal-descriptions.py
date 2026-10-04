#!/usr/bin/env python3
"""Public goals track selected variants/configs; these tests do not run physics."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]

from topogym.config.registry import task_definition
from topogym.tasks.goal_description import TASK_IDS, describe_goal, render_goal
from topogym_mk_task import goal_words, instruction, validate_goal_instance


class PublicGoalTests(unittest.TestCase):
    def test_all_thirty_nine_tiers_have_public_goals(self):
        for name in TASK_IDS:
            for tier in ('easy', 'medium', 'hard'):
                with self.subTest(task=name, tier=tier):
                    task = task_definition(name, tier)()
                    goal = describe_goal(task)
                    self.assertEqual(goal['variation_id'], task.variation_id)
                    self.assertEqual(goal['stable_duration_s'], task.config['stable_duration_s'])
                    self.assertGreaterEqual(len(goal['success_conditions']), 4)
                    self.assertEqual(task.public_instruction(), render_goal(goal, include_summary=True))
                    json.dumps(goal, allow_nan=False)

    def test_easy_threading_does_not_ask_for_a_missing_third_ring(self):
        easy = describe_goal(task_definition('rope_threading', 'easy')())
        hard = describe_goal(task_definition('rope_threading', 'hard')())
        self.assertIn('cyan ring (R1) then green ring (R2)', easy['summary'])
        self.assertNotIn('purple', render_goal(easy, include_summary=True))
        self.assertIn('purple ring (R3)', hard['summary'])
        self.assertIn('cyan ring (R1): cross toward the side containing the green', hard['success_conditions'][0])
        self.assertIn('green ring (R2): cross away from the side containing the cyan', easy['success_conditions'][0])
        self.assertIn('green ring (R2): cross toward the side containing the purple', hard['success_conditions'][0])
        self.assertIn('purple ring (R3): cross away from', hard['success_conditions'][0])

    def test_pose_and_appearance_randomization_do_not_leak_into_goal(self):
        from topogym.tasks.scene_variation import draw
        for name in TASK_IDS - {'fiber_bundling'}:
            cls = task_definition(name, 'medium')
            a, b = cls(seed=7), cls(draw(cls, 7), seed=7)
            self.assertEqual(render_goal(describe_goal(a)), render_goal(describe_goal(b)), name)

    def test_actual_config_thresholds_are_used(self):
        fiber = task_definition('fiber_bundling', 'easy')({'terminal': {'maximum_bend_deg': 47.}})
        self.assertIn('47 degrees', fiber.public_instruction())
        blanket = task_definition('blanket_flatten', 'easy')({
            'minimum_coverage_ratio': .93, 'maximum_drift_m': .0025, 'stable_duration_s': .75})
        text = blanket.public_instruction()
        for value in ('93%', '2.5 mm', '0.75 s'):
            self.assertIn(value, text)

    def test_lock_and_holding_tasks_have_no_invented_release_rule(self):
        task = task_definition('lock_picking', 'medium')()
        text = task.public_instruction()
        self.assertIn('all four plates', text)
        self.assertIn('0.01 mm', text)
        self.assertIn('Release and zero velocity are not required', text)
        self.assertNotIn('1 degree', text)
        for name in ('interlocked_claws', 'hedgehog_in_cage', 'horseshoe_ring', 'cast_keyhole', 'slotted_post_ring', 'orbits'):
            self.assertIn('release is not required', task_definition(name, 'easy')().public_instruction())

    def test_release_requirements_include_shared_settling(self):
        for name in ('knot_untying', 'cast_coil', 'buzz_wire_3d', 'blanket_flatten'):
            text = task_definition(name, 'medium')().public_instruction()
            self.assertIn(('1' if name == 'knot_untying' else '5')+' mm of verified clearance', text)
            if name == 'knot_untying':
                self.assertIn('World-fixed bases may touch', text)
            self.assertIn('displacement from the start of confirmation', text)

    def test_generator_refuses_stale_or_mismatched_describe(self):
        d = json.loads((ROOT/'ci_checks/fixtures/difficulty_eval_describe.json').read_text())
        d.pop('public_goal', None)
        with self.assertRaisesRegex(ValueError, 'lacks public_goal'):
            goal_words('cast_coil', 'old prose', d)
        d['public_goal'] = describe_goal(task_definition('rope_threading', 'easy')())
        with self.assertRaisesRegex(ValueError, 'differs'):
            goal_words('cast_coil', 'old prose', d)

    def test_unlimited_uses_complete_public_goal_not_family_fallback(self):
        d = json.loads((ROOT/'ci_checks/fixtures/difficulty_eval_describe.json').read_text())
        d['public_goal'] = describe_goal(task_definition('rope_threading', 'easy')())
        text = instruction('rope_threading', 'stale purple-ring family text', d)
        self.assertNotIn('stale purple', text)
        self.assertIn(render_goal(d['public_goal']), text)
        self.assertIn('partial implementation excerpt', text)

    def test_reused_description_cannot_cross_variations_or_seeds(self):
        d = dict(stable_duration_s=.5, public_goal=describe_goal(task_definition('rope_threading', 'easy')(seed=3)))
        instance = dict(variation_id='seeded', resolved_variation_id='rope_threading_easy', seed=3)
        validate_goal_instance('rope_threading', d, instance)
        for bad in (dict(instance, seed=4), dict(instance, resolved_variation_id='rope_threading_hard')):
            with self.assertRaisesRegex(ValueError, 'different variation/seed'):
                validate_goal_instance('rope_threading', d, bad)
        with self.assertRaisesRegex(ValueError, 'requirements differ'):
            validate_goal_instance('rope_threading', d, dict(instance, public_goal=dict(d['public_goal'], terminal_revision='stale-config')))
        validate_goal_instance('rope_threading', d, dict(instance, public_goal=d['public_goal']))

    def test_checked_in_twins_include_the_same_complete_requirements(self):
        for name in TASK_IDS:
            folder = ROOT/'tasks'/f'topogym-{name.replace("_", "-")}-i00'
            instance = json.loads((folder/'environment/instance.json').read_text())
            cfg = instance['simulator']
            task = task_definition(name, cfg['variation_id'], cfg['seed'])(cfg.get('task_parameters', {}), seed=cfg['seed'])
            requirements = render_goal(describe_goal(task))
            if name == 'knot_untying' and 'public_goal' not in instance:
                # These untiered i00 packages predate public_goal metadata and
                # remain frozen on their original image/release contract. A
                # local v5 oracle result must not relabel their v4 text.
                from topogym.evaluation.terminal import SettlingSpec
                with patch.object(task, 'final_settling_spec', return_value=SettlingSpec(fem_targets=('rope',),
                        maximum_speed_m_s=task.config['terminal']['maximum_speed_m_s'])):
                    requirements = render_goal(describe_goal(task))
            for target in (folder, folder.with_name(folder.name+'-limited')):
                with self.subTest(task=name, mode=target.name):
                    self.assertIn(requirements, (target/'instruction.md').read_text())
                    self.assertIn(requirements, (target/'README.md').read_text())


if __name__ == '__main__':
    unittest.main()
