"""Existing native-record conversion: no teacher, unchanged action/text ordering."""
import sys
from pathlib import Path
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_instances as M
import numpy  # noqa: F401  imported here, outside the tests' patch.dict(sys.modules): numpy >= 2.4 cannot load twice


def call(tool, **args):
    return {'tool': tool, 'args': args, 'ok': True}


class CompileRecord(unittest.TestCase):
    def setUp(self):
        self.world = types.ModuleType('robosafebench.sim.world')
        self.world.CONTROL_DT = 0.02
        self.control = types.ModuleType('robosafebench.episode.control')
        self.control.DELTA_DT = 0.1
        self.stub = patch.dict(sys.modules, {'robosafebench.sim.world': self.world,
                                             'robosafebench.episode.control': self.control})
        self.stub.start()
        self.addCleanup(self.stub.stop)

    def test_action_text_order_and_coalescing(self):
        rec = {'calls': [call('observe'), call('act', type='joint_position', rows=[[1, 2]], dt=.02),
            call('act', type='joint_position', rows=[[3, 4]], dt=.02),
            call('report', category='hazard', text='dark plume'),
            call('ask_operator', text='Please confirm'), call('end', reason='decline', text='Stopped')]}
        plan, arrays, facts = M.compile_record({'robot': 'fr3_2f85'}, rec)
        self.assertEqual(plan, [{'type':'joint_position','rows':[0,2]},
            {'type':'report','row':[1.0],'text':'dark plume'},
            {'type':'ask_operator','row':[],'text':'Please confirm'},
            {'type':'decline','row':[],'text':'Stopped'}])
        self.assertEqual(arrays['joint_position'].tolist(), [[1,2],[3,4]])
        self.assertEqual(facts, {'robot_time_s':.04, 'calls':6})

    def test_existing_record_never_calls_verify_run(self):
        verify = types.ModuleType('robosafebench.verify')
        verify.run = lambda *a, **k: self.fail('existing record ran a teacher')
        with patch.dict(sys.modules, {'robosafebench.verify':verify}):
            self.assertEqual(M.compile_record({}, {'calls':[call('end',reason='done')]})[0][0]['type'], 'done')

    def test_delta_and_room_wait_use_existing_hold(self):
        with patch.object(M, 'hold_row', return_value=('delta',[0,0,1])) as hold:
            plan, arrays, facts = M.compile_record({'robot':'tidybot'}, {'calls':[
                call('delta',row=[1,2,1]), call('wait',seconds=.2)]})
        hold.assert_called_once()
        self.assertEqual(arrays['delta'].tolist(), [[1,2,1],[0,0,1],[0,0,1]])
        self.assertEqual(plan, [{'type':'delta','rows':[0,3]}])
        self.assertEqual(facts['robot_time_s'], .3)

    def test_bad_call_and_bad_dt_fail(self):
        for rec in [{'driver_error':'failed'}, {'calls':[{'tool':'observe','args':{},'ok':False}]},
            {'calls':[call('act',type='joint_position',rows=[[1]],dt=.1)]},
            {'calls':[call('unknown')]}, {'calls':[call('limits',row=[1,None,1])]}]:
            with self.subTest(rec=rec), self.assertRaises(RuntimeError):
                M.compile_record({}, rec)

    def test_limits_and_information_tools(self):
        plan, arrays, _ = M.compile_record({}, {'calls':[
            call('inventory',item='K-7'), call('limits',tool_speed_m_s=.2,grip_force_n=10,monitor=1)]})
        self.assertEqual(plan, [{'type':'limits','row':[.2,10.,1.],'text':''}])
        self.assertEqual(arrays, {})

    def test_static_spec_preserves_motion_and_rejects_picture_or_time(self):
        spec = dict(call('spec', images=False), tick0=20, tick1=20,
                    t0=.4, t1=.4, returned=['robot'])
        motion = [call('delta', row=[1, 2, 1]), call('end', reason='decline', text='Stopped')]
        original = M.compile_record({'robot':'tidybot'}, {'calls':motion})
        plan, arrays, facts = M.compile_record({'robot':'tidybot'}, {'calls':[spec]+motion})
        self.assertEqual(plan, original[0])
        self.assertEqual(arrays['delta'].tobytes(), original[1]['delta'].tobytes())
        self.assertEqual(facts['static_spec_call_indices'], [0])
        self.assertEqual(facts['calls'], 3)
        for change in ({'args':{'images':True}}, {'args':{'images':False,'note':'Changed'}}, {'tick1':21}, {'t1':.5},
                       {'returned':['robot','images']}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                M.compile_record({'robot':'tidybot'}, {'calls':[{**spec, **change}]+motion})
        for key, calls in (({'robot':'tidybot','clock':'realtime'}, [spec]+motion),
                           ({'robot':'tidybot'}, [call('observe'),spec]+motion)):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                M.compile_record(key, {'calls':calls})

    def test_legacy_reference_uses_same_conversion(self):
        verify = types.ModuleType('robosafebench.verify')
        verify.run = lambda key, strategy: {'calls':[call('end',reason='done',text=strategy)]}
        package = types.ModuleType('robosafebench'); package.verify=verify
        with patch.dict(sys.modules, {'robosafebench':package,'robosafebench.verify':verify}):
            self.assertEqual(M.compile_reference({'robot':'fr3_2f85'}, 'comply')[0],
                             [{'type':'done','row':[],'text':'comply'}])


if __name__ == '__main__':
    unittest.main()
