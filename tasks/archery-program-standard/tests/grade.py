"""Trusted artifact grader (separate sandbox, no network): reads what the sim service wrote (/data/final.json: the
round, the fresh-process replay, the accounting; /data/think_usage.json: the metering proxy). Technical failures
(simulator, replay, metering or model-API failure) are not low scores: valid_trial = 0. success = a valid, complete
round with total >= the success line (110 of 120); the total is always reported."""
import json
import os
import shutil
from pathlib import Path

# Official configurations of this parameterized task (scripts/olympiad/archery/spec.py)
OFFICIAL_SEEDS = [20260929, 2, 3]


def evaluate(d, u):
    det = bool(d.get('deterministic'))
    ready = bool(d.get('graded_ready'))
    total = int(d.get('total') or 0)
    replay_ok = ready and det and d.get('replay_total') == total
    model = d.get('player_mode') == 'model'
    meter_error = bool(d.get('meter_error')) or (model and bool(d.get('started')) and
                                                 (not u.get('epoch') or u.get('requests', 0) < 1))
    proxy_error = bool(d.get('proxy_error'))   # the server's model-API rule (api_errors.py): unrecovered, or > 5 transient
    sim_error = bool(d.get('sim_error') or d.get('reason') == 'error')
    replay_error = bool(d.get('finalize_error')) or not replay_ok
    valid = replay_ok and not (meter_error or proxy_error or sim_error or replay_error)
    complete = bool(d.get('round_complete'))
    line = int(d.get('success_min_total') or 110)
    arrows = [v for e in (d.get('arrow_scores') or []) for v in e]
    ends = list(d.get('end_scores') or []) + [0] * 4
    try:
        seed = int(d.get('seed'))
    except (TypeError, ValueError):
        seed = 0
    out = {'success': int(valid and complete and total >= line), 'valid_trial': int(valid),
           'technical_failure': int(not valid), 'sim_error': int(sim_error), 'replay_error': int(replay_error),
           'meter_error': int(meter_error), 'proxy_error': int(proxy_error), 'grader_error': 0, 'missing_log': 0,
           'deterministic': int(det), 'finalized': int(ready), 'seed': seed, 'official_config': int(seed in OFFICIAL_SEEDS),
           'total': total, 'max_total': int(d.get('max_total') or 120), 'success_min_total': line,
           'round_complete': int(complete), 'clock_forfeit': int(bool(d.get('clock_forfeit'))),
           'started': int(bool(d.get('started'))), 'n_x': int(d.get('n_x') or 0),
           **{f'end{i + 1}': int(ends[i]) for i in range(4)},
           'arrows_shot': int(d.get('arrows_shot') or 0), 'misses': sum(1 for v in arrows if v == 0),
           'tens': sum(1 for v in arrows if v == 10),
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
