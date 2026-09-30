"""Build canonical self-contained two-mode tasks without changing historical inputs."""
import argparse,ast,collections,importlib.util,json,re,shutil,sys,tomllib
from pathlib import Path
import yaml
from common import ROOT,ARCHIVE,REGISTRY,PROTOCOL,VERSION,BENCHMARKS,read,write,sha,resolve
PYBASE='python:3.10.18-slim-bookworm@sha256:445b9efb2c047a7ccdb30d293fd6b1aa0f62a55062dc2b69051df91e10848749'

def copy(src,dest):
 shutil.copytree(src,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.mp4','validation','recipe.json'),dirs_exist_ok=False)

def identity(name,mode):
 name=re.sub(r'-(?:privileged|priviledged|limited60(?:-v\d+)?|unlimited60(?:-v\d+)?)','',name)
 head,index=name.rsplit('-',1)
 return head+'-'+mode+VERSION+'-'+index

def network(dest):
 env=dest/'environment';p=env/'docker-compose.yaml'
 cfg=yaml.safe_load(p.read_text()) if p.exists() else {'services':{'main':{}}}
 services=cfg['services'];main=services.setdefault('main',{})
 main.pop('networks',None);main.pop('network_mode',None)
 main.update(cap_drop=['ALL'],security_opt=['no-new-privileges:true'])
 for name,s in services.items():
  if name not in ('main','codex-egress'):s['networks']=['episode']
 services['harbor-docker-egress-control-sidecar']={'networks':['episode']}
 cfg['networks']={'episode':{'internal':True},'codex_external':{}}
 proxy=env/'codex-egress';proxy.mkdir(exist_ok=True)
 shutil.copy2(ROOT/'scripts/vlabench/codex_subscription/egress.py',proxy/'egress.py')
 (proxy/'Dockerfile').write_text(f'FROM {PYBASE}\nCOPY egress.py /egress.py\nUSER 65532:65532\nCMD ["python","-u","/egress.py"]\n')
 services['codex-egress']={'build':{'context':'${CONTEXT_DIR}/codex-egress'},'networks':['episode','codex_external'],
  'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],'read_only':True,'cpus':.25,'mem_limit':'128m',
  'healthcheck':{'test':['CMD','python','-c',"import socket; socket.create_connection(('localhost',3128),timeout=2).close()"],'interval':'2s','timeout':'5s','retries':30}}
 main.setdefault('depends_on',{})['codex-egress']={'condition':'service_healthy'}
 main.setdefault('environment',{}).update(HTTP_PROXY='http://codex-egress:3128',HTTPS_PROXY='http://codex-egress:3128',NO_PROXY='sim,localhost,127.0.0.1',http_proxy='http://codex-egress:3128',https_proxy='http://codex-egress:3128',no_proxy='sim,localhost,127.0.0.1')
 p.write_text(yaml.safe_dump(cfg,sort_keys=False))
 t=dest/'task.toml';s=t.read_text();s=re.sub(r'^network_mode\s*=.*\n','',s,flags=re.M) if '[verifier.environment]' not in s else s
 # Restrict ONLY main environment; verifier keeps its no-network setting.
 start=s.index('[environment]');end=s.find('\n[',start+2);end=len(s) if end<0 else end
 block=s[start:end];block=re.sub(r'\n(?:network_mode|allowed_hosts)\s*=.*','',block)
 block+='\nnetwork_mode = "allowlist"\nallowed_hosts = ["sim", "codex-egress"]\n'
 s=s[:start]+block+s[end:];t.write_text(s)

def clock_patch(dest):
 p=dest/'environment/server/server.py';s=p.read_text()
 if 'agent_clock_fields' in s or 'agent_stop_elapsed' in s:return
 s=s.replace('class Service:', 'from episode_clock import AgentClock\n\nclass Service(AgentClock):')
 tree=ast.parse(s);cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Service')
 method=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name=='deadline')
 lines=s.splitlines(True);del lines[method.lineno-1:method.end_lineno];s=''.join(lines)
 pattern=r'(        self\.persist\(\)\n)';s=re.sub(pattern,'        self.init_agent_clock()\n\\1',s,count=1)
 s=s.replace("        temp = ROOT / 'episode.tmp'", "        value.update(self.agent_clock_fields())\n        temp = ROOT / 'episode.tmp'")
 s=s.replace("        temp=ROOT/'episode.tmp'", "        value.update(self.agent_clock_fields())\n        temp=ROOT/'episode.tmp'")
 s=s.replace("            if command == 'seal':\n", "            if command == 'stop': return self.stop_agent()\n            if command == 'seal':\n                self.stop_agent()\n")
 s=s.replace("            if command=='seal':\n", "            if command=='stop': return self.stop_agent()\n            if command=='seal':\n                self.stop_agent()\n")
 s=s.replace("self.event('request_rejected')", "self.event('request_rejected',physics_steps=0)")
 ast.parse(s);p.write_text(s);shutil.copy2(Path(__file__).with_name('episode_clock.py'),p.parent/'episode_clock.py')
 grade=dest/'tests/grade.py';s=grade.read_text()
 s=s.replace("if not episode['sealed']", "if not episode.get('agent_stopped') or not episode['sealed']")
 # Both current grader styles are supported.
 s=s.replace("episode['termination_reason'] == 'timeout'", "(episode['termination_reason'] == 'timeout' or episode['agent_seconds'] >= 3600)")
 s=s.replace("episode['termination_reason']=='timeout'", "(episode['termination_reason']=='timeout' or episode['agent_seconds']>=3600)")
 needle="        begins = [e for e in events" if '        begins = [e for e in events' in s else "        begins=[e for e in events"
 at=s.index(needle);s=s[:at]+"        if any(sum(e['kind']==k for e in events)!=1 for k in ('agent_start','agent_stop','sealed')): raise ValueError('invalid lifecycle journal')\n"+s[at:]
 s=s.replace("and same and not reward['timeout'])", "and same and not reward['timeout'] and not reward['simulation_failure'])")
 if 'vlabench' in str(dest):
  s=s.replace("        original=json.loads", "        if not all(r['initial_state_sha']==episode['initial_state_sha'] for r in replays): raise ValueError('initial state mismatch')\n        from vlb_traj import digest\n        if episode['instance_sha']!=digest(json.loads(Path('/tests/instance.json').read_text())): raise ValueError('instance mismatch')\n        original=json.loads")
 ast.parse(s);grade.write_text(s)

