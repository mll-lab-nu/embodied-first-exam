"""Numeric-only symmetric scoring from isolated trusted simulator artifacts."""
import hashlib,json,os,shutil
from pathlib import Path
DATA=Path(os.environ.get('RCB_DATA','/data'))
LOG=Path(os.environ.get('RCB_LOG','/logs/verifier'));LOG.mkdir(parents=True,exist_ok=True)
OFFICIAL_SLOWDOWNS = [10, 20]   # official configurations of the parameterized duel
WIN_POINTS, WIN_BY, CAP_POINTS = 5, 2, 7   # first to 5; from 4:4 lead by 2; at 6:6 the next point wins (duel.py)


def game_winner(score):
    for s, o in (('A', 'B'), ('B', 'A')):
        if score[s] >= CAP_POINTS or (score[s] >= WIN_POINTS and score[s] - score[o] >= WIN_BY):
            return s
    return None


def grade(d,r,t):
    targets={s:t[s] for s in ('A','B')}
    sha=hashlib.sha256(json.dumps(targets,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    replay=(d['state_sha']==r['state_sha'] and d['score']==r['score'] and
            sha==d['targets_sha']==r['targets_sha'] and d['source_sha']==r['source_sha']==t['source_sha'] and
            d['seed']==r['seed']==t['seed'] and d['first_receiver']==r['first_receiver']==t['first_receiver'] and
            d['revision']==r['revision']==t['revision']=='duel-wallclock-3' and
            d['steps']==r['steps']==len(t['A'])==len(t['B']) and d['points']==r['points'])
    # every played-out match has a winner (no draws): the game rule, or at the let guard the leader / last point winner
    match=(d['reason']=='match_over' and r['done'] and d['winner'] in ('A','B') and r.get('winner')==d['winner'] and
           game_winner(d['score']) in (None, d['winner']) and max(d['score'].values())<=CAP_POINTS)
    forfeit=(d['reason']=='ready_timeout' and d.get('forfeiting') in ('A','B') and all(d['joined'].values()) and
             d['winner']!=d['forfeiting'] and d['winner'] in ('A','B'))
    errors=bool(d.get('errors') or any(d['meter_error'].values()) or any(d['proxy_error'].values()))
    valid=bool(d['valid_trial'] and d['finalized'] and d['graded_ready'] and replay and (match or forfeit) and not errors)
    out=dict(success=int(valid),valid_trial=int(valid),technical_failure=int(not valid),grader_error=0,missing_log=0,
             deterministic=int(replay),match_over=int(match),ready_forfeit=int(forfeit),timing_invalid=0,
             steps=d['steps'],hits=d['hits'],seed=d['seed'],slowdown=d['slowdown'],official_config=int(float(d['slowdown']) in OFFICIAL_SLOWDOWNS),video_rendered=int(d['video']),
             sim_lag_max_s=d['sim_lag']['late_max_s'],net_touches=sum(p.get('net_touches',0) for p in d['points']),
             lets=sum(bool(p.get('let')) for p in d['points']))
    for s in ('A','B'):
        out[s+'_points']=d['score'][s];out[s+'_won']=int(valid and d['winner']==s)
        out[s + '_transient_api_errors'] = int((d.get('transient_api_errors') or {}).get(s, 0))
        out[s + '_unrecovered_api_errors'] = int((d.get('unrecovered_api_errors') or {}).get(s, 0))
        for k in ('attempts','applied','refused','dropped','observations'):out[s+'_'+k]=d['seats'][s][k]
        for k in ('plan_s','act_s','obs_age_s'):out[s+'_'+k+'_max']=max(d['seats'][s][k],default=0)
    return out
if __name__=='__main__':
    try:
        out=grade(*(json.loads((DATA/f).read_text()) for f in ('final.json','replay_check.json','trajectory.json')))
        for f in ('final.json','replay_check.json','episode.jsonl','trajectory.json','replay.mp4'):
            if (DATA/f).exists():shutil.copy(DATA/f,LOG/f)
    except Exception as e:
        print(type(e).__name__,str(e));out=dict(success=0,valid_trial=0,technical_failure=1,grader_error=1,missing_log=int(not (DATA/'final.json').exists()))
    assert all(isinstance(v,(int,float)) for v in out.values())
    (LOG/'reward.json').write_text(json.dumps(out));(LOG/'reward.txt').write_text(str(out['success'])+'\n');print(out)
