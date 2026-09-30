"""Score only sidecar-sealed evidence: online native success AND two exact fresh replays."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPLAY_TIMEOUT = 900


def main():
    root = Path('/recorded'); logs = Path('/logs/verifier'); logs.mkdir(parents=True, exist_ok=True)
    reward = dict(success=0, online_success=0, replay_success=0, deterministic=0, n_actions=0, physics_steps=0,
                  missing_trajectory=0, invalid_trajectory=0, grader_error=0, timeout=0, simulation_failure=0,
                  replay_count=0)
    details = {'evaluation': 'limited single continuous episode',
               'state_comparison': 'source native state hash (integration, model arrays and task caches; navigation source snapshot) of online '
                                   'and two fresh replays, plus zero maximum integration difference'}
    start = time.monotonic()
    try:
        required = ('episode.json', 'events.jsonl', 'trajectory.npz', 'online.json', 'online.state.npz')
        if not all((root / name).is_file() for name in required):
            reward['missing_trajectory'] = 1; details['missing'] = [n for n in required if not (root / n).is_file()]
            return
        from backend import Backend
        # Identity is checked without loading a third simulator.
        config=json.loads((HERE/'backend.json').read_text())
        if config['kind']=='navigation':instance_sha=hashlib.sha256((HERE/'instance.npz').read_bytes()).hexdigest()
        else:
            with np.load(HERE/'instance.npz',allow_pickle=False) as z:instance_sha=str(z['instance_sha'])
        episode = json.loads((root / 'episode.json').read_text()); details['episode'] = episode
        if not episode['sealed'] or not episode['agent_stopped'] or episode['initializations'] != 1 or episode['resets'] != 0:
            raise ValueError('episode not sealed, or initialization/reset count invalid')
        if episode['instance_sha'] != instance_sha:
            raise ValueError('episode instance does not match the verifier instance')
        events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
        begins = [e for e in events if e['kind'] == 'action_begin']
        ends = [e for e in events if e['kind'] == 'action_end']
        with np.load(root / 'trajectory.npz', allow_pickle=False) as archive:
            actions = archive['actions']
            completed_controls = int(np.count_nonzero(archive['completed']))
        if len(begins) != len(actions) or len(ends) != len(actions) or episode['n_actions'] != len(actions):
            raise ValueError('incomplete action journal')
        if len(actions) and not np.array_equal(np.asarray([e['action'] for e in begins], dtype=np.float64).reshape(actions.shape), actions):
            raise ValueError('trajectory omits or changes an attempted control')
        if sum(e['physics_steps'] for e in ends) != episode['physics_steps']:
            raise ValueError('physics journal mismatch')
        if [e['kind'] for e in events].count('agent_start') != 1 or [e['kind'] for e in events].count('sealed') != 1:
            raise ValueError('missing or repeated start/seal')
        if [e['kind'] for e in events].count('agent_stop') != 1:
            raise ValueError('missing or repeated agent stop')
        reward.update(online_success=int(episode['online_success']), n_actions=len(actions),
                      physics_steps=episode['physics_steps'], timeout=int(episode['termination_reason'] == 'timeout' or episode['agent_seconds'] >= episode['limit_seconds']),
                      simulation_failure=int(episode['termination_reason'] == 'simulation_failure'))
        details['trajectory_sha256'] = hashlib.sha256((root / 'trajectory.npz').read_bytes()).hexdigest()
        replays = []
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'LD_PRELOAD')}
        for i in range(2):
            target = logs / f'replay-{i}.json'
            with (logs / f'replay-{i}.log').open('w') as log:
                proc = subprocess.run([sys.executable, '-I', str(HERE / 'worker.py'), '--input', str(root / 'trajectory.npz'), '--result', str(target)] + (['--video',str(logs/'replay.mp4')] if i==1 else []),
                                      stdout=log, stderr=subprocess.STDOUT, env=env, cwd='/', timeout=REPLAY_TIMEOUT)
            if proc.returncode or not target.is_file():
                raise RuntimeError('independent replay worker failed')
            replays.append(json.loads(target.read_text()))
        reward['replay_count'] = 2
        details['replays'] = replays
        if any(r.get('invalid_trajectory') for r in replays):
            reward['invalid_trajectory'] = 1
        online = json.loads((root / 'online.json').read_text())
        states = [np.load(root / 'online.state.npz', allow_pickle=False)['integration']] + \
                 [np.load(logs / f'replay-{i}.json.state.npz', allow_pickle=False)['integration'] for i in range(2)]
        same_shape = all(s.shape == states[0].shape for s in states[1:])
        difference = max(float(np.max(np.abs(states[0] - s))) for s in states[1:]) if same_shape else None
        if difference is not None: reward['max_abs_state_difference'] = difference
        checks = dict(
            state_sha=len({online['state_sha'], *[r.get('state_sha') for r in replays]}) == 1,
            integration_difference_zero=difference == 0,
            initial_state=all(r.get('initial_state_sha') == episode['initial_state_sha'] for r in replays),
            physics_steps=all(r['physics_steps'] == episode['physics_steps'] for r in replays),
            completed_controls=all(r['completed_controls'] == completed_controls == episode['completed_controls'] for r in replays),
            first_success_index=all(r.get('first_success_index') == episode.get('first_success_index') for r in replays),
            online_success_matches=all(bool(r['success']) == bool(episode['online_success']) for r in replays
                                       if not r.get('error_type')))
        details['determinism_checks'] = checks
        reward['deterministic'] = int(all(checks.values()))
        if any(r.get('error_type') for r in replays) and not reward['simulation_failure']:
            reward['grader_error'] = int(not reward['invalid_trajectory'])
        reward['replay_success'] = int(all(r['success'] for r in replays))
        reward['success'] = int(reward['online_success'] and reward['replay_success'] and reward['deterministic']
                                and not reward['timeout'] and not reward['simulation_failure'] and not any(r.get('initial_success') for r in replays))
    except Exception as exc:
        reward['grader_error'] = 1; details['error_type'] = type(exc).__name__; details['error'] = str(exc)
    finally:
        reward['verifier_wall_seconds'] = time.monotonic() - start
        (logs / 'reward.json').write_text(json.dumps(reward, indent=2) + '\n')
        (logs / 'reward.txt').write_text(str(reward['success']) + '\n')
        (logs / 'details.json').write_text(json.dumps(details, indent=2, default=str) + '\n')
        print(json.dumps(reward))


if __name__ == '__main__':
    main()