def vlb_unlimited(source,dest):
 copy(source,dest)
 # Sensor-only historical IDs share the same frozen task; use its privileged
 # counterpart tooling while retaining their own identity and instance bytes.
 env=dest/'environment';template=resolve('tasks/vlabench-select-fruit-i00')
 if not (env/'vlb_traj.py').exists():
  shutil.rmtree(env);shutil.copytree(template/'environment',env)
  shutil.copy2(source/'tests/instance.json',env/'instance.json')
  for f in ('vlb_traj.py','backend.tar.gz'):
   if (source/'tests'/f).exists():shutil.copy2(source/'tests'/f,env/f)
  # Private verifier/tooling already belongs to this exact source instance.
 if not (dest/'tests/grade.py').exists():shutil.copy2(template/'tests/grade.py',dest/'tests/grade.py')
 p=env/'vlb_traj.py';s=p.read_text();s=s.replace('import argparse','import uuid\nimport argparse',1)
 start=s.index('        if self.budget_path and self.budget_path.exists():');end=s.index('        self.reset()',start)
 s=s[:start]+'''        self.session_id = uuid.uuid4().hex
        if self.budget_path:
            self.budget_path = self.budget_path.parent / 'sim-usage' / (self.session_id + '.json')
        self._prior_wall = 0.0
'''+s[end:]
 s=s.replace('        self.counters["wall_seconds"] =', '        self.counters["session_id"] = self.session_id\n        self.counters["reset_count"] = max(0,self.counters["resets"]-1)\n        self.counters["wall_seconds"] =')
 ast.parse(s);p.write_text(s)
 # Full privileged tooling/instruction from the native source; no experts in main.
 desc=read(env/'instance.json')
 (dest/'instruction.md').write_text(f'''Complete this fixed robot task: **{desc['instruction']}**.
Use `from vlb_traj import Session; s=Session()`; read /app/API.md.
Unlimited means privileged state via s.state(), native general skills, same-instance reset,
record and replay. No reset count, cumulative exploration, model-call or token quota.
No episode or submitted-trajectory step cap. All exploration, thought and resets share 3600 seconds.
Only robot controls may change the scene; do not change runtime, physics, predicates or scores.
Start recording immediately after reset with s.record_start(); use s.save_trajectory(s.record_stop(),'/app/output/trajectory.npz').
Only the final submitted trajectory is independently replayed twice; exploration successes do not score.
Costs are per-Session under /app/output/sim-usage; sum all records. No expert policy is provided.
''')


