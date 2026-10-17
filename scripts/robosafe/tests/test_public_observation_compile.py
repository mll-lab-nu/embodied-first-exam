"""Portable public-RT compile tests using authored native1e763 metadata fields.

No native module is imported: only CONTROL_DT and DELTA_DT are stubbed for the
existing converter. No teacher, simulation, rendered image or model is run.
The metadata is synthetic but follows verify.compile._PublicObservationMap's
actual schema, including per-play basis, kept count and absolute call index.
Install under scripts/robosafe/tests or set ROBOSAFE_COMPILE_TEST_SOURCE.
"""
import copy
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

SOURCE = Path(os.environ.get('ROBOSAFE_COMPILE_TEST_SOURCE', Path(__file__).resolve().parents[1]))


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


O = load_module('rsb_compile_tests_observation_plan',SOURCE/'public_observation_plan.py')
M = load_module('rsb_compile_tests_make_instances',SOURCE/'make_instances.py')
CAMERAS = ['front','top','wrist']
KEY = {'family':'synthetic_compile_scope','member':'hazard','robot':'ur5e_2f85',
       'seed':0,'interface':'control'}


def call(tool, **args):
    return {'tool':tool,'args':args,'ok':True}


def act(rows, **extra):
    return call('act',type='joint_position',rows=copy.deepcopy(rows),dt=0.02,images=False,**extra)


def boundary(index, offset, *, end=None, kept=0, kind='skill_look_end', skill=2,
             position='within_act_rows', oracle=0, start=0):
    # Real1e763 maps an oracle-local row end to an absolute original call/offset.
    return {'skill_call_index':skill,'skill_tool':'observe' if kind=='skill_observe' else 'look',
            'compiled_row_end':offset if end is None else end,'preceding_kept_segments':kept,
            'kind':kind,'opportunity_only':True,'oracle_index':oracle,
            'play_record_call_start_index':start,'record_call_index':index,
            'row_offset':offset,'position':position}


def envelope(boundaries, starts=(0,)):
    oracles = []
    for index,start in enumerate(starts):
        count = sum(b['oracle_index']==index for b in boundaries)
        oracles.append({'oracle_index':index,'complete':True,'record_call_start_index':start,
                        'expected_boundaries':count,'mapped_boundaries':count})
    return {'schema':O.NATIVE_SCHEMA,'complete':True,'boundaries':copy.deepcopy(boundaries),'oracles':oracles}


def record(calls, boundaries=(), *, starts=(0,), mapping=True):
    result = {'instance':copy.deepcopy(KEY),'calls':copy.deepcopy(calls)}
    if mapping:
        result['strategy_info'] = {'public_observation_boundaries':envelope(list(boundaries),starts)}
    return result


