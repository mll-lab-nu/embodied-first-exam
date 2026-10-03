"""Trusted artifact grader (separate sandbox, no network): reads what the sim service wrote (/data/final.json: the
match, the fresh-process replay, the accounting; /data/think_usage.json: the metering proxy). Technical failures
(simulator, replay, metering or model-API failure) are not losses: valid_trial = 0. success = a valid match won (best of 3 legs)."""
import json
import os
import shutil
from pathlib import Path

# Official configurations of this parameterized task (scripts/olympiad/darts/spec.py)
OFFICIAL_SEEDS = {1: [5011, 5012, 5013], 2: [5021, 5022, 5023], 3: [5031, 5032, 5033], 4: [5041, 5042, 5043]}


def official_config(d):
    try:
        level, seed = int(d.get('level')), int(d.get('seed'))
    except (TypeError, ValueError):
        return 0
    return int(seed in OFFICIAL_SEEDS.get(level, []))


def evaluate(d, u):
    det = bool(d.get('deterministic'))
    ready = bool(d.get('graded_ready'))
    replay_ok = (ready and det and d.get('replay_remaining') == [d.get('you_remaining'), d.get('opponent_remaining')]
                 and d.get('replay_legs') == d.get('legs'))
    model = d.get('player_mode') == 'model'
    meter_error = bool(d.get('meter_error')) or (model and bool(d.get('started')) and
                                                 (not u.get('epoch') or u.get('requests', 0) < 1))
    proxy_error = bool(d.get('proxy_error'))   # the server's model-API rule (api_errors.py): unrecovered, or > 5 transient
    sim_error = bool(d.get('sim_error') or d.get('reason') == 'error')
    replay_error = bool(d.get('finalize_error')) or not replay_ok
    valid = replay_ok and not (meter_error or proxy_error or sim_error or replay_error)
    won = bool(d.get('won'))
    sy, so = d.get('stats_you') or {}, d.get('stats_opponent') or {}
    out = {'success': int(valid and won), 'won': int(won), 'valid_trial': int(valid), 'technical_failure': int(not valid),
           'sim_error': int(sim_error), 'replay_error': int(replay_error), 'meter_error': int(meter_error),
           'proxy_error': int(proxy_error), 'grader_error': 0, 'missing_log': 0, 'deterministic': int(det),
           'finalized': int(ready), 'level': int(d.get('level') or 0), 'seed': int(d.get('seed') or 0),
           'official_config': official_config(d), 'match_over': int(bool(d.get('match_over'))),
           'clock_forfeit': int(bool(d.get('clock_forfeit'))), 'started': int(bool(d.get('started'))),
           'you_legs': int((d.get('legs') or [0, 0])[0]), 'opponent_legs': int((d.get('legs') or [0, 0])[1]),
           'you_remaining': int(d.get('you_remaining') or 0), 'opponent_remaining': int(d.get('opponent_remaining') or 0),
           'darts': int(sy.get('darts', 0)), 'visits': int(sy.get('visits', 0)),
           'three_dart_avg': float(sy.get('three_dart_avg', 0.0)), 'busts': int(sy.get('busts', 0)),
           'trebles': int(sy.get('trebles', 0)), 'opponent_visits': int(so.get('visits', 0)),
           'opponent_three_dart_avg': float(so.get('three_dart_avg', 0.0)),
           'clock_used_s': float(d.get('clock_used_s') or 0.0), 'n_reviews': int(d.get('n_reviews') or 0),
           'n_act': int(d.get('n_act') or 0), 'n_observe': int(d.get('n_observe') or 0),
           'refused_busy': int(d.get('refused_busy') or 0), 'refused_not_model': int(d.get('refused_not_model') or 0),
           'elapsed_s': float(d.get('elapsed_s') or 0.0), 'video_rendered': int(bool(d.get('video'))),
           'metered_requests': int(u.get('requests', 0)), 'metered_output_tokens': int(u.get('output_tokens', 0)),
           'metered_input_tokens': int(u.get('input_tokens', 0)), 'rate_limit_retries': int(u.get('rate_limit_retries', 0)),
           'transient_api_errors': int(d.get('transient_api_errors') or 0),
           'unrecovered_api_errors': int(d.get('unrecovered_api_errors') or 0)}
    return out


def main():
    log = Path(os.environ.get('RCB_LOG', '/logs/verifier')); log.mkdir(parents=True, exist_ok=True)
    data = Path(os.environ.get('RCB_DATA', '/data'))
    try:
        d = json.loads((data / 'final.json').read_text())
        try:
            u = json.loads((data / 'think_usage.json').read_text())
        except (OSError, ValueError):
            u = {}
        out = evaluate(d, u)
        for name in ('replay.mp4', 'trajectory.json', 'episode.jsonl', 'replay_check.json', 'think_calls.jsonl'):
            if (data / name).exists():
                shutil.copyfile(data / name, log / name)
    except Exception:  # noqa: BLE001
        import traceback; traceback.print_exc()
        out = {'success': 0, 'valid_trial': 0, 'technical_failure': 1, 'grader_error': 1,
               'missing_log': int(not (data / 'final.json').exists())}
    assert all(isinstance(v, (int, float)) for v in out.values())
    (log / 'reward.txt').write_text(str(out['success']) + '\n')
    (log / 'reward.json').write_text(json.dumps(out, allow_nan=False))
    print(out)


if __name__ == '__main__':
    main()
