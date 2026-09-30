"""Fresh-process replay of the sealed limited episode with the verifier-owned runtime."""
import argparse
import json
from pathlib import Path
import sys
import traceback
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mw_runtime import Session, MAX_ACTIONS, integration, snapshot
from archive import load_npz, digest

SCHEMA = 'rcb-metaworldplus-limited-controls-v1'


def load_controls(path, instance_sha):
    data = load_npz(path)
    if set(data) != {'actions', 'instance_sha', 'schema'} or str(data['schema']) != SCHEMA or str(data['instance_sha']) != instance_sha:
        raise ValueError('wrong trajectory schema or instance')
    actions = data['actions']
    # An empty sealed episode is valid evidence of no attempted control.
    if actions.dtype != np.float64 or actions.ndim != 2 or actions.shape[1] != 4 or len(actions) > MAX_ACTIONS \
            or not np.isfinite(actions).all() or np.any(np.abs(actions) > 1):
        raise ValueError('invalid actions')
    return actions


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--instance', default=str(HERE / 'instance.npz'))
    p.add_argument('--input', default='/recorded/trajectory.npz')
    p.add_argument('--result', required=True)
    args = p.parse_args()
    result = dict(success=False, n_actions=0, completed_controls=0, physics_steps=0, first_success_index=None,
                  error_type=None, invalid_trajectory=False)
    s = Session(args.instance, budget_path=None)
    try:
        result['instance_sha'] = s.instance_sha
        result['initial_state_sha'] = digest(snapshot(s.env))
        try:
            actions = load_controls(args.input, s.instance_sha)
        except Exception:
            result['invalid_trajectory'] = True
            raise
        result['n_actions'] = len(actions)
        dt = s.env.model.opt.timestep
        for i, action in enumerate(actions):
            if result['first_success_index'] is not None:
                raise ValueError('control recorded after native success')
            before = float(s.env.data.time)
            try:
                s.step(action)
            finally:
                result['physics_steps'] += int(round((float(s.env.data.time) - before) / dt))
                result['completed_controls'] = len(s.actions)
            if s.ever_success:
                result['first_success_index'] = i
        native = s.result()
        result.update(success=bool(native['success']), final_success=bool(native['final_success']),
                      final_reward=native['final_reward'], native_info=native['info'])
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc), success=False)
        traceback.print_exc()
    finally:
        try:
            result['state_sha'] = digest(snapshot(s.env))
            np.savez_compressed(args.result + '.state.npz', integration=integration(s.env))
        finally:
            Path(args.result).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
            s.close()


if __name__ == '__main__':
    main()
