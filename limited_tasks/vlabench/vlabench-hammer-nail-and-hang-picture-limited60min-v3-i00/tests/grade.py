"""Score only protected sidecar evidence; two exact fresh replays are mandatory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np


def main():
    root=Path('/recorded'); logs=Path('/logs/verifier'); logs.mkdir(parents=True,exist_ok=True)
    reward=dict(success=0,online_success=0,replay_success=0,deterministic=0,n_actions=0,physics_steps=0,
                missing_trajectory=0,grader_error=0,invalid_trajectory=0,timeout=0,simulation_failure=0)
    details={'evaluation':'limited single episode','state_comparison':'exact sha256 plus zero maximum integration-state difference'}
    start=time.monotonic()
    try:
        if not (root/'episode.json').exists() or not (root/'trajectory.npz').exists():
            reward['missing_trajectory']=1; return
        episode=json.loads((root/'episode.json').read_text()); details['episode']=episode
        if not episode.get('agent_stopped') or not episode['sealed'] or episode['initializations']!=1 or episode['resets']!=0:
            raise ValueError('Episode was not sealed, or initialization/reset count invalid')
        events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
        if any(sum(e['kind']==k for e in events)!=1 for k in ('agent_start','agent_stop','sealed')): raise ValueError('invalid lifecycle journal')
        begins=[e for e in events if e['kind']=='action_begin']
        ends=[e for e in events if e['kind']=='action_end']
        with np.load(root/'trajectory.npz',allow_pickle=False) as archive:
            actions=archive['actions']
        if len(begins)!=len(actions) or len(ends)!=len(actions): raise ValueError('Incomplete action journal')
        if not np.array_equal(np.asarray([e['action'] for e in begins]).reshape(-1,9),actions):
            raise ValueError('Trajectory omits or changes an attempted control')
        if sum(e['physics_steps'] for e in ends)!=episode['physics_steps']: raise ValueError('Physics journal mismatch')
        if len([e for e in events if e['kind']=='agent_start'])!=1: raise ValueError('Missing or repeated start')
        reward.update(online_success=int(episode['online_success']),n_actions=len(actions),
                      physics_steps=episode['physics_steps'],timeout=int((episode['termination_reason']=='timeout' or episode['agent_seconds']>=3600)),
                      simulation_failure=int(episode['termination_reason']=='simulation_failure'))
        details['trajectory_sha256']=hashlib.sha256((root/'trajectory.npz').read_bytes()).hexdigest()
        replays=[]
        for i in range(2):
            result=logs/f'replay-{i}.json'
            command=[sys.executable,'-I','/tests/worker.py','--result',str(result)]
            if i==0 and len(actions): command+=['--video',str(logs/'replay.mp4')]
            with (logs/f'replay-{i}.log').open('w') as log:
                p=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            if p.returncode or not result.exists(): raise RuntimeError('Independent replay worker failed')
            replays.append(json.loads(result.read_text()))
        details['replays']=replays
        if any(r.get('error_type') for r in replays):
            reward['simulation_failure']=int(any(r.get('error_type')=='PhysicsError' for r in replays))
            reward['grader_error']=1; return
        if not all(r['initial_state_sha']==episode['initial_state_sha'] for r in replays): raise ValueError('initial state mismatch')
        from vlb_traj import digest
        if episode['instance_sha']!=digest(json.loads(Path('/tests/instance.json').read_text())): raise ValueError('instance mismatch')
        original=json.loads((root/'online.json').read_text())
        states=[np.load(root/'online.state.npz')['integration']]+[np.load(logs/f'replay-{i}.json.state.npz')['integration'] for i in range(2)]
        difference=max(float(np.max(np.abs(states[0]-s))) for s in states[1:])
        reward['max_abs_state_difference']=difference
        same=(len({original['state_sha'],*[r['state_sha'] for r in replays]})==1 and difference==0)
        same= same and all(r['physics_steps']==episode['physics_steps'] for r in replays)
        reward['deterministic']=int(same)
        reward['replay_success']=int(all(r['success'] for r in replays))
        reward['success']=int(reward['online_success'] and reward['replay_success'] and same and not reward['timeout'] and not reward['simulation_failure'])
    except Exception as exc:
        reward['grader_error']=1; details['error_type']=type(exc).__name__; details['error']=str(exc)
    finally:
        reward['verifier_wall_seconds']=time.monotonic()-start
        (logs/'reward.json').write_text(json.dumps(reward,indent=2)+'\n')
        (logs/'reward.txt').write_text(str(reward['success'])+'\n')
        (logs/'details.json').write_text(json.dumps(details,indent=2)+'\n')
        print(json.dumps(reward))


if __name__=='__main__': main()
