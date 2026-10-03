"""Reference player for either seat of the badminton duel, camera-only (cam_player.py): it uses the seat's ordinary
endpoints (spec / status / observe / act / wait / start / ready) and nothing else, like any player program.

    SEAT=A|B python3 oracle_play.py          (SIM_URL, default http://sim:8000)
"""
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np                                    # noqa: E402
import cam_player as C                                # noqa: E402

SEAT = os.environ.get('SEAT', 'A')
OUT = os.environ.get('RCB_OUT', '/app/output')
os.makedirs(OUT, exist_ok=True)
BASE = os.environ.get('SIM_URL', 'http://sim:8000') + '/' + SEAT
REFINE_M = 0.03           # re-act when the predicted contact moves by more than this
LAST_REFINE_S = 0.25      # no corrections closer to the contact than this (game seconds)


def call(ep, body=None):
    req = urllib.request.Request(BASE + '/' + ep, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return dict(json.load(e), http_status=e.code)
        except ValueError:                        # e.g. the per-seat rate limiter's bare 429
            time.sleep(0.2)
            return dict(error=str(e), http_status=e.code)
    except (urllib.error.URLError, OSError, ValueError) as e:   # a dropped connection: retry later
        time.sleep(0.2)
        return dict(error=repr(e)[:200])


for _ in range(180):
    spec = call('spec')
    if 'timing' in spec:
        break
    time.sleep(1)
else:
    sys.exit('game service unreachable')
LEAD = int(spec['timing']['act_lead_steps'])
PERIOD = float(spec['timing']['period_s'])
CAMS = [C.Cam(c) for c in spec['cameras']]
VMAX = float(spec.get('base', {}).get('max_speed_mps', 6.0))
AMAX = float(spec.get('base', {}).get('max_accel_mps2', 20.0))
rng = random.Random(f"{SEAT}-{time.time()}")
log = open(os.path.join(OUT, 'reference.jsonl'), 'w', buffering=1)
stats = {'act': 0, 'react': 0, 'refine': 0, 'observe': 0, 'fit_fail': 0, 'ready': 0, 'flights': 0}


def L(**kw):
    log.write(json.dumps(kw, default=lambda o: o.tolist() if hasattr(o, 'tolist') else float(o)) + '\n')


def send(plan, T):
    stats['act'] += 1
    return call('act', {'type': 'act', 't': round(float(T), 3), 'pos': [round(float(x), 4) for x in plan['pos']],
                        'normal': [round(float(x), 4) for x in plan['normal']],
                        'vel': [round(float(x), 4) for x in plan['vel']]})


def act(plan, step):
    """Act so that the contact is at game time plan['t']; T counts from the effect step, assumed step + LEAD."""
    T = plan['t'] - (step + LEAD) * 0.01
    if T < 0.03:
        return None
    r = send(plan, T)
    te = (r.get('took_effect') or {}).get('step')
    if te is not None and te != step + LEAD and 'now' in r:      # it took effect late: correct T once
        T2 = plan['t'] - (int(r['now']['step']) + LEAD) * 0.01
        if T2 >= 0.03:
            stats['react'] += 1
            r = send(plan, T2)
    return r


def play():
    flight, obs, plan = None, [], None
    while True:
        s = call('status')
        if s.get('done'):
            return s
        if 'phase' not in s:
            time.sleep(PERIOD); continue
        if s['phase'] == 'review' and not s.get('ready', {}).get(SEAT):
            r = call('ready', {'why': 'reference player: camera-only, scripted', 'plan': 'same policy'})
            stats['ready'] += 1; L(ready=r.get('accepted') or r.get('error')); continue
        if s['phase'] != 'running':
            time.sleep(PERIOD); continue
        if s.get('ball_state') != 'coming to you':
            flight, obs, plan = None, [], None
            call('wait', {'dt': 0.03}); continue
        t0 = round(s['t_sim'] - s['t_since_played'], 3)
        if flight != (s['point'], t0):
            flight, obs, plan = (s['point'], t0), [], None
            stats['flights'] += 1
        o = call('observe', {})
        ob = o.get('observation') or {}
        if 'image_png_b64' not in ob:
            continue
        stats['observe'] += 1
        img = C.decode(base64.b64decode(ob['image_png_b64']))
        seen = {round(t, 3) for t, _ in obs}
        for t, X in C.detect_views(img, CAMS, ob['view_sim_times']):
            if t > t0 + 0.005 and round(t, 3) not in seen:
                obs.append((t, X))
        now = o['now']
        t_now = float(ob.get('t_sim_at_reply', now['t_sim']))
        if len(obs) < 4 or max(t for t, _ in obs) - min(t for t, _ in obs) < 0.05:
            continue
        tf, p, v, res = C.fit(obs)
        if res > 0.08:
            stats['fit_fail'] += 1; L(fit_fail=res, n=len(obs)); obs = obs[-4:]; continue
        ts, P, V = C.predict(p, v, tf)
        if plan is None:
            c = C.choose(ts, P, V, t_now + (LEAD + 2) * 0.01, np.asarray(now['robot_base_xy']), VMAX, AMAX, rng)
            if c is None:
                L(no_contact=True, t=t_now); plan = {'skip': True}; continue
            t_c, pos, v_in, opts, target = c
            plan = dict(t=float(t_c), pos=pos, normal=opts[0][0], vel=opts[0][1], target=target, opts=opts[1:])
        elif plan.get('skip') or plan['t'] - t_now < LAST_REFINE_S:
            call('wait', {'dt': 0.02}); continue
        else:
            i = int(np.argmin(np.abs(ts - plan['t'])))
            if np.linalg.norm(P[i] - plan['pos']) < REFINE_M:
                continue
            opts = C.strokes(P[i], V[i], plan['target'], C.DEEP_THETAS if plan['target'][1] > 4 else C.SHORT_THETAS)
            if not opts:
                continue
            plan.update(pos=P[i], normal=opts[0][0], vel=opts[0][1], opts=opts[1:]); stats['refine'] += 1
        w = call('wait', {'dt': 0.01})                 # returns right after a control step: act early in the next one
        if w.get('now', {}).get('phase') != 'running':
            continue
        r = act(plan, int(w['now']['step']))
        st = (r or {}).get('stroke') or {}
        # the reply predicts the delivery: if the joint speed limits cap the head speed or the pose is not delivered,
        # take the next (faster-head or other-angle) stroke to the same target while there is time
        bad = lambda st: (st.get('speed_scale') or 1) > 1.03 or (st.get('blade_error_m') or 0) > 0.03
        while bad(st) and plan['opts'] and 'now' in (r or {}) and plan['t'] - r['now']['t_sim'] > 0.3:
            plan['normal'], plan['vel'] = plan['opts'].pop(0)
            r = act(plan, int(r['now']['step'])); st = (r or {}).get('stroke') or {}; stats['retry'] = stats.get('retry', 0) + 1
        L(flight=flight, n_obs=len(obs), fit_rms=round(res, 4), plan={k: plan[k] for k in ('t', 'pos', 'vel')},
          took_effect=(r or {}).get('took_effect'), stroke=(r or {}).get('stroke'), error=(r or {}).get('error'))


while True:                                       # start blocks until both seats have started
    r = call('start', {})
    if r.get('accepted') or r.get('http_status') in (400, 409) or r.get('now'):
        break
L(start=r.get('accepted') or r.get('error'))
final = play()
print('final:', json.dumps({'status': {k: final.get(k) for k in ('score', 'reason', 'phase')}, 'stats': stats}))
L(final=final, stats=stats)
