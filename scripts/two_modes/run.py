"""Unified lifecycle runner. Smoke runs oracle/nop only; model execution is explicit."""
import argparse,asyncio,datetime,importlib.metadata,json,os,shutil,sys,time
from pathlib import Path
from common import ROOT,REGISTRY,rows,read,write,sha,resolve
from lifecycle import command,containers,isolate,public_probe
sys.path.append(str(ROOT/'scripts/vlabench'))
SECRET_ENV=('OPENAI_API_KEY','CODEX_API_KEY','OPENROUTER_API_KEY','LITELLM_API_KEY','OPENAI_BASE_URL','OPENAI_API_BASE','OPENROUTER_API_BASE','CODEX_ACCESS_TOKEN','AZURE_OPENAI_API_KEY','OPENAI_ORG_ID')
STABLE={'vlabench':'vlabench-select-fruit-i00','metaworldplus':'metaworldplus-push-privileged-i00','robocasa':'robocasa-close-drawer-privileged-i00','robocasa365':'robocasa365-turn-on-stove-privileged-i00','robocasa-gr1':'robocasa-gr1-pn-p-can-to-drawer-close-privileged-i00'}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def codex_config():
 binary=Path(shutil.which('codex') or '').resolve()
 if not binary.is_file():raise RuntimeError('Codex binary missing')
 version=__import__('subprocess').check_output([str(binary),'--version'],text=True).strip().split()[-1]
 auth=Path(os.environ.get('CODEX_AUTH_JSON_PATH',str(Path.home()/'.codex/auth.json')))
 d=read(auth)
 if d.get('auth_mode')!='chatgpt' or not (d.get('tokens') or {}).get('access_token') or d.get('OPENAI_API_KEY'):raise RuntimeError('ChatGPT subscription login required; no API-key fallback')
 os.environ['VLABENCH_CODEX_BINARY']=str(binary)
 for key in SECRET_ENV:os.environ.pop(key,None)
 return dict(import_path='codex_subscription.agent:SubscriptionCodex',model_name='openai/gpt-6-luna',override_timeout_sec=3600,override_setup_timeout_sec=300,
  kwargs=dict(version=version,reasoning_effort='high',web_search='disabled',config=dict(model_provider='openai',forced_login_method='chatgpt',cli_auth_credentials_store='file',chatgpt_base_url='https://chatgpt.com/backend-api',model_reasoning_effort='high',features={'shell_snapshot':False})))

