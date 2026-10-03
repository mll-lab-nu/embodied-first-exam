"""Numeric-only symmetric grading of a turn-based duel from the trusted simulator artifacts (separate sandbox).

valid_trial = 1 iff the match is complete (played out, or ended by a clock or start forfeit), the fresh-process
replay (replay_check.json) reproduces the live score and state hash from trajectory.json with the same simulator code,
and no seat had a metering or model-API failure. success = valid_trial (the duel itself is the deliverable); the
winner is A_won / B_won (they sum to 1 in a valid trial: there are no draws; a tie at the cap is decided by the
recorded chess clocks, `clock_tiebreak`)."""
import json
import os
import shutil
from pathlib import Path

DATA = Path(os.environ.get('RCB_DATA', '/data'))
LOG = Path(os.environ.get('RCB_LOG', '/logs/verifier')); LOG.mkdir(parents=True, exist_ok=True)
OFFICIAL_SEEDS = [1, 2, 3]          # official configurations: these seeds, each with FIRST_PLAYER A and B
SCORE = 'points'


def grade(d, r, t):
    replay = (d['state_sha'] == r['state_sha'] and d['score'] == r['score'] and d['source_sha'] == r['source_sha'] == t['source_sha']
              and d['seed'] == r['seed'] == t['seed'] and d['first_player'] == r['first_player'] == t['first_player']
              and d['revision'] == r['revision'] == t['revision'] and d['n_shots'] == len(t['decisions']))
    complete = d['reason'] in ('match_over', 'clock_expired') or (d['reason'] == 'start_timeout' and d.get('forfeiting') in ('A', 'B'))
    errors = bool(d.get('errors') or any(d['meter_error'].values()) or any(d['proxy_error'].values()))
    decided = d.get('winner') in ('A', 'B')
    valid = bool(d['valid_trial'] and d['finalized'] and d['graded_ready'] and replay and complete and decided and not errors)
    out = dict(success=int(valid), valid_trial=int(valid), technical_failure=int(not valid), grader_error=0, missing_log=0,
               deterministic=int(replay), match_over=int(d['reason'] == 'match_over'),
               clock_forfeit=int(d['reason'] == 'clock_expired'), start_forfeit=int(d['reason'] == 'start_timeout'),
               clock_tiebreak=int(bool(d.get('tiebreak'))), seed=int(d['seed']), first_player=0 if d['first_player'] == 'A' else 1,
               official_config=int(int(d['seed']) in OFFICIAL_SEEDS and d['first_player'] in ('A', 'B')),
               n_shots=int(d['n_shots']), video_rendered=int(bool(d.get('video'))), elapsed_s=float(d.get('elapsed_s') or 0))
    for s in ('A', 'B'):
        st = d['seats'][s]
        out[f'{s}_{SCORE}'] = int(d['score'][s])
        out[f'{s}_won'] = int(valid and d.get('winner') == s)
        out[s + '_transient_api_errors'] = int((d.get('transient_api_errors') or {}).get(s, 0))
        out[s + '_unrecovered_api_errors'] = int((d.get('unrecovered_api_errors') or {}).get(s, 0))
        out[f'{s}_clock_forfeit'] = int(d['reason'] == 'clock_expired' and d.get('forfeiting') == s)
        for k in ('n_decisions', 'n_reviews', 'refused_busy', 'refused_not_model', 'refused_out_of_turn'):
            out[f'{s}_{k}'] = int(st.get(k, 0))
        out[f'{s}_clock_left_s'] = float(st.get('clock_left_s', 0))
    return out


if __name__ == '__main__':
    try:
        out = grade(*(json.loads((DATA/f).read_text()) for f in ('final.json', 'replay_check.json', 'trajectory.json')))
        for f in ('final.json', 'replay_check.json', 'episode.jsonl', 'trajectory.json', 'replay.mp4'):
            if (DATA/f).exists():
                shutil.copy(DATA/f, LOG/f)
    except Exception as e:  # noqa: BLE001
        print(type(e).__name__, str(e))
        out = dict(success=0, valid_trial=0, technical_failure=1, grader_error=1, missing_log=int(not (DATA/'final.json').exists()))
    assert all(isinstance(v, (int, float)) for v in out.values())
    (LOG/'reward.json').write_text(json.dumps(out)); (LOG/'reward.txt').write_text(str(out['success'])+'\n'); print(out)
