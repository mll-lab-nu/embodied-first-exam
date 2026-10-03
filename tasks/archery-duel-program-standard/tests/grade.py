"""Trusted artifact grader of the archery duel (separate sandbox, no network): reads what the sim service wrote
(/data/final.json, /data/replay_check.json). success = valid_trial = a match played out (or won on the other
player's clock or abandonment) with a deterministic replay and no simulator, metering or model-API failure. The
winner is A_won / B_won (shoot-offs continue until the tie is broken, so there is no draw). Numbers only in reward.json."""
import json
import os
import shutil
from pathlib import Path

DATA = Path(os.environ.get('RCB_DATA', '/data'))
LOG = Path(os.environ.get('RCB_LOG', '/logs/verifier'))
# Official configurations of this parameterized duel (scripts/olympiad/archery/spec.py): play both FIRST_PLAYER orders
OFFICIAL_DUEL_SEEDS = [1, 2, 3]


def grade(d, r):
    replay = bool(d.get('deterministic')) and r.get('totals') == d.get('totals') and r.get('winner') == d.get('match_winner')
    complete = d.get('reason') in ('match_over', 'clock', 'abandoned') and d.get('match_winner') in ('A', 'B')
    errors = bool(d.get('errors') or any((d.get('meter_error') or {}).values()) or any((d.get('proxy_error') or {}).values()))
    valid = bool(d.get('valid_trial') and d.get('finalized') and replay and complete and not errors)
    seed = int(d.get('seed') or 0)
    so = d.get('shootoff') or []
    out = dict(success=int(valid), valid_trial=int(valid), technical_failure=int(not valid), grader_error=0,
               missing_log=0, deterministic=int(replay), match_over=int(d.get('reason') == 'match_over'),
               clock_forfeit=int(bool(d.get('clock_forfeit'))), abandoned=int(bool(d.get('abandoned'))),
               shootoff_arrows=len(so), seed=seed,
               first_player_A=int(d.get('first_player') == 'A'),
               official_config=int(seed in OFFICIAL_DUEL_SEEDS and d.get('first_player') in ('A', 'B')),
               video_rendered=int(bool(d.get('video'))), elapsed_s=float(d.get('elapsed_s') or 0.0))
    for s in ('A', 'B'):
        st = (d.get('seats') or {}).get(s, {})
        out[s + '_total'] = int((d.get('totals') or {}).get(s, 0))
        out[s + '_n_x'] = int((d.get('n_x') or {}).get(s, 0))
        out[s + '_won'] = int(valid and d.get('match_winner') == s)
        out[s + '_transient_api_errors'] = int((d.get('transient_api_errors') or {}).get(s, 0))
        out[s + '_unrecovered_api_errors'] = int((d.get('unrecovered_api_errors') or {}).get(s, 0))
        out[s + '_clock_used_s'] = float((d.get('clock_used_s') or {}).get(s, 0.0))
        out[s + '_clock_forfeit'] = int(d.get('clock_forfeit') == s)
        for k in ('n_act', 'n_observe', 'n_reviews', 'refused_busy', 'refused_turn', 'refused_not_model'):
            out[s + '_' + k] = int(st.get(k, 0))
    return out


if __name__ == '__main__':
    LOG.mkdir(parents=True, exist_ok=True)
    try:
        out = grade(*(json.loads((DATA / f).read_text()) for f in ('final.json', 'replay_check.json')))
        for f in ('final.json', 'replay_check.json', 'episode.jsonl', 'trajectory.json', 'replay_A.mp4', 'replay_B.mp4'):
            if (DATA / f).exists():
                shutil.copy(DATA / f, LOG / f)
    except Exception as e:  # noqa: BLE001
        print(type(e).__name__, str(e))
        out = dict(success=0, valid_trial=0, technical_failure=1, grader_error=1,
                   missing_log=int(not (DATA / 'final.json').exists()))
    assert all(isinstance(v, (int, float)) for v in out.values())
    (LOG / 'reward.json').write_text(json.dumps(out))
    (LOG / 'reward.txt').write_text(str(out['success']) + '\n')
    print(out)
