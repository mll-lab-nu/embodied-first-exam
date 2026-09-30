"""Real native MetaWorld execution past the old horizon, plus two fresh replays."""
import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/tools')
from mw_runtime import Session
s=Session('/tools/instance.npz',budget_path=None)
for _ in range(501):s.step([0,0,0,-1])
s.save('/out/trajectory.npz');online=s.result();s.close()
results=[]
for i in range(2):
 target=f'/out/replay-{i}.json'
 subprocess.run([sys.executable,'/tools/mw_runtime.py','--instance','/tools/instance.npz','--trajectory','/out/trajectory.npz','--output',target],check=True,stdout=subprocess.DEVNULL)
 results.append(json.loads(Path(target).read_text()))
assert online['n_actions']==501 and all(r['n_actions']==501 for r in results)
assert len({online['state_sha'],*[r['state_sha'] for r in results]})==1
Path('/out/result.json').write_text(json.dumps(dict(passed=True,actions=501,physics_steps=2505,old_horizon=500,online_replay_exact=True,model_requests=0),indent=2)+'\n')
print('501 controls + two independent exact replays PASS')