def warm_setup(dest):
 env=dest/'environment';shutil.copy2(Path(__file__).with_name('warm_session.py'),env/'warm_session.py')
 p=env/'Dockerfile';s=p.read_text()
 s+='\nCOPY warm_session.py /opt/rcb-setup/warm_session.py\nCOPY warm_session.py /app/warm_session.py\nENV RCB_WARM_CLIENT=1\n'
 # Existing simulator module paths stay intact; only add the public proxy helper.
 match=re.findall(r'^ENV PYTHONPATH=(.*)$',s,re.M)
 s+='ENV PYTHONPATH=/opt/rcb-setup:'+ (match[-1] if match else '/app')+'\n'
 p.write_text(s)
 instruction=dest/'instruction.md'
 instruction.write_text(instruction.read_text().replace('`Session.env` exposes native fixture geometry, robot state and controllers.', '`NativeSession().env` exposes native fixture geometry, robot state and controllers; import NativeSession from casa_traj for this advanced local API. This additional initialization counts toward agent time.'))
 # The legacy navigation reference is copied to /app/output before execution;
 # it introspects .env for its own audit hash and must use the explicit native API.
 reference=dest/'solution/gen.py'
 if reference.exists():
  reference.write_text(reference.read_text().replace('from casa_traj import Session, state_sha','from casa_traj import NativeSession as Session, state_sha'))
 for name in ('mw_runtime.py','vlb_traj.py','casa_runtime.py','casa_traj.py'):
  p=env/name
  if not p.exists():continue
  s=p.read_text();s=s.replace('budget_path=None,replaying=True',"budget_path='/app/output/budget.json',replaying=True").replace('s=Session(instance,budget_path=None);writer=None','s=Session(instance);writer=None');s+='\n# Trusted runner preinitializes the first simulator outside the agent clock.\nif __name__ != "__main__":\n import sys as _sys\n from warm_session import install as _install\n _install(_sys.modules[__name__])\n';p.write_text(s)


