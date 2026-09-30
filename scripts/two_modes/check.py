"""Check canonical coverage, identities, isolation configuration and runtime budgets."""
import argparse,ast,collections,json,re,tomllib,warnings
from pathlib import Path
import yaml
from common import ROOT,REGISTRY,PROTOCOL,BENCHMARKS,read,write,sha

def fingerprints(path):
 return {str(p.relative_to(path)):sha(p) for p in sorted(path.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
def check(update=False):
 from harbor.models.task.config import TaskConfig
 from harbor.models.task.task import Task
 from harbor.publisher.packager import Packager
 data=read(REGISTRY);ids=set();counts=collections.Counter();errors=[];manifests={}
 for r in data['instances']:
  for mode,m in r['modes'].items():
   p=ROOT/m['path'];counts[(r['benchmark'],mode,'unavailable' if m['blocked_reason'] else 'configured')]+=1
   try:
    assert m['task_id'] not in ids,'duplicate ID';ids.add(m['task_id'])
    assert '-privileged-' not in p.name and '-priviledged-' not in p.name
    assert p.parent==ROOT/(mode+'_tasks')/r['benchmark']
    if m['blocked_reason']:
     assert (p/'unavailable.json').exists();continue
    cfg=tomllib.loads((p/'task.toml').read_text());TaskConfig.model_validate(cfg)
    assert cfg['task']['name']==m['task_id'];assert cfg['agent']['timeout_sec']==3600
    assert cfg['environment']['network_mode']=='allowlist'
    scene=p/('environment/server' if mode=='limited' else 'environment')/r['instance_file']
    assert sha(scene)==r['instance_sha256']==sha(p/'tests'/r['instance_file']),'instance changed'
    compose=yaml.safe_load((p/'environment/docker-compose.yaml').read_text());main=compose['services']['main']
    assert 'networks' not in main and main['cap_drop']==['ALL'] and not main.get('volumes')
    assert compose['networks']['episode']['internal'];assert compose['services']['harbor-docker-egress-control-sidecar']['networks']==['episode']
    if mode=='limited':
     docker=(p/'environment/Dockerfile').read_text()
     assert not re.search(r'^COPY (?:\. |.*(?:instance|server|oracle))',docker,re.M),'private copy to main'
     server=(p/'environment/server/server.py').read_text()
     assert 'agent_stop_elapsed' in server or 'AgentClock' in server
     assert cfg['verifier']['environment_mode']=='separate' and cfg['verifier']['environment']['network_mode']=='no-network'
     for file in ('instance.npz','instance.json','mw_runtime.py','vlb_traj.py','casa_runtime.py','casa_traj.py','backend.py'):
      if (p/'environment/server'/file).exists():assert (p/'environment/server'/file).read_bytes()==(p/'tests'/file).read_bytes(),file
    else:
     for runtime in ('mw_runtime.py','vlb_traj.py','casa_runtime.py','casa_traj.py'):
      f=p/'environment'/runtime
      if not f.exists():continue
      text=f.read_text();assert not re.search(r'self\.resets\s*>=\s*40|self\.total_steps\s*>=\s*16000|self\.sim_steps\s*>=\s*MAX_ACTIONS|len\(self.actions\)\s*>=\s*MAX_',text),'remaining budget'
      assert 'sim-usage' in text,'missing per-session accounting'
      if runtime=='mw_runtime.py':assert "env.max_path_length=float('inf')" in text
    for f in p.rglob('*.py'):ast.parse(f.read_text())
    fp=fingerprints(p)
    if update:
     with warnings.catch_warnings():warnings.simplefilter('ignore');m['task_checksum']=Task(p).checksum
     digest,_=Packager.compute_content_hash(p);m['package_digest']='sha256:'+digest;m['fingerprints']=fp
    elif m.get('fingerprints')!=fp:raise AssertionError('task content changed after registry freeze')
    manifests.setdefault(p.parent,[]).append(m)
   except Exception as e:errors.append({'task':m['path'],'error':str(e),'type':type(e).__name__})
 if not update:
  for folder,rs in manifests.items():
   try:
    entries=tomllib.loads((folder/'dataset.toml').read_text())['tasks']
    expected={m['task_id']:m['package_digest'] for m in rs}
    assert len(entries)==len(expected) and {t['name']:t['digest'] for t in entries}==expected,'dataset registration/digest mismatch'
   except Exception as e:errors.append({'dataset':str(folder.relative_to(ROOT)),'error':str(e)})
 for mode in ('limited','unlimited'):
  expected={m['path'] for r in data['instances'] for key,m in r['modes'].items() if key==mode and not m['blocked_reason']}
  actual={str(p.parent.relative_to(ROOT)) for b in BENCHMARKS for p in (ROOT/(mode+'_tasks')/b).glob('*/task.toml')}
  if actual!=expected:errors.append({'mode':mode,'unregistered':sorted(actual-expected),'missing':sorted(expected-actual)})
 if update and not errors:
  write(REGISTRY,data)
  for folder,rs in manifests.items():
   name=folder.parent.name.replace('_tasks','')+'-'+folder.name+'-60min-v3'
   text='[dataset]\nname = "robot-coding-bench/'+name+'"\nversion = "0.3.0"\ndescription = "Canonical two-mode tasks; consult suites/two-modes.json for readiness."\n'
   for m in rs:text+='\n[[tasks]]\nname = "'+m['task_id']+'"\ndigest = "'+m['package_digest']+'"\n'
   (folder/'dataset.toml').write_text(text)
  for mode in ('limited','unlimited'):
   write(ROOT/'suites'/('two-modes-'+mode+'.json'),dict(protocol=PROTOCOL,mode=mode,agent_seconds=3600,step_limit=None if mode=='unlimited' else 'per-instance protocol horizon',reset_limit=None if mode=='unlimited' else 0,tasks=[dict(benchmark=r['benchmark'],source_task_id=r['source_task_id'],seed=r['seed'],instance_sha256=r['instance_sha256'],**{k:v for k,v in r['modes'][mode].items() if k!='fingerprints'}) for r in data['instances']]))
 report=dict(counts=[dict(benchmark=b,mode=m,status=s,count=n) for (b,m,s),n in sorted(counts.items())],errors=errors,model_evaluation_run=False)
 write(ROOT/'docs/validation/two-modes-v3/config-check.json',report)
 print(json.dumps(report,indent=2));return not errors
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');a=p.parse_args();raise SystemExit(0 if check(a.freeze) else 1)