class PublicObservationCompileTests(unittest.TestCase):
    def setUp(self):
        world = types.ModuleType('robosafebench.sim.world');world.CONTROL_DT = 0.02
        control = types.ModuleType('robosafebench.episode.control');control.DELTA_DT = 0.1
        native_constants = patch.dict(sys.modules,{'robosafebench.sim.world':world,
                                                  'robosafebench.episode.control':control})
        native_constants.start();self.addCleanup(native_constants.stop)
        public_plan = patch.dict(sys.modules,{'public_observation_plan':O})
        public_plan.start();self.addCleanup(public_plan.stop)
        # Nontrivial values, including signed zero, expose accidental row rewriting.
        self.rows = [[-0.0,0.125],[0.25,-0.75],[0.5,0.875],[-0.125,0.0],[0.625,1.0],[-1.0,0.375]]

    def compile(self, rec):
        return M.compile_public_rt_record(KEY,rec,CAMERAS)

    def preserved(self, rec):
        return M.compile_record(KEY,rec,preserve_call_boundaries=True)

    def test_explicit_observe_prevents_cross_call_merge_only_in_public_rt_plan(self):
        rec = record([act(self.rows[:2]),call('observe',cameras=['front']),act(self.rows[2:]),
                      call('end',reason='done')])
        before = copy.deepcopy(rec)
        old, old_arrays, old_facts = M.compile_record(KEY,rec)
        raw, arrays, facts = self.preserved(rec)
        self.assertEqual(old,[{'type':'joint_position','rows':[0,6]},
                              {'type':'done','row':[],'text':''}])
        self.assertEqual([it['_source_call'] for it in raw],[0,1,2,3])
        self.assertEqual([it['type'] for it in raw],['joint_position','observe','joint_position','done'])
        doc, public_arrays, public_facts = self.compile(rec)
        self.assertEqual([it['type'] for it in doc['plan']],
                         ['joint_position','observe','joint_position','done'])
        self.assertEqual(doc['plan'][1]['boundary']['source'],'native_record_observe')
        for current in (arrays,public_arrays):
            self.assertEqual(current['joint_position'].dtype,np.float64)
            self.assertEqual(current['joint_position'].tobytes(),old_arrays['joint_position'].tobytes())
        self.assertEqual(public_facts,facts)
        self.assertEqual(facts,old_facts)
        self.assertEqual(rec,before)

    def test_authored_interior_look_hold_and_look_end_split_plan_without_touching_arrays(self):
        rec = record([act(self.rows),call('end',reason='decline',text='Stopped')],
                     [boundary(0,2,kind='compiled_look_hold'),boundary(0,4)])
        doc, arrays, facts = self.compile(rec)
        old, old_arrays, old_facts = M.compile_record(KEY,rec)
        self.assertEqual([it['rows'] for it in doc['plan'] if 'rows' in it],[[0,2],[2,4],[4,6]])
        snapshots = [it for it in doc['plan'] if it['type']=='observe']
        self.assertEqual([it['boundary']['row_offset'] for it in snapshots],[2,4])
        self.assertEqual([it['boundary']['kind'] for it in snapshots],['compiled_look_hold','skill_look_end'])
        self.assertTrue(all(it['camera_batches']==[['front','top'],['wrist']] for it in snapshots))
        self.assertEqual(arrays['joint_position'].tobytes(),old_arrays['joint_position'].tobytes())
        self.assertEqual(facts,old_facts)
        self.assertEqual(old[0]['rows'],[0,6])
        self.assertEqual(doc['source_record_canonical_sha256'],O.canonical(rec))

    def test_initial_minus_one_is_an_authored_opportunity_not_an_automatic_picture(self):
        initial = boundary(-1,0,end=0,kind='skill_observe',position='before_first_call')
        rec = record([act(self.rows),call('end',reason='done')],[initial])
        doc, _, _ = self.compile(rec)
        self.assertFalse(doc['observation_policy']['initial_observe'])
        self.assertEqual(doc['plan'][0]['type'],'observe')
        self.assertEqual(doc['plan'][0]['boundary']['record_call_index'],-1)
        self.assertEqual(sum(it['type']=='observe' for it in doc['plan']),1)
        without, _, _ = self.compile(record(rec['calls']))
        self.assertFalse(any(it['type']=='observe' for it in without['plan']))

    def test_after_call_zero_offset_stays_after_report_and_cannot_move_to_start(self):
        event = boundary(0,0,end=0,kept=1,kind='skill_observe',position='after_call')
        rec = record([call('report',category='note',text='Ready'),act(self.rows),
                      call('end',reason='done')],[event])
        doc, _, _ = self.compile(rec)
        self.assertEqual([it['type'] for it in doc['plan']],['report','observe','joint_position','done'])
        self.assertEqual(doc['plan'][1]['boundary']['row_offset'],0)
        self.assertEqual(doc['plan'][1]['boundary']['position'],'after_call')
        moved = copy.deepcopy(rec)
        moved['strategy_info']['public_observation_boundaries']['boundaries'][0].update(
            record_call_index=-1,position='before_first_call')
        with self.assertRaisesRegex(ValueError,'initial opportunity basis'): self.compile(moved)

    def test_multiple_oracles_use_local_row_kept_basis_with_absolute_original_calls(self):
        rec = record([act(self.rows[:3]),call('report',category='note',text='First play complete'),
                      act(self.rows[3:]),call('end',reason='done')],
                     [boundary(0,2),boundary(2,2,end=2,oracle=1,start=2)],starts=(0,2))
        doc, arrays, _ = self.compile(rec)
        self.assertEqual([it['rows'] for it in doc['plan'] if 'rows' in it],[[0,2],[2,3],[3,5],[5,6]])
        snapshots = [it['boundary'] for it in doc['plan'] if it['type']=='observe']
        self.assertEqual([(b['oracle_index'],b['record_call_index'],b['play_record_call_start_index'])
                          for b in snapshots],[(0,0,0),(1,2,2)])
        self.assertEqual(snapshots[1]['compiled_row_end'],2)
        self.assertEqual(arrays['joint_position'].tobytes(),np.asarray(self.rows,dtype=np.float64).tobytes())
        invalid = copy.deepcopy(rec)
        invalid['strategy_info']['public_observation_boundaries']['boundaries'][1]['play_record_call_start_index'] = 0
        with self.assertRaisesRegex(ValueError,'play basis'): self.compile(invalid)

    def test_no_mapping_is_invented_from_evidence_ticks_or_success_verdict(self):
        rec = record([act(self.rows),call('end',reason='done')],mapping=False)
        rec.update(evidence_seen={'tick':3,'call':0},verdict={'pass':True},final_hash='a'*64)
        with self.assertRaisesRegex(ValueError,'complete native boundary mapping'): self.compile(rec)

    def test_duplicate_opportunity_is_hold_even_if_native_declared_counts_are_adjusted(self):
        event = boundary(0,2)
        rec = record([act(self.rows),call('end',reason='done')],[event,event])
        with self.assertRaisesRegex(ValueError,'duplicate'): self.compile(rec)

    def test_missing_duplicated_or_reordered_original_call_is_hold(self):
        rec = record([act(self.rows[:2]),call('observe'),act(self.rows[2:]),call('end',reason='done')])
        plan, _, _ = self.preserved(rec)
        variants = [plan[:1]+plan[2:],plan[:1]+plan, list(reversed(plan))]
        for changed in variants:
            with self.subTest(plan=changed), self.assertRaisesRegex(ValueError,'every original'):
                O.build(rec,changed,CAMERAS)

    def test_overlapping_repeated_or_gapped_converted_row_span_is_hold(self):
        rec = record([act(self.rows[:2]),act(self.rows[2:]),call('end',reason='done')])
        original, _, _ = self.preserved(rec)
        for span in ([1,5],[0,4],[3,7]):
            changed = copy.deepcopy(original);changed[1]['rows'] = span
            with self.subTest(span=span), self.assertRaisesRegex(ValueError,'motion rows'):
                O.build(rec,changed,CAMERAS)

    def test_offset_outside_original_act_rows_is_hold(self):
        for offset in (0,7):
            rec = record([act(self.rows),call('end',reason='done')],[boundary(0,offset)])
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError,'original fixed-arm act rows'):
                self.compile(rec)

    def test_compiled_row_end_and_preceding_kept_count_must_match_original_calls(self):
        base = record([call('report',category='note',text='Ready'),act(self.rows),call('end',reason='done')],
                      [boundary(1,2,end=2,kept=1)])
        for field,value in (('compiled_row_end',3),('preceding_kept_segments',0)):
            rec = copy.deepcopy(base)
            rec['strategy_info']['public_observation_boundaries']['boundaries'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'row/kept position'):
                self.compile(rec)

    def test_oracle_expected_mapped_boundary_count_mismatch_is_hold(self):
        base = record([act(self.rows),call('end',reason='done')],[boundary(0,2)])
        for field,value in (('expected_boundaries',2),('mapped_boundaries',0)):
            rec = copy.deepcopy(base)
            rec['strategy_info']['public_observation_boundaries']['oracles'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'mapped opportunity count'):
                self.compile(rec)

    def test_motion_requires_complete_mapping_and_nonempty_oracle_basis(self):
        base = record([act(self.rows),call('end',reason='done')],[boundary(0,2)])
        for variant in ('missing','incomplete','empty_oracles','incomplete_oracle'):
            rec = copy.deepcopy(base)
            info = rec['strategy_info']['public_observation_boundaries']
            if variant=='missing': del rec['strategy_info']['public_observation_boundaries']
            elif variant=='incomplete': info['complete'] = False
            elif variant=='empty_oracles': info['oracles'] = []
            else: info['oracles'][0]['complete'] = False
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError,'mapping|oracles'):
                self.compile(rec)

    def test_live_realtime_or_retried_source_is_not_flattened_as_paired_paused(self):
        rec = record([act(self.rows),call('end',reason='done')],[boundary(0,2)])
        rec['instance']['clock'] = 'realtime'
        with self.assertRaisesRegex(ValueError,'accepted paired paused source'): self.compile(rec)

    def test_queued_current_act_is_not_accepted_as_paused_original_provenance(self):
        rec = record([act(self.rows,at=100),call('end',reason='done')],[boundary(0,2)])
        with self.assertRaisesRegex(ValueError,'queued native schedules'): self.compile(rec)

    def test_queued_prior_act_is_not_accepted_as_paused_original_provenance(self):
        rec = record([act(self.rows[:2],at=100),act(self.rows[2:]),call('end',reason='done')],
                     [boundary(1,2,end=4)])
        with self.assertRaisesRegex(ValueError,'queued native schedules'): self.compile(rec)

    def test_original_source_call_index_and_refused_anchor_are_not_guessed(self):
        base = record([act(self.rows),call('end',reason='done')],[boundary(0,2)])
        rec = copy.deepcopy(base)
        rec['strategy_info']['public_observation_boundaries']['boundaries'][0]['record_call_index'] = 3
        with self.assertRaisesRegex(ValueError,'anchor outside'): self.compile(rec)
        rec = copy.deepcopy(base);rec['calls'][0]['ok'] = False
        with self.assertRaises(RuntimeError): self.compile(rec)

    def test_delta_and_non_fixed_arm_rows_are_explicitly_held(self):
        for calls in ([call('delta',row=[0.0,0.0,1.0])],
                      [call('act',type='whole_body',rows=[[0.0]*8],dt=0.02)]):
            with self.subTest(calls=calls), self.assertRaisesRegex(ValueError,'only fixed-arm'):
                self.compile(record(calls))

    def test_multiple_authored_initial_opportunities_stay_in_prefix(self):
        first=boundary(-1,0,end=0,kind='skill_observe',position='before_first_call',skill=0)
        second=boundary(-1,0,end=0,kind='skill_observe',position='before_first_call',skill=1)
        rec=record([act(self.rows),call('end',reason='done')],[first,second])
        document,_,_=self.compile(rec)
        self.assertEqual([item['type'] for item in document['plan'][:3]],['observe','observe','joint_position'])
        tampered=copy.deepcopy(document)
        tampered['plan'][1],tampered['plan'][2]=tampered['plan'][2],tampered['plan'][1]
        with self.assertRaisesRegex(ValueError,'must precede'):O.validate(tampered,CAMERAS)

    def test_empty_nop_remains_literal_empty_with_no_authored_or_automatic_observe(self):
        rec = record([],mapping=False)
        old, old_arrays, old_facts = M.compile_record(KEY,rec,'nop')
        doc, arrays, facts = M.compile_public_rt_record(KEY,rec,CAMERAS,'nop')
        self.assertEqual(old,[])
        self.assertEqual(doc['plan'],[])
        self.assertEqual(arrays,old_arrays)
        self.assertEqual(arrays,{})
        self.assertEqual(facts,old_facts)
        self.assertFalse(doc['observation_policy']['initial_observe'])


if __name__ == '__main__':
    unittest.main()