def unbound(dest,benchmark):
 if benchmark=='metaworldplus':
  # Use the identical unlimited adapter in main and verifier: same frozen physical
  # state and predicate, with only time-limit truncation disabled after restore.
  text=(dest/'environment/mw_runtime.py').read_text()
  text=text.replace('not 1<=len(a)<=MAX_ACTIONS','len(a)<1')
  text=text.replace("        if len(self.actions)>=MAX_ACTIONS:raise RuntimeError('episode control limit (500) reached; reset() to start a new episode')\n",'')
  text=text.replace("        self.obs=frozen['observation'].copy();", "        env.max_path_length=float('inf')  # User override: unlimited controls, unchanged native success.\n        self.obs=frozen['observation'].copy();")
  text=text.replace('no reset cap and no cumulative control cap (the 500-control native episode cap is\nkept)', 'no reset, cumulative-control or episode-control cap')
  for part in ('environment','tests'):(dest/part/'mw_runtime.py').write_text(text)
  instruction=(dest/'instruction.md').read_text().replace('Each episode, and\ntherefore the submitted trajectory, is limited to the native 500 controls.', 'No episode or submitted-trajectory control cap applies; the native success predicate is unchanged.')
  (dest/'instruction.md').write_text(instruction)
 elif benchmark=='vlabench':
  for part in ('environment','tests'):
   p=dest/part/'vlb_traj.py';s=p.read_text()
   s=s.replace('not 1 <= len(a) <= MAX_ACTIONS','len(a) < 1')
   s=s.replace('        if self.sim_steps >= MAX_ACTIONS: raise RuntimeError("episode action budget exceeded")\n','')
   s=s.replace('1..4000 finite rows','one or more finite rows').replace('MAX_BYTES = 8 * 1024 * 1024','MAX_BYTES = 1024 * 1024 * 1024')
   p.write_text(s)
  for p in (dest/'environment').glob('*.md'):
   s=p.read_text().replace('4000','unbounded');p.write_text(s)
 # Long unlimited trajectories need independently budgeted verifier workers.
 for p in (dest/'tests').glob('*grade.py'):
  s=p.read_text();s=re.sub(r'timeout\s*=\s*(300|600|900)(?![0-9])','timeout=3600',s);p.write_text(s)
 p=dest/'task.toml';s=p.read_text();s=re.sub(r'(\[verifier\]\s*(?:environment_mode[^\n]*\n)?timeout_sec\s*=\s*)[\d.]+',r'\g<1>7500.0',s);p.write_text(s)
 for p in (dest/'environment/archive.py',dest/'tests/archive.py'):
  if p.exists():
   s=p.read_text().replace('16_000_000','1_073_741_824').replace('64_000_000','2_147_483_648');p.write_text(s)


def collect():
 data=[]
 srcroot=ROOT/'tasks' if not (ARCHIVE/'tasks').exists() else ARCHIVE/'tasks'
 for p in sorted(srcroot.glob('*/task.toml')):
  cfg=tomllib.loads(p.read_text());m=cfg['metadata'];b=m.get('benchmark',m.get('simulator'))
  if b not in BENCHMARKS or b=='vlabench':continue
  source=str(p.parent.relative_to(ROOT));slug=p.parent.name
  data.append(dict(benchmark=b,source=source,source_slug=slug,source_task_id=cfg['task']['name'],family=m['family'],seed=m.get('instance_seed'),environment_id=m.get('environment_id'),instance_file='instance.npz'))
 # Include the complete previously integrated VLABench inventory (including unavailable).
 old=read(ROOT/'docs/validation/vlabench-limited-60min-20260924/inventory.json')
 available={tomllib.loads(p.read_text())['task']['name']:p.parent for p in srcroot.glob('vlabench*/task.toml')}
 for r in old['instances']:
  src=available.get(r['task_id'])
  if src is None:
   try:src=resolve(r['directory'])
   except FileNotFoundError:src=ROOT/'staging/removed-duplicates'/Path(r['directory']).name
  descriptor=next((src/p for p in ('environment/instance.json','tests/instance.json','environment/server/instance.json') if (src/p).exists()),None)
  if descriptor is None and r.get('descriptor'):
   try:descriptor=resolve(r['descriptor'])
   except FileNotFoundError:pass
  data.append(dict(benchmark='vlabench',source=str(src.relative_to(ROOT)),source_slug=src.name,source_task_id=r['task_id'],family=r['family'],seed=r['seed'],environment_id=read(descriptor).get('native_task') if descriptor else r['family'],instance_file='instance.json',descriptor=str(descriptor.relative_to(ROOT)) if descriptor else None,unavailable_reason=None if descriptor else 'missing_frozen_instance',old_limited=r['limited_directory'],historical_validation=r.get('existing_validation')))
 return data

