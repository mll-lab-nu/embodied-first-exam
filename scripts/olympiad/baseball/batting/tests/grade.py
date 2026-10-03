"""Trusted artifact grader (wall-clock baseball): technical failures are distinct from ordinary failures to reach the
bases threshold; the video is optional.

success = bases >= threshold AND a valid trial: the fresh-process replay reproduced the bases, the decisions and the
state hash (graded_ready), and there was no simulator, replay, metering or model-API failure. Revision wallclock-3:
scheduling lateness is reported (sim_lag_*), not a disqualification (timing_invalid only if a service sets a cap).
Numeric-only reward.json."""
import json
import os
from pathlib import Path
import shutil


def evaluate(d, u):
    bases, thr = int(d.get('bases') or 0), int(d.get('threshold') or 10 ** 6)
    rep = d.get('replay_bases')
    rep = -1 if rep is None else int(rep)
    ready = bool(d.get('graded_ready'))
    det = bool(d.get('deterministic'))
    decs = bool(d.get('replay_decisions_equal'))
    replay_ok = ready and det and decs and rep == bases
    sim_error = bool(d.get('sim_error') or d.get('reason') == 'error')
    replay_error = bool(d.get('finalize_error')) or not replay_ok
    model = d.get('player_mode') == 'model'
    meter_error = bool(d.get('meter_error')) or (model and (not u.get('epoch') or u.get('requests', 0) < 1))
    proxy_error = bool(d.get('proxy_error'))   # the server's model-API rule (api_errors.py): unrecovered, or > 5 transient
    timing_error = bool(d.get('timing_invalid'))
    valid = replay_ok and not (replay_error or sim_error or meter_error or proxy_error or timing_error)
    passed = bases >= thr
    lag = d.get('sim_lag') or {}
    delays = d.get('act_delay_steps') or []
    out = {'success': int(valid and passed), 'passed': int(passed), 'valid_trial': int(valid),
           'technical_failure': int(not valid), 'sim_error': int(sim_error), 'replay_error': int(replay_error),
           'meter_error': int(meter_error), 'proxy_error': int(proxy_error), 'timing_invalid': int(timing_error),
           'grader_error': int(sim_error or replay_error or meter_error), 'missing_log': 0,
           'bases': bases, 'threshold': thr, 'replay_bases': rep, 'deterministic': int(det),
           'replay_decisions_equal': int(decs), 'finalized': int(ready), 'revision': 3,
           'timing_lag_enforced': int(d.get('max_lag_s') is not None),
           'game_over': int(d.get('reason') == 'game_over'), 'video_rendered': int(d.get('video') is True),
           'act_delay_steps_max': max(delays, default=0),
           'metered_requests': int(u.get('requests', 0)), 'metered_output_tokens': int(u.get('output_tokens', 0)),
           'metered_input_tokens': int(u.get('input_tokens', 0)), 'rate_limit_retries': int(u.get('rate_limit_retries', 0)),
           'transient_api_errors': int(d.get('transient_api_errors') or 0),
           'unrecovered_api_errors': int(d.get('unrecovered_api_errors') or 0)}
    direct = {'level': 'level', 'seed': 'seed', 'slowdown': 'slowdown', 'pa_done': 'pa_done', 'hits': 'hits',
              'walks': 'walks', 'strikeouts': 'strikeouts', 'home_runs': 'home_runs', 'pitches': 'pitches',
              'n_decisions': 'n_decisions', 'refused_not_model': 'refused_not_model', 'dropped_acts': 'dropped_acts',
              'rejected_acts': 'rejected_acts', 'act_rule_wait_max_s': 'act_rule_wait_max_s',
              'act_rule_wait_mean_s': 'act_rule_wait_mean_s', 'n_actions': 'n_actions', 'steps': 'steps',
              'n_reviews': 'n_reviews', 'n_calls': 'n_calls', 'n_observe': 'n_observe', 'n_act': 'n_act',
              'n_wait': 'n_wait', 'elapsed_s': 'elapsed_s', 'max_lag_s': 'max_lag_s'}
    for name, key in direct.items():
        out[name] = float(d.get(key) or 0)
    out['refused_busy'] = float(d.get('refused_busy') or 0)
    out['official_config'] = official_config(d)
    for name, key in {'sim_lag_late_max_s': 'late_max_s', 'sim_lag_late_p99_s': 'late_p99_s',
                      'sim_lag_frac_late_over_1_period': 'frac_steps_late_over_1_period',
                      'sim_step_ms_max': 'step_ms_max', 'sim_commit_ms_max': 'commit_ms_max',
                      'sim_judge_ms_max': 'judge_ms_max', 'sim_next_pitch_ms_max': 'next_pitch_ms_max',
                      'sim_effective_slowdown': 'effective_slowdown', 'sim_run_wall_s': 'run_wall_s'}.items():
        out[name] = float(lag.get(key) or 0)
    return out


# Official configurations of this parameterized task (scripts/olympiad/baseball/spec.py).
OFFICIAL_SEEDS = {1: [301, 311, 321], 2: [302, 312, 322], 3: [303, 313, 323], 4: [304, 314, 324]}
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
        try:
            u = json.loads((data/'think_usage.json').read_text())
        except (OSError, ValueError):
            u = {}
        out = evaluate(d, u)
        for name in ('replay.mp4', 'trajectory.json', 'episode.jsonl', 'replay_check.json', 'think_calls.jsonl',
                     'final.json'):
            if (data/name).exists():
                shutil.copyfile(data/name, log/name)
    except Exception:  # noqa: BLE001
        import traceback; traceback.print_exc()
        out = {'success': 0, 'valid_trial': 0, 'technical_failure': 1, 'grader_error': 1,
               'missing_log': int(not (data/'final.json').exists())}
    (log/'reward.txt').write_text(str(out['success'])+'\n')
    (log/'reward.json').write_text(json.dumps(out, allow_nan=False))
    print(out)


if __name__ == '__main__':
    main()
