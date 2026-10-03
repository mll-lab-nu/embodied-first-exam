#!/usr/bin/env python3
"""Low-tier geometry, reference and terminal regressions; no physics claims."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.config.registry import task_definition, variation_registration, seeded_variation
from topogym.config.scene import load_scene_config
from topogym.simulator import SimulatorConfig
from topogym.assets.geometry.claws_simplified import SimplifiedClawModel
from topogym.assets.geometry.interlocked_claws import load_reference, tcp_frames
from topogym.tasks.interlocked_claws.common import InterlockedClawsTask, recommended_grasp_assist
from topogym.planning.interlocked_claws.simplified_routes import reference, world_route, read_reference_route
from topogym.planning.interlocked_claws.simplified_policy import SimplifiedClawsPolicy
from topogym.planning.rigid_reference.feedback import body_pose


class ClawsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.scenes = {}
        for tier in ('very_easy', 'easier'):
            task = task_definition('interlocked_claws', tier)()
            cfg = load_scene_config(SimulatorConfig(task_id='interlocked_claws', variation_id=tier))
            root = Path(cls.temp.name)/tier
            table = cfg.env.world.table
            spec = task.declare(root, float(table.pos[2]+table.size[2]/2))
            spec = task.finalize_spec(spec, asset_dir=root, scene_config=cfg)
            cls.scenes[tier] = task, spec

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_names_do_not_change_legacy_seed_pool(self):
        self.assertEqual(variation_registration('interlocked_claws')['variation_id'], 'interlocked_claws_hard')
        for i in range(9):
            self.assertEqual(seeded_variation('interlocked_claws', i)['difficulty'], ('easy','medium','hard')[i%3])
        for tier,(task,_) in self.scenes.items():
            row = variation_registration('interlocked_claws', tier)
            self.assertEqual(row['pool'], 'experimental')
            self.assertEqual(row['model_revision'], task.model_revision)
            self.assertIs(task_definition('interlocked_claws', task.variation_id), type(task))

    def test_approved_l_short_legs_are_perpendicular(self):
        model = SimplifiedClawModel('shallow_l_hooks', InterlockedClawsTask.opposed_q(.13,.30528805,.0222))
        a,b = [p.boxes[1] for p in model.parts]
        axes = [np.asarray(x['pose'])[:3,np.argmax(x['size'])] for x in (a,b)]
        self.assertAlmostEqual(float(np.dot(*axes)), 0.)
        self.assertGreater(np.asarray(a['pose'])[0,3], np.asarray(b['pose'])[0,3])
        self.assertGreater(model.audit['initial_surface_gap_m'], .0039)
        self.assertLessEqual(model.audit['axial_pull_collision_witness_m'], .0051)

    def test_cross_is_xyz_and_frame_has_an_outside_elbow(self):
        model = SimplifiedClawModel('cross_square_offset', InterlockedClawsTask.opposed_q(.13,.30528805,.0222))
        cross,frame = model.parts
        axes = [int(np.argmax(x['size'])) for x in cross.boxes[:3]]
        self.assertEqual(axes,[0,1,2])
        self.assertEqual(int(np.argmax(frame.boxes[4]['size'])),1)
        self.assertEqual(int(np.argmax(frame.boxes[5]['size'])),0)
        self.assertGreater(np.asarray(frame.boxes[5]['pose'])[1,3],.132/2)
        # Even the optimal in-plane yaw cannot fit the complete cross in the
        # aperture; the candidate actually needs out-of-plane manipulation.
        self.assertGreater((.120+.014)/np.sqrt(2), .088)

    def test_solids_primitive_collisions_and_ik(self):
        for task,spec in self.scenes.values():
            report = spec.metadata['asset_report']
            self.assertFalse(report['initial_surface_collision'])
            self.assertLess(report['tcp_position_error_m'],1e-7)
            for part in report['parts']:
                self.assertTrue(part['watertight'])
                self.assertEqual(part['components'],1)
                self.assertGreater(np.linalg.eigvalsh(part['inertia']).min(),0)
            self.assertEqual([e.fixed for e in spec.entities[:2]],[False,False])

    def test_both_grasps_are_on_distinct_matching_pads(self):
        for tier,(task,_) in self.scenes.items():
            targets = recommended_grasp_assist(tier).targets
            self.assertEqual({x.entity for x in targets},{'piece_0','piece_1'})
            report = task.build_assets(Path(self.temp.name)/(tier+'_grasp'))[1]
            for target in targets:
                part = next(p for p in report['parts'] if p['name']==target.entity)
                pad = np.asarray(part['boxes'][-1]['pose'])[:3,3]
                np.testing.assert_allclose(target.center_m,pad,atol=1e-8)

    def test_continuous_exit_routes_and_blocked_pull(self):
        for tier in self.scenes:
            _,_,checker,motions,audit = reference(tier)
            self.assertTrue(all(e['passed'] for e in audit['edges']))
            self.assertGreater(min(e['clearance_lower_bound_m'] for e in audit['edges']),.0015)
            self.assertFalse(audit['straight_pull']['passed'])
            self.assertGreater(checker.clearance(motions[-1].end),.02)

    def test_easier_route_rejects_stale_model(self):
        record = read_reference_route()
        record['model_revision'] = 'stale'
        with patch('topogym.planning.interlocked_claws.simplified_routes.read_reference_route',return_value=record):
            with self.assertRaisesRegex(ValueError,'model revision'): reference('easier')

    def test_initial_and_just_separated_are_not_terminal(self):
        for tier,(task,spec) in self.scenes.items():
            bodies = {e.name:dict(position_m=list(e.position_m),quaternion_wxyz=e.quaternion_wxyz,
                linear_velocity_m_s=[0.,0.,0.],angular_velocity_rad_s=[0.,0.,0.]) for e in spec.entities[:2]}
            self.assertFalse(task.evaluate_goal_region({'bodies':bodies},task.goal_region)[0])
            bodies['piece_0']['position_m'][0]-=.10
            self.assertFalse(task.evaluate_goal_region({'bodies':bodies},task.goal_region)[0])

    def test_goal_transfer_and_partial_fast_or_wrong_side_rejection(self):
        for tier,(task,spec) in self.scenes.items():
            bodies = {e.name:dict(position_m=list(e.position_m),quaternion_wxyz=e.quaternion_wxyz,
                linear_velocity_m_s=[0.,0.,0.],angular_velocity_rad_s=[0.,0.,0.]) for e in spec.entities[:2]}
            initial = {s:body_pose(bodies[n]) for s,n in (('left','piece_0'),('right','piece_1'))}
            route,audit = world_route(tier,initial,asdict(task.goal_region))
            self.assertTrue(audit['goal_transfer']['passed'])
            p,r = route[-1].end
            bodies['piece_0'].update(position_m=p.tolist(),quaternion_wxyz=r.as_quat()[[3,0,1,2]].tolist())
            self.assertTrue(task.evaluate_goal_region({'bodies':bodies},task.goal_region)[0])
            for scenario in ('fast','partial','wrong_side'):
                bad = deepcopy(bodies)
                if scenario=='fast':bad['piece_0']['linear_velocity_m_s']=[.01,0,0]
                elif scenario=='partial':bad['piece_0']['position_m'][1]+=.12
                else:bad['piece_1']['position_m'][1]+=.20
                self.assertFalse(task.evaluate_goal_region({'bodies':bad},task.goal_region)[0],scenario)

    def test_policy_rejects_lost_grasp(self):
        policy = SimplifiedClawsPolicy()
        policy.program = iter(())
        with self.assertRaisesRegex(RuntimeError,'Lost acquired grasp'):
            policy.act(dict(privileged=dict(world=dict(grasp=dict(hands={s:dict(phase='open') for s in ('left','right')})))))


if __name__=='__main__':unittest.main()