def prepare():
 if REGISTRY.exists():raise SystemExit('Canonical registry already exists; validate it with check.py (no overwriting frozen tasks).')
 mw=read(ROOT/'jobs/metaworldplus-codex-luna-high-60min-20260928T1717Z/plan.json')
 mwrows={(r['source_slug'],r['mode']):r for r in mw['records']}
 casa=read(resolve('unlimited_tasks/robocasa-60min-v2/inventory.json'))['records'];casamap={Path(r['source']).name:r for r in casa}
 records=collect()
 for r in records:
  source=ROOT/r['source'];r['modes']={}
  frozen=source/'tests'/r['instance_file']
  if not frozen.exists() and r.get('descriptor'):frozen=ROOT/r['descriptor']
  r['instance_sha256']=sha(frozen) if frozen.exists() else None
  if r['benchmark'].startswith('robocasa'):r['seed']=casamap[r['source_slug']]['seed']
  for mode in ('unlimited','limited'):
   slug=identity(r['source_slug'],mode);dest=ROOT/(mode+'_tasks')/r['benchmark']/slug
   blocked=r.get('unavailable_reason');template=None
   if r['benchmark']=='metaworldplus':
    old=mwrows[r['source_slug'],mode];blocked=old.get('blocked_reason');template=ROOT/old['path'] if old.get('path') else None
   elif r['benchmark'].startswith('robocasa'):
    row=casamap[r['source_slug']];template=resolve(row['path']) if mode=='unlimited' else resolve(row['path'].replace('unlimited_tasks','limited_tasks').replace('unlimited60-v2','limited60-v2'))
   elif mode=='limited' and not blocked:template=resolve(r['old_limited'])
   r['modes'][mode]=dict(path=str(dest.relative_to(ROOT)),task_id='robot-coding-bench/'+slug,blocked_reason=blocked,validation='not_run_for_this_revision')
   if blocked:
    dest.mkdir(parents=True);write(dest/'unavailable.json',dict(source=r['source'],reason=blocked,seed=r['seed'],instance_sha256=r['instance_sha256']))
    continue
   if template:copy(template,dest)
   else:
    base=source
    if 'sensor-only' in r['source_slug']:
     matches=[x for x in records if x['benchmark']=='vlabench' and 'sensor-only' not in x['source_slug'] and x.get('descriptor') and sha(ROOT/x['descriptor'])==r['instance_sha256']]
     if not matches:raise RuntimeError('Missing matching privileged source '+r['source_slug'])
     base=ROOT/matches[0]['source']
    vlb_unlimited(base,dest)
   if mode=='unlimited':
    unbound(dest,r['benchmark'])
    warm_setup(dest)
   if mode=='limited':
    clock_patch(dest)
    for file in ('environment/client/API.md','instruction.md'):
     p=dest/file
     if p.exists():
      s=p.read_text().replace('The host vision bridge attaches these public images to the next model turn.','Use the Codex native view_image tool to open the saved RGB file.').replace('The original physical cap','The repository episode/trajectory cap')
      p.write_text(s)
   p=dest/'task.toml';s=p.read_text();cfg=tomllib.loads(s)
   s=s.replace(cfg['task']['name'],'robot-coding-bench/'+slug,1)
   s=re.sub(r'^experiment_mode\s*=.*\n','',s,flags=re.M)
   s=s.replace('[metadata]\n',f'[metadata]\nexperiment_mode = "{mode}-{VERSION}"\n')
   s=re.sub(r'(\[agent\]\s*timeout_sec\s*=\s*)[\d.]+',r'\g<1>3600.0',s)
   p.write_text(s);network(dest)
   for f in dest.rglob('*.py'):ast.parse(f.read_text())
   scene=dest/('environment/server' if mode=='limited' else 'environment')/r['instance_file']
   assert sha(scene)==r['instance_sha256'],scene
   assert sha(dest/'tests'/r['instance_file'])==r['instance_sha256'],dest
   (dest/'README.md').write_text(f'''# {slug}

{mode} task, protocol: `{PROTOCOL}`. Historical source: `{r['source']}`.
Frozen instance SHA256: `{r['instance_sha256']}`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
''')
  print(r['benchmark'],r['source_slug'],flush=True)
 write(REGISTRY,dict(schema_version=1,protocol=PROTOCOL,protocol_sha256=sha(ROOT/PROTOCOL),version=VERSION,overrides={'unlimited': 'User override: no episode/submission/exploration step or reset cap; 3600 seconds only. Native success unchanged.'},instances=records))
 print(dict(collections.Counter(r['benchmark'] for r in records)))
if __name__=='__main__':prepare()