async def trial(row,mode,role,out):
 from harbor.job import Job
 from harbor.models.job.config import JobConfig
 from harbor.trial.hooks import TrialEvent
 from harbor.models.task.task import Task
 m=row['modes'][mode];task=ROOT/m['path'];name=task.name+'-'+role
 if m['blocked_reason']:return dict(task_id=m['task_id'],status='not_evaluated',reason=m['blocked_reason'])
 if (out/name).exists():raise RuntimeError('Attempt exists; no retry or overwrite: '+str(out/name))
 agent=codex_config() if role=='codex' else {'name':'oracle' if role=='oracle' and mode=='unlimited' else 'nop'}
 cfg=dict(job_name=name,jobs_dir=str(out),n_attempts=1,n_concurrent_trials=1,quiet=True,retry=dict(max_retries=0),environment=dict(type='docker',delete=True),agents=[agent],tasks=[dict(path=str(task))])
 job=await Job.create(JobConfig.model_validate(cfg));limited=mode=='limited';state={'phase':'formal' if role=='codex' else 'smoke','role':role,'task_id':m['task_id'],'task_checksum':Task(task).checksum,'harbor_version':importlib.metadata.version('harbor'),'model_requests':None if role=='codex' else 0}
 async def hard_deadline(ids):
  await asyncio.sleep(3600);state['timed_out']=True
  # Process kill is independent of a sidecar lock or a long model/tool request.
  await command('docker','stop','--time','0',ids['main'],check=False,timeout=30)
 async def start(event):
  ids=await containers(event,limited);state['isolation']=await isolate(ids,limited)
  if limited:
   state['public_probe']=await public_probe(ids)
   await command('docker','exec',ids['sim'],'python','/private/control.py','start')
  else:
   # Cold-start/preflight before granting the agent permission. Later new Sessions
   # and reset initialization are the agent's exploration work and consume time.
   mod='vlb_traj' if row['benchmark']=='vlabench' else 'mw_runtime' if row['benchmark']=='metaworldplus' else 'casa_traj' if 'navigation' in row['source_slug'] else 'casa_runtime'
   await command('docker','exec',ids['main'],'sh','-c',f'python /opt/rcb-setup/warm_session.py {mod} > /tmp/rcb-unlimited-setup.log 2>&1 &')
   ready_code="import time;from pathlib import Path; p=Path('/tmp/rcb-unlimited-ready'); deadline=time.monotonic()+900\nwhile not p.exists():\n if time.monotonic()>deadline:raise RuntimeError('native setup did not become ready')\n time.sleep(.1)\nprint('simulator_ready')"
   state['ready']=await command('docker','exec',ids['main'],'python','-c',ready_code,timeout=910)
  state['started_at']=now();state['monotonic_start']=time.monotonic();state['watchdog']=asyncio.create_task(hard_deadline(ids))
  if not limited and role=='nop':
   # No robot controls: exercise privileged queries, same-instance reset and RGB
   # through the preinitialized public Session; empty submission must still fail.
   code=f"import json,numpy as np;from {mod} import Session; s=Session(); before=s.instance_sha if hasattr(s,'instance_sha') else None; obs=s.state() if '{mod}'=='vlb_traj' else s.observe(); s.reset(); assert before==(s.instance_sha if hasattr(s,'instance_sha') else None); rgb=s.observe()['rgb'] if '{mod}'=='vlb_traj' else s.frame() if '{mod}'=='casa_traj' else s.render(); assert np.asarray(rgb).ndim==3; s.close(); print(json.dumps(dict(privileged_query=True,same_instance_reset=True,rgb=True,warmed_proxy=True)))"
   state['unlimited_probe']=json.loads((await command('docker','exec',ids['main'],'python','-c',code,timeout=900)).strip().splitlines()[-1])
  if limited and role=='oracle':
   source=resolve(row['source']);ref=source/'solution/oracle.npz'
   if not ref.exists():ref=source/'reference_oracle/trajectory.npz'
   if not ref.exists():raise RuntimeError('No frozen reference trajectory for smoke '+row['source_slug'])
   await command('docker','cp',ref,ids['sim']+':/tmp/reference.npz')
   actions=await command('docker','exec',ids['sim'],'python','-c',"import json,numpy as np; print(json.dumps(np.load('/tmp/reference.npz',allow_pickle=False)['actions'].tolist()))")
   code='''import json,sys
import limited_client as r
for a in json.load(sys.stdin):
 if r.status()['ended']:break
 r.step(a)
print(json.dumps(r.status()))
'''
   state['driver']=json.loads(await command('docker','exec','-i',ids['main'],'python','-c',code,input=actions,timeout=3600))
 async def stop(event):
  state['ended_at']=now();state['agent_seconds']=time.monotonic()-state.get('monotonic_start',time.monotonic())
  state['timed_out']=state.get('timed_out',False) or state['agent_seconds']>=3600
  if state.get('watchdog'):state['watchdog'].cancel()
  ids=await containers(event,limited)
  if limited:
   await command('docker','exec',ids['sim'],'python','/private/control.py','stop',timeout=90)
   await command('docker','stop','--time','0',ids['main'],check=False)
   await command('docker','exec',ids['sim'],'python','/private/control.py','seal',timeout=120)
  else:
   # Kill all background agent children, then restart for the trusted verifier.
   await command('docker','restart','--time','0',ids['main'])
 job.add_hook(TrialEvent.AGENT_START,start);job.add_hook(TrialEvent.AGENT_END,stop)
 try:await job.run()
 finally:
  watch=state.pop('watchdog',None)
  if watch:watch.cancel()
  state.pop('monotonic_start',None);write(out/(name+'-lifecycle.json'),state)
 results=list((out/name).glob('*/result.json'))
 if len(results)!=1:raise RuntimeError('Missing trial result')
 d=read(results[0]);reward=(d.get('verifier_result') or {}).get('rewards',{});state.update(reward=reward,result=str(results[0].relative_to(ROOT)))
 exc=d.get('exception_info');state['exception']=exc
 if role=='oracle' and not limited:
  exit_file=results[0].parent/'agent/exit-code.txt'
  # Harbor 0.23 writes exit-code.txt only for nonzero exits.
  state['oracle_exit_code']=int(exit_file.read_text().strip()) if exit_file.exists() else 0 if (exit_file.parent/'oracle.txt').exists() and not exc else None
 state['status']='timeout' if state.get('timed_out') or reward.get('timeout') or (exc and 'Timeout' in str(exc.get('exception_type'))) else 'infrastructure_failure' if exc or reward.get('grader_error') else 'success' if reward.get('success')==1 else 'task_failure'
 if role!='codex':state['passed']=not exc and reward.get('success')==(1 if role=='oracle' else 0) and not reward.get('grader_error') and (reward.get('deterministic')==1 if limited or role=='oracle' else reward.get('missing_trajectory')==1)
 if role=='oracle' and not limited and state.get('oracle_exit_code')!=0:
  state['passed']=False;state['status']='baseline_failure'
 write(out/(name+'-lifecycle.json'),state);print(row['benchmark'],mode,role,state.get('passed',state['status']),flush=True);return state
async def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['list','smoke','run']);p.add_argument('--benchmark',choices=STABLE);p.add_argument('--mode',choices=['limited','unlimited','both'],default='both');p.add_argument('--task');p.add_argument('--role',choices=['oracle','nop','both'],default='both');p.add_argument('--output',type=Path);a=p.parse_args()
 rs=[r for r in rows() if not a.benchmark or r['benchmark']==a.benchmark]
 if a.task:rs=[r for r in rs if a.task in (r['source_slug'],*(Path(m['path']).name for m in r['modes'].values()))]
 if a.action=='list':
  print(json.dumps([{k:r[k] for k in ('benchmark','source_slug','seed','modes')} for r in rs],indent=2));return
 if not a.output:raise SystemExit('--output required: a new experiment directory')
 if a.action=='run' and not a.task:raise SystemExit('Explicit --task required; no accidental full-suite model dispatch')
 if a.action=='smoke' and not a.task:rs=[r for r in rs if r['source_slug']==STABLE[r['benchmark']]]
 if not rs:raise SystemExit('No matching task')
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);results=[]
 for row in rs:
  for mode in ('limited','unlimited') if a.mode=='both' else (a.mode,):
   for role in (('oracle','nop') if a.role=='both' else (a.role,)) if a.action=='smoke' else ('codex',):
    try:result=await trial(row,mode,role,out)
    except Exception as e:result=dict(task=row['source_slug'],mode=mode,role=role,passed=False,error_type=type(e).__name__,error=str(e))
    results.append(result);write(out/'summary.json',results)
 if any(r.get('passed') is False for r in results):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
