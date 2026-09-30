"""Behavioral boundary tests: actual runtime methods with an inert physics backend."""
import ast,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from episode_clock import AgentClock
ROOT=Path(__file__).resolve().parents[2]
class Clock(AgentClock):
 def __init__(self):
  self.t=0;self.active=True;self.ended=False;self.reason=None;self.end_elapsed=None;self.events=[];self.init_agent_clock()
 def elapsed(self):return self.t
 def finish(self,reason):self.ended=True;self.reason=reason;self.end_elapsed=self.t
 def event(self,kind,**kwargs):self.events.append(kind)
 def persist(self):return self.agent_clock_fields()
class Tests(unittest.TestCase):
 def test_success_does_not_freeze_agent_clock(self):
  c=Clock();c.t=2;c.finish('native_success');c.t=3601;c.deadline();c.stop_agent()
  self.assertTrue(c.agent_timeout);self.assertEqual(c.persist()['termination_reason'],'timeout');self.assertEqual(c.persist()['episode_seconds'],2)
 def test_collection_not_charged(self):
  c=Clock();c.t=8;c.stop_agent();c.t=9999;c.deadline();c.stop_agent()
  self.assertEqual(c.persist()['agent_seconds'],8);self.assertFalse(c.agent_timeout);self.assertEqual(c.events.count('agent_stop'),1)
 def test_unlimited_runtime_crosses_old_boundaries(self):
  registry=json.loads((ROOT/'suites/two-modes.json').read_text())
  representatives={}
  for r in registry['instances']:
   if not r['modes']['unlimited']['blocked_reason']:representatives.setdefault(r['benchmark'],r)
  for b,r in representatives.items():
   folder=ROOT/r['modes']['unlimited']['path'];module='vlb_traj.py' if b=='vlabench' else 'mw_runtime.py' if b=='metaworldplus' else 'casa_runtime.py'
   p=folder/'environment'/module
   tree=ast.parse(p.read_text());cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Session')
   relevant=[x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name in ('step','_step','_validate','reset','load_trajectory')]
   for fn in relevant:
    for node in ast.walk(fn):
     if isinstance(node,ast.If):
      test=ast.unparse(node.test)
      self.assertNotIn('MAX_ACTIONS',test,(b,fn.name,test));self.assertNotIn('MAX_CONTROLS',test,(b,fn.name,test));self.assertNotIn('16000',test);self.assertNotIn('>= 40',test)
  # Execute VLAB's real archive validator on 4001 valid controls.
  r=representatives['vlabench'];tree=ast.parse((ROOT/r['modes']['unlimited']['path']/'environment/vlb_traj.py').read_text());cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Session');fn=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='_validate')
  ns={'np':np};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual-vlb-validator>','exec'),ns)
  class S:lower=np.ones(9)*-10;upper=np.ones(9)*10
  self.assertEqual(ns['_validate'](S(),np.zeros((4001,9))).shape,(4001,9))
 def test_limited_only_four_public_operations(self):
  d=json.loads((ROOT/'suites/two-modes.json').read_text())
  for b in ('vlabench','metaworldplus','robocasa','robocasa365','robocasa-gr1'):
   r=next(x for x in d['instances'] if x['benchmark']==b and not x['modes']['limited']['blocked_reason'])
   s=(ROOT/r['modes']['limited']['path']/'environment/server/server.py').read_text();tree=ast.parse(s)
   cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Service');dispatch=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='dispatch')
   endpoints={n.value for n in ast.walk(dispatch) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('/v1/')}
   self.assertEqual(endpoints,{'/v1/spec','/v1/observe','/v1/step','/v1/status'})
if __name__=='__main__':unittest.main()
