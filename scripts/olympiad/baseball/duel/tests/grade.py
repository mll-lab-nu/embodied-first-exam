"""Numeric-only symmetric grading of the baseball duel from the isolated trusted simulator artifacts.

success = a valid game: played out (or won by a review forfeit), the fresh-process replay reproduced the state hash,
the score, the commands and the step count, and there was no simulator, model-API or metering failure. The winner is
A_won / B_won (more runs; level after the extra innings: the winner of the last pitch; no draws; a valid game
has exactly one winner); A_runs / B_runs (also A_points / B_points) are the scores."""
import json
import os
import shutil
from pathlib import Path

DATA = Path(os.environ.get('RCB_DATA', '/data'))
LOG = Path(os.environ.get('RCB_LOG', '/logs/verifier')); LOG.mkdir(parents=True, exist_ok=True)
OFFICIAL_SLOWDOWNS = [10, 20]   # official configurations of the parameterized duel


def grade(d, r, t):
    replay = (d['state_sha'] == r['state_sha'] and d['score'] == r['score'] and
              d['decisions_sha'] == r['decisions_sha'] and d['source_sha'] == r['source_sha'] == t['source_sha'] and
              d['seed'] == r['seed'] == t['seed'] and d['first_batter'] == r['first_batter'] == t['first_batter'] and
              d['revision'] == r['revision'] == t['revision'] == 'baseball-duel-2' and
              d['steps'] == r['steps'] == t['k_end'] and len(t['commands']) == sum(
                  d['seats'][s]['applied'] for s in ('A', 'B')))
    game = d['reason'] == 'game_over' and r['done'] and d['winner'] in ('A', 'B')
    forfeit = (d['reason'] == 'ready_timeout' and d.get('forfeiting') in ('A', 'B') and all(d['joined'].values()) and
               d['winner'] != d['forfeiting'] and d['winner'] in ('A', 'B'))
    errors = bool(d.get('errors') or any(d['meter_error'].values()) or any(d['proxy_error'].values()))
    valid = bool(d['valid_trial'] and d['finalized'] and d['graded_ready'] and replay and (game or forfeit) and not errors)
    out = dict(success=int(valid), valid_trial=int(valid), technical_failure=int(not valid), grader_error=0,
               missing_log=0, deterministic=int(replay), game_over=int(game), ready_forfeit=int(forfeit),
               decided_by_last_pitch=int(d.get('decided_by') == 'last pitch'), timing_invalid=0, steps=d['steps'],
               pitches=d['pitches'], plate_appearances=d['plate_appearances'], seed=d['seed'],
               first_batter_A=int(d['first_batter'] == 'A'), slowdown=d['slowdown'],
               official_config=int(float(d['slowdown']) in OFFICIAL_SLOWDOWNS), video_rendered=int(d['video'] is True),
               sim_lag_max_s=d['sim_lag']['late_max_s'])
    for s in ('A', 'B'):
        out[s + '_runs'] = out[s + '_points'] = d['score'][s]
        out[s + '_won'] = int(valid and d['winner'] == s)
        out[s + '_transient_api_errors'] = int((d.get('transient_api_errors') or {}).get(s, 0))
        out[s + '_unrecovered_api_errors'] = int((d.get('unrecovered_api_errors') or {}).get(s, 0))
        for k in ('attempts', 'applied', 'refused', 'refused_busy', 'dropped', 'observations'):
            out[s + '_' + k] = d['seats'][s][k]
        for k in ('prepare_s', 'act_s', 'obs_age_s'):
            out[s + '_' + k + '_max'] = max(d['seats'][s][k], default=0)
    return out


if __name__ == '__main__':
    try:
        out = grade(*(json.loads((DATA / f).read_text()) for f in ('final.json', 'replay_check.json', 'trajectory.json')))
        for f in ('final.json', 'replay_check.json', 'episode.jsonl', 'trajectory.json', 'replay.mp4'):
            if (DATA / f).exists(): shutil.copy(DATA / f, LOG / f)
    except Exception as e:  # noqa: BLE001
        print(type(e).__name__, str(e))
        out = dict(success=0, valid_trial=0, technical_failure=1, grader_error=1,
                   missing_log=int(not (DATA / 'final.json').exists()))
    assert all(isinstance(v, (int, float)) for v in out.values())
    (LOG / 'reward.json').write_text(json.dumps(out)); (LOG / 'reward.txt').write_text(str(out['success']) + '\n'); print(out)
