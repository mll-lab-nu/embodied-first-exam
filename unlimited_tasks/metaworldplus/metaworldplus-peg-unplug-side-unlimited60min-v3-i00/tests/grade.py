"""Independent replay using verifier-owned adapter, instance and subprocesses."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from mw_runtime import load_instance,load_trajectory
p=argparse.ArgumentParser();p.add_argument('--traj',default='/app/output/trajectory.npz');p.add_argument('--logs',default='/logs/verifier');a=p.parse_args()
out=Path(a.logs);out.mkdir(parents=True,exist_ok=True);start=time.monotonic()
r=dict(success=0,deterministic=0,missing_trajectory=0,invalid_trajectory=0,grader_error=0)
try:
 if not Path(a.traj).is_file():r['missing_trajectory']=1
 else:
  _,sha=load_instance(HERE/'instance.npz')
  try:actions=load_trajectory(a.traj,sha)
  except Exception:r['invalid_trajectory']=1;actions=None
  if actions is not None:
   results=[]
   for i in range(2):
    target=out/f'replay-{i}.json'
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','LD_PRELOAD')}
    with (out/f'replay-{i}.log').open('w') as log:
     subprocess.run([sys.executable,'-I',str(HERE/'worker.py'),'--instance',str(HERE/'instance.npz'),'--trajectory',str(Path(a.traj).resolve()),'--output',str(target)],check=True,stdout=log,stderr=subprocess.STDOUT,env=env,cwd='/',timeout=3600)
    results.append(json.loads(target.read_text()))
   states=[np.load(out/f'replay-{i}.json.state.npz',allow_pickle=False)['integration'] for i in range(2)]
   exact=results[0]['state_sha']==results[1]['state_sha']
   r.update(success=int(exact and all(x['success'] for x in results)),deterministic=int(exact),n_actions=len(actions),sim_steps=sum(x['sim_steps'] for x in results),physics_steps=sum(x['physics_steps'] for x in results),final_success=int(results[0]['final_success']),final_reward=results[0]['final_reward'],max_abs_state_difference=float(np.max(abs(states[0]-states[1]))),replay_count=2)
except Exception as exc:
 import traceback
 r['grader_error']=1;(out/'error.txt').write_text(traceback.format_exc())
r['verifier_wall_seconds']=time.monotonic()-start
(out/'reward.json').write_text(json.dumps(r,indent=2)+'\n');(out/'reward.txt').write_text(str(r['success'])+'\n');print(json.dumps(r))
