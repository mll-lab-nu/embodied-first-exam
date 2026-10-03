"""Trusted artifact grader: technical failures are distinct from normal match losses; video is optional."""
import json
import os
from pathlib import Path
import shutil


def evaluate(d, u):
    pf, pa = int(d.get('points_for', 0)), int(d.get('points_against', 0))
    replay = d.get('replay_score') or [-1, -1]
    ready = bool(d.get('graded_ready'))
    det = bool(d.get('deterministic'))
    targets = bool(d.get('replay_joint_targets_equal'))
    replay_ok = ready and det and targets and list(replay) == [pf, pa]
    sim_error = bool(d.get('sim_error') or d.get('reason') == 'error')
    replay_error = bool(d.get('finalize_error')) or not replay_ok
    model = d.get('player_mode') == 'model'
    meter_error = bool(d.get('meter_error')) or (model and (not u.get('epoch') or u.get('requests', 0) < 1))
    proxy_error = bool(d.get('proxy_error'))   # the server's model-API rule (api_errors.py): unrecovered, or > 5 transient
    timing_error = bool(d.get('timing_invalid'))
    valid = replay_ok and not (replay_error or sim_error or meter_error or proxy_error or timing_error)
    won = bool(d.get('won')) and d.get('winner') == 'you'     # the game always has a winner (no draws)
    lag = d.get('sim_lag') or {}
    delays = d.get('act_delay_steps') or []
    out = {'success': int(valid and won), 'won': int(won), 'valid_trial': int(valid),
           'technical_failure': int(not valid), 'sim_error': int(sim_error), 'replay_error': int(replay_error),
           'meter_error': int(meter_error), 'proxy_error': int(proxy_error), 'timing_invalid': int(timing_error),
           'grader_error': int(sim_error or replay_error or meter_error), 'missing_log': 0,
           'points_for': pf, 'points_against': pa, 'replay_points_for': int(replay[0]),
           'replay_points_against': int(replay[1]), 'deterministic': int(det),
           'replay_joint_targets_equal': int(targets), 'finalized': int(ready), 'revision': 5,
           'timing_lag_enforced': int(d.get('max_lag_s') is not None),
           'match_over': int(d.get('reason') == 'match_over'), 'video_rendered': int(bool(d.get('video'))),
           'act_delay_steps_max': max(delays, default=0),
           'metered_requests': int(u.get('requests', 0)), 'metered_output_tokens': int(u.get('output_tokens', 0)),
           'metered_input_tokens': int(u.get('input_tokens', 0)), 'rate_limit_retries': int(u.get('rate_limit_retries', 0)),
           'transient_api_errors': int(d.get('transient_api_errors') or 0),
           'unrecovered_api_errors': int(d.get('unrecovered_api_errors') or 0)}
    direct = {'level':'level', 'seed':'seed', 'slowdown':'slowdown', 'our_shots':'our_shots', 'balls_to_you':'our_legs',
              'good_shots':'returns', 'n_decisions':'n_decisions', 'refused_not_model':'refused_not_model',
              'dropped_acts':'dropped_acts', 'act_rule_wait_max_s':'act_rule_wait_max_s',
              'act_rule_wait_mean_s':'act_rule_wait_mean_s', 'n_actions':'n_actions', 'sim_steps':'physics_steps',
              'steps':'steps', 'n_reviews':'n_reviews', 'n_calls':'n_calls', 'n_observe':'n_observe',
              'n_act':'n_act', 'n_wait':'n_wait', 'elapsed_s':'elapsed_s', 'max_lag_s':'max_lag_s'}
    for name, key in direct.items(): out[name] = float(d.get(key) or 0)
    out['official_config'] = official_config(d)
    for name, key in {'sim_lag_late_max_s':'late_max_s', 'sim_lag_late_p99_s':'late_p99_s',
                      'sim_lag_frac_late_over_1_period':'frac_steps_late_over_1_period',
                      'sim_effective_slowdown':'effective_slowdown', 'sim_run_wall_s':'run_wall_s'}.items():
        out[name] = float(lag.get(key) or 0)
    return out


# Official configurations of this parameterized task (scripts/olympiad/generate.py).
OFFICIAL_SEEDS = {1: [101, 111, 121], 2: [202, 212, 222], 3: [303, 313, 323], 4: [404, 414, 424]}
OFFICIAL_SLOWDOWNS = [1, 2, 5, 10, 20]


def official_config(d):
    try:
        level, seed, s = int(d.get('level')), int(d.get('seed')), float(d.get('slowdown'))
    except (TypeError, ValueError):
        return 0
    return int(seed in OFFICIAL_SEEDS.get(level, []) and s in OFFICIAL_SLOWDOWNS)


def main():
    log = Path(os.environ.get('RCB_LOG', '/logs/verifier')); log.mkdir(parents=True, exist_ok=True)
    data = Path(os.environ.get('RCB_DATA', '/data'))
    try:
        d = json.loads((data/'final.json').read_text())
        try: u = json.loads((data/'think_usage.json').read_text())
        except (OSError, ValueError): u = {}
        out = evaluate(d, u)
        for name in ('replay.mp4','trajectory.json','episode.jsonl','replay_check.json','think_calls.jsonl'):
            if (data/name).exists(): shutil.copyfile(data/name, log/name)
    except Exception:
        import traceback; traceback.print_exc()
        out = {'success': 0, 'valid_trial': 0, 'technical_failure': 1, 'grader_error': 1,
               'missing_log': int(not (data/'final.json').exists())}
    (log/'reward.txt').write_text(str(out['success'])+'\n')
    (log/'reward.json').write_text(json.dumps(out, allow_nan=False))
    print(out)


if __name__ == '__main__':
    main()
