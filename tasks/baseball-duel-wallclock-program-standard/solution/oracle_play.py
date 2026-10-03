"""Scripted reference player for the baseball duel, usable on either seat (SEAT=A|B): it pitches when its seat
pitches and bats (bat_player.py, camera-only) when its seat bats. It uses only the seat's endpoints, the camera
images, the spec and the documented models; no simulator state.

The pitcher: a fixed mix (fastball 45 %, slider 20 %, changeup 20 %, curveball 15 %) near the top of each speed band,
about two thirds aimed inside the strike zone and the rest just off an edge; its random choices depend only on the
pitch number and the count, so both seats pitch the same way.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bat_player as BP  # noqa: E402

BASE = os.environ.get('SIM_URL', 'http://sim:8000') + '/' + os.environ['SEAT']
Path('/app/output').mkdir(exist_ok=True, parents=True)
LOG = open('/app/output/reference.jsonl', 'w', buffering=1)
MIX = [("fastball", .45), ("slider", .20), ("changeup", .20), ("curveball", .15)]


def call(ep, body=None):
    req = urllib.request.Request(BASE + '/' + ep, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            out = json.load(e)
        except ValueError:
            out = {'error': str(e)}
        out.setdefault('error', f'HTTP {e.code}')
        return out


def note(**kw):
    LOG.write(json.dumps(kw, default=float) + '\n')


class Api:
    def observe(self):
        r = call('observe', {})
        return r, r.get('observation')

    def act(self, body):
        r = call('act', body)
        return r

    def wait(self, dt):
        return call('wait', {'dt': dt})


def choose_pitch(spec, now):
    c = now['count']
    rng = random.Random(f"{now['pitch']}-{c['balls']}-{c['strikes']}")
    u, name = rng.random(), MIX[-1][0]
    for n, p in MIX:
        if u < p:
            name = n
            break
        u -= p
    lo, hi = spec['match']['pitching']['arsenal'][name]['speed_mps']
    speed = hi - 1.5 * rng.random()
    if rng.random() < (0.85 if c['balls'] == 3 else 0.65):
        x, z = -0.17 + 0.34 * rng.random(), 0.52 + 0.48 * rng.random()
    else:
        side = rng.randrange(4)
        x, z = [(-0.33, 0.45 + 0.6 * rng.random()), (0.33, 0.45 + 0.6 * rng.random()),
                (-0.2 + 0.4 * rng.random(), 0.36), (-0.2 + 0.4 * rng.random(), 1.18)][side]
    return {'type': 'pitch', 'pitch': name, 'speed': round(speed, 2), 'x': round(x, 3), 'z': round(z, 3)}


for _ in range(180):
    try:
        spec = call('spec')
        if 'timing' in spec:
            break
    except OSError:
        pass
    time.sleep(1)
else:
    raise RuntimeError('server did not start')
period = spec['timing']['period_s']
spins = [[a['spin_rad_s'] * x for x in a['spin_axis']] for a in spec['match']['pitching']['arsenal'].values()]
B = BP.Batter(spec['cameras'])
api = Api()
note(start=call('start', {}).get('now'))
while True:
    s = call('status')
    now = s.get('now') or {}
    if s.get('done') or now.get('done'):
        break
    if now.get('phase') == 'review':
        r = call('ready', {'why': 'reference player: review recorded', 'plan': 'same policy'})
        note(pitch_over=s.get('pitch_over'), ready=r.get('accepted') or r.get('error'))
        continue
    if now.get('phase') != 'running':
        time.sleep(.1)
        continue
    if now.get('role') == 'batting':
        r = BP.bat_pitch(api, B, spins, period, log=note)
        continue
    if now.get('t_since_release') is None and now.get('pitch_phase', '').startswith('windup') \
            and not isinstance(now.get('command'), dict):
        cmd = choose_pitch(spec, now)
        r = call('act', cmd)
        note(pitch=cmd, result=r.get('pitch') or r.get('error'))
        if not r.get('error'):
            continue
    r = call('wait', {'dt': 1.0})
final = call('status')
print(json.dumps(final.get('now')))
