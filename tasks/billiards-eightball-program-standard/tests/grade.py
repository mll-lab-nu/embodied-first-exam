"""Trusted artifact grader (separate sandbox, no network): technical failures are kept apart from match losses.

success = 1 iff the player won a valid 8-ball game: finalized, the fresh-process replay reproduces the result and the
state hash, no simulator, model-API or metering failure, and the clock did not run out."""
import json
import os
import shutil
from pathlib import Path

# Official configurations of this parameterized task (scripts/olympiad/billiards/spec.py).
OFFICIAL_SEEDS = {1: [1, 3, 6], 2: [2, 4, 8]}


def official_config(d):
    try:
        level, seed = int(d.get('level')), int(d.get('seed'))
    except (TypeError, ValueError):
        return 0
    return int(seed in OFFICIAL_SEEDS.get(level, []))


def evaluate(d, u):
    ready = bool(d.get('graded_ready'))
    det = bool(d.get('deterministic'))
    replay_ok = ready and det and d.get('replay_winner') == {'you': 0, 'opponent': 1}.get(d.get('winner'))
    sim_error = bool(d.get('sim_error') or d.get('reason') == 'error')
    replay_error = bool(d.get('finalize_error')) or not replay_ok
    model = d.get('player_mode') == 'model'
    meter_error = bool(d.get('meter_error')) or (model and bool(d.get('started')) and
                                                 (not u.get('epoch') or u.get('requests', 0) < 1))
    proxy_error = bool(d.get('proxy_error'))   # the server's model-API rule (api_errors.py): unrecovered, or > 5 transient
    valid = replay_ok and not (replay_error or sim_error or meter_error or proxy_error)
    clock_forfeit = d.get('reason') == 'clock_expired'
    won = bool(d.get('won')) and d.get('winner') == 'you' and d.get('reason') == 'match_over'
    shots = d.get('shots') or []
    ours = [s for s in shots if s.get('player') == 0]
    return {'success': int(valid and won), 'won': int(won), 'valid_trial': int(valid), 'technical_failure': int(not valid),
            'sim_error': int(sim_error), 'replay_error': int(replay_error), 'meter_error': int(meter_error),
            'proxy_error': int(proxy_error), 'grader_error': 0, 'missing_log': 0,
            'level': int(d.get('level') or 0), 'seed': int(d.get('seed') or 0), 'official_config': official_config(d),
            'game_over': int(bool(d.get('game_over'))), 'lost': int(d.get('winner') == 'opponent'),
            'clock_tiebreak': int(bool(d.get('tiebreak'))),
            'your_balls_left': int(d.get('your_balls_left', 7)), 'opponent_balls_left': int(d.get('opponent_balls_left', 7)),
            'deterministic': int(det), 'finalized': int(ready), 'match_over': int(d.get('reason') == 'match_over'),
            'clock_forfeit': int(clock_forfeit), 'clock_left_s': float(d.get('clock_left_s') or 0.0),
            'our_shots': len(ours), 'opponent_shots': len(shots) - len(ours),
            'our_pots': int(sum(len(s.get('potted') or []) for s in ours if not s.get('foul'))),
            'our_fouls': int(sum(1 for s in ours if s.get('foul'))),
            'n_decisions': int(d.get('n_decisions') or 0), 'n_reviews': int(d.get('n_reviews') or 0),
            'refused_busy': int(d.get('refused_busy') or 0), 'refused_not_model': int(d.get('refused_not_model') or 0),
            'video_rendered': int(bool(d.get('video'))), 'elapsed_s': float(d.get('elapsed_s') or 0.0),
            'metered_requests': int(u.get('requests', 0)), 'metered_output_tokens': int(u.get('output_tokens', 0)),
            'metered_input_tokens': int(u.get('input_tokens', 0)), 'rate_limit_retries': int(u.get('rate_limit_retries', 0)),
           'transient_api_errors': int(d.get('transient_api_errors') or 0),
           'unrecovered_api_errors': int(d.get('unrecovered_api_errors') or 0)}


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
        for name in ('replay.mp4', 'trajectory.json', 'episode.jsonl', 'replay_check.json', 'think_calls.jsonl'):
            if (data/name).exists():
                shutil.copyfile(data/name, log/name)
    except Exception:
        import traceback; traceback.print_exc()
        out = {'success': 0, 'valid_trial': 0, 'technical_failure': 1, 'grader_error': 1,
               'missing_log': int(not (data/'final.json').exists())}
    (log/'reward.txt').write_text(str(out['success'])+'\n')
    (log/'reward.json').write_text(json.dumps(out, allow_nan=False))
    print(out)


if __name__ == '__main__':
    main()
