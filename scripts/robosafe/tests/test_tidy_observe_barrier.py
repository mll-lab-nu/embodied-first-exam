"""Pure conversion contracts for the two selected authored Tidy observes.

No native module/teacher/simulator is imported or run. All rows are synthetic;
explicit time constants keep the converter on its pure NumPy path.
"""
import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import make_instances as M
import validation_coverage as V


def call(tool,**args):
    return {'tool':tool,'args':args,'ok':True}


def key(member='hazard'):
    return {'family':'f_room_person_down','robot':'tidybot','member':member,'seed':0,
            'interface':'control','clock':'paused','cameras':'onboard','evidence':None,'variant':None}


def convert(scope,record,strategy='reference',**kwargs):
    return M.compile_record(scope,record,strategy,control_dt=.02,delta_dt=.1,**kwargs)


class TidyObserveBarrier(unittest.TestCase):
    def test_both_selected_members_keep_prefix_observe_dock_segments_and_exact_row_bytes(self):
        rows=np.asarray([[.1,0.,1.],[.2,.1,1.],[.3,.2,1.],[.4,.3,0.],[.5,.4,0.],[.6,.5,1.]],dtype=np.float64)
        record={'calls':[call('delta',row=rows[0].tolist()),
            call('act',type='delta',rows=rows[1:3].tolist(),dt=.1),call('observe',images=True),
            call('act',type='delta',rows=rows[3:5].tolist(),dt=.1),
            call('delta',row=rows[5].tolist()),call('end',reason='done',text='Docked safely.') ]}
        for member in ('hazard','benign'):
            with self.subTest(member=member):
                scope=key(member);before=copy.deepcopy(record)
                legacy,legacy_arrays,legacy_facts=convert(scope,record)
                plan,arrays,facts=convert(scope,record,preserve_tidy_observe_boundaries=True)
                self.assertEqual(record,before)
                self.assertIsNotNone(V.tidy_policy(scope))
                self.assertEqual(legacy,[{'type':'delta','rows':[0,6]},
                    {'type':'done','row':[],'text':'Docked safely.'}])
                self.assertEqual(plan,[{'type':'delta','rows':[0,3]},{'type':'delta','rows':[3,6]},
                    {'type':'done','row':[],'text':'Docked safely.'}])
                self.assertEqual(arrays['delta'].dtype,np.dtype(np.float64))
                self.assertEqual(arrays['delta'].tobytes(),rows.tobytes())
                self.assertEqual(arrays['delta'].tobytes(),legacy_arrays['delta'].tobytes())
                self.assertFalse(any(item['type']=='observe' for item in plan))
                self.assertEqual(facts['public_observe_barriers'],[
                    {'record_call_index':2,'row_offsets':{'delta':3}}])
                self.assertEqual({name:value for name,value in facts.items() if name not in ('public_observe_barriers','reference_observation_policy')},legacy_facts)
                self.assertNotIn('public_observe_barriers',legacy_facts)
                self.assertNotIn('reference_observation_policy',legacy_facts)
                self.assertEqual(facts['reference_observation_policy'],V.tidy_policy(scope))

    def test_reports_survive_and_offsets_count_raw_delta_plus_actual_act_lengths(self):
        rows=np.arange(30,dtype=np.float64).reshape(10,3)/10
        text='Hazard report: person still down; retain this exact text.'
        record={'calls':[call('delta',row=rows[0].tolist()),call('observe',images=True),
            call('act',type='delta',rows=rows[1:5].tolist(),dt=.1),
            call('report',category='hazard',text=text),call('delta',row=rows[5].tolist()),
            call('observe',images=True),call('act',type='delta',rows=rows[6:9].tolist(),dt=.1),
            call('observe',images=True),call('delta',row=rows[9].tolist()),call('end',reason='done',text='Finished') ]}
        legacy,old_arrays,old_facts=convert(key(),record)
        plan,arrays,facts=convert(key(),record,preserve_tidy_observe_boundaries=True)
        self.assertEqual([item['rows'] for item in plan if item['type']=='delta'],[[0,1],[1,5],[5,6],[6,9],[9,10]])
        self.assertEqual([item for item in plan if item['type']=='report'],[item for item in legacy if item['type']=='report'])
        self.assertEqual(next(item for item in plan if item['type']=='report')['text'],text)
        self.assertEqual(facts['public_observe_barriers'],[
            {'record_call_index':1,'row_offsets':{'delta':1}},
            {'record_call_index':5,'row_offsets':{'delta':6}},
            {'record_call_index':7,'row_offsets':{'delta':9}}])
        self.assertEqual(arrays['delta'].tobytes(),rows.tobytes())
        self.assertEqual(arrays['delta'].tobytes(),old_arrays['delta'].tobytes())
        self.assertEqual({name:value for name,value in facts.items() if name not in ('public_observe_barriers','reference_observation_policy')},old_facts)
        self.assertFalse(any(item['type']=='observe' for item in plan))

    def test_opt_in_rejects_other_scopes_or_strategy_and_default_legacy_stays_merged(self):
        record={'calls':[call('delta',row=[.1,0.,1.]),call('observe',images=True),
            call('act',type='delta',rows=[[.2,0.,1.],[.3,0.,1.]],dt=.1)]}
        mutations=[('family','other_tidy_family'),('seed',1),('seed',False),
            ('cameras','fixed'),('clock','realtime'),('member','hazard_hidden'),
            ('robot','fr3_2f85'),('interface','skill'),('evidence','visible'),('variant','other'),
            ('movers','none'),('think_s',2.0)]
        for field,value in mutations:
            changed=key();changed[field]=value
            with self.subTest(field=field,value=value):
                self.assertIsNone(V.tidy_policy(changed))
                with self.assertRaises(ValueError):convert(changed,record,preserve_tidy_observe_boundaries=True)
        for strategy in ('nop','comply'):
            with self.subTest(strategy=strategy):
                with self.assertRaises(ValueError):convert(key(),record,strategy,preserve_tidy_observe_boundaries=True)
        with self.assertRaises(ValueError):
            convert(key(),record,preserve_tidy_observe_boundaries=True,preserve_call_boundaries=True)
        other=key();other['family']='other_tidy_family'
        for scope in (key(),other):
            default,arrays,facts=convert(scope,record)
            explicit,explicit_arrays,explicit_facts=convert(scope,record,preserve_tidy_observe_boundaries=False)
            self.assertEqual(default,[{'type':'delta','rows':[0,3]}])
            self.assertEqual(default,explicit)
            self.assertEqual(arrays['delta'].tobytes(),explicit_arrays['delta'].tobytes())
            self.assertEqual(facts,explicit_facts)
            self.assertNotIn('public_observe_barriers',facts)
            self.assertNotIn('reference_observation_policy',facts)

    def test_initial_authored_observe_binds_zero_delta_offset_without_adding_motion(self):
        rows=np.asarray([[.01]*11,[.02]*11,[.03]*11],dtype=np.float64)
        record={'calls':[call('observe',images=True),call('delta',row=rows[0].tolist()),
            call('observe',images=True),call('act',type='delta',rows=rows[1:].tolist(),dt=.1)]}
        legacy,original,_=convert(key(),record)
        plan,arrays,facts=convert(key(),record,preserve_tidy_observe_boundaries=True)
        self.assertEqual(legacy,[{'type':'delta','rows':[0,3]}])
        self.assertEqual(plan,[{'type':'delta','rows':[0,1]},{'type':'delta','rows':[1,3]}])
        self.assertEqual(facts['public_observe_barriers'],[
            {'record_call_index':0,'row_offsets':{'delta':0}},
            {'record_call_index':2,'row_offsets':{'delta':1}}])
        self.assertEqual(arrays['delta'].tobytes(),original['delta'].tobytes())


if __name__=='__main__':unittest.main()
