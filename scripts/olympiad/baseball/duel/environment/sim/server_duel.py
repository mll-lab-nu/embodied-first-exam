"""Two-seat wall-clock baseball duel service (pitcher against batter, program play); slow work runs outside the
world lock.

The world (bbduel.Duel) runs on its own clock at 1/SLOWDOWN of real speed in 10 ms control steps, paced from an anchor
as in the single-player service. It is frozen before the start (until both seats have sent `start`; the second has
START_TIMEOUT_S after the first) and after every pitch until both seats have sent `ready` (READY_TIMEOUT_S after the
pitch: a seat that misses it forfeits the game). Seats: /A/... and /B/..., each reachable only from its own container
(SEAT_HOSTS), each with its own metering proxy and usage file (think_usage_<seat>.json) and act rule (think_clock.py,
RCB_ACT_RULE=program: a live metered model session, no new response per act). One act and one observation in flight per
seat (HTTP 429). A pitch command is prepared (its flight computed) in a separate process before it is queued; every
queued command takes effect at the next control step.

Evidence (/data): episode.jsonl, final.json, trajectory.json (+ .npz): every command that took effect with its pitch,
step and seat; on the end (or SIGUSR1 from the collect hook) a fresh process (replay.py) re-runs the game from it and
must reproduce the state hash, the score and the step count.
"""
from __future__ import annotations

import base64
import concurrent.futures
import copy
import json
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bb  # noqa: E402
import bbduel  # noqa: E402
from bbduel import DT, OTHER, SIDES  # noqa: E402
from render_worker import RenderProcess  # noqa: E402
from replay import fingerprint  # noqa: E402
from think_clock import ThinkClock, read_usage  # noqa: E402
from api_errors import seat_api_errors  # noqa: E402
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog, pitch_frame, flight  # noqa: E402
except ImportError:  # pragma: no cover
    BroadcastLog = None

DATA = Path(os.environ.get('RCB_DATA', '/data'))
SEED = int(os.environ.get('DUEL_SEED', '1'))
FIRST = os.environ.get('FIRST_BATTER', 'A')
if FIRST not in SIDES:
    raise ValueError('FIRST_BATTER must be A or B')
REVIEW_PROMPT = ('Pitch over. Review it: `game ready "WHY" "PLAN"` (why it went as it did; what you will change). '
                 'The world stays frozen until both players are ready.')




# the pitcher's commands (spec match.pitching)
PITCHING = dict(release=list(bb.REL), target_x_m=list(bbduel.TARGET_X), target_z_m=list(bbduel.TARGET_Z),
              scatter=dict(bbduel.PITCH_SCATTER),
              arsenal={n: dict(speed_mps=list(bbduel.ARSENAL[n]), spin_rad_s=bb.PITCH_TYPES[n]['spin'],
                               spin_axis=list(bb.PITCH_TYPES[n]['axis'])) for n in sorted(bbduel.ARSENAL)},
              command="{'type':'pitch','pitch':TYPE,'speed':m/s,'x':target x,'z':target z} during the "
                      "windup; at the release the last one is thrown; none = an automatic ball")


class Service:
    def __init__(self, data=DATA, workers=True):
        self.data = Path(data); self.data.mkdir(parents=True, exist_ok=True)
        self.g = bbduel.Duel(SEED, FIRST)
        self.source_sha = fingerprint()
        self.cond = threading.Condition(threading.RLock())
        self.log_lock = threading.Lock()
        self.slowdown = float(os.environ.get('SLOWDOWN', '20'))
        if not np.isfinite(self.slowdown) or self.slowdown <= 0: raise ValueError('invalid slowdown')
        self.period = DT * self.slowdown
        self.t0 = time.monotonic()
        self.phase = 'prepare'
        self.joined = {s: False for s in SIDES}
        self.ready_seats = {s: False for s in SIDES}
        self.ready_deadline = None
        self.resume_at = None
        self.anchor = None
        self.reason = None
        self.forfeit = None
        self.finalized = self.finalizing = False
        self.errors = []
        self.replay = {}
        self.video = False
        self.reviews = []
        self.pending = {}
        self.applied = []                       # [pitch, step, seat, command] of every command that took effect
        self.last = None                        # the public record of the last pitch
        self.bc = None                          # the spectator broadcast log (set in __main__)
        self.lates = []; self.run_steps = 0; self.run_wall = 0.; self.segment_start = None
        self.clock = {s: ThinkClock(usage_file=str(self.data / f'think_usage_{s}.json'),
                                    mode=os.environ.get(f'PLAYER_MODE_{s}', os.environ.get('RCB_PLAYER_MODE', 'model')))
                      for s in SIDES}
        self.act_locks = {s: threading.Lock() for s in SIDES}
        self.view_locks = {s: threading.Lock() for s in SIDES}
        self.stats = {s: dict(attempts=0, applied=0, refused=0, refused_busy=0, dropped=0, observations=0,
                              prepare_s=[], act_s=[], obs_age_s=[]) for s in SIDES}
        self.render = {}
        self.pool = None
        if workers:
            self.pool = concurrent.futures.ProcessPoolExecutor(1, mp_context=multiprocessing.get_context('spawn'))
            for s in SIDES: self.render[s] = RenderProcess()
        self.log(dict(ev='start', revision=bbduel.REVISION, seed=SEED, first_batter=FIRST, source_sha=self.source_sha,
                      slowdown=self.slowdown, timing_policy='report_only',
                      player_modes={s: self.clock[s].mode for s in SIDES}))

    def log(self, event):
        row = dict(ts=time.time(), wall=time.monotonic() - self.t0, step=self.g.k, pitch=self.g.idx, **event)
        with self.log_lock:
            with (self.data / 'episode.jsonl').open('a') as f: f.write(json.dumps(row, default=float) + '\n')

    # ------------------------------------------------------------------------------------------- what a seat sees
    def state(self, side):
        g = self.g
        s = dict(seat=side, phase=self.phase, done=self.phase == 'over', reason=self.reason,
                 world='running' if self.phase == 'running' else 'frozen',
                 role=g.role(side), batter=g.batter, pitcher=g.pitcher, plate_appearance=g.pa + 1,
                 your_plate_appearances=sum(1 for r in g.pa_results if r['batter'] == side),
                 count=dict(balls=g.balls, strikes=g.strikes), score=dict(you=g.score[side], opponent=g.score[OTHER[side]]),
                 pitch=g.idx + 1, t_sim=round(g.k * DT, 4), step=g.k, ready=dict(self.ready_seats),
                 heard=g.heard(), command=g.command(side), last_pitch=self.last)
        if self.phase == 'running' and self.anchor is not None:
            a, k = self.anchor
            s['step_phase'] = round(min(1., max(0., (time.monotonic() - (a + (g.k - k) * self.period)) / self.period)), 3)
        else:
            s['step_phase'] = 0.0
        if g.over:
            s['pitch_phase'], s['t_since_release'] = 'pitch over', None
        elif g.released():
            s['pitch_phase'], s['t_since_release'] = 'ball released', g.t
        else:
            s['pitch_phase'], s['t_since_release'] = "windup (the ball is still in the pitcher's hand)", None
            s['release_in_s'] = round(-g.t, 4) if side == g.pitcher else None
        if self.phase == 'review':
            s['review_prompt'] = REVIEW_PROMPT
            s['review_deadline_s'] = round(max(0., self.ready_deadline - time.monotonic()), 1) if self.ready_deadline else None
        return s

    def reply(self, side, **extra):
        st = self.state(side)
        out = dict(extra, now=st)
        if st['done']: out['done'] = True
        if 'review_prompt' in st:
            out['review_prompt'] = st['review_prompt']
            out['pitch_over'] = self.last
        return out

    def failure(self, where, exc):
        with self.cond:
            self.errors.append(dict(where=where, error=str(exc)[:300]))
            self.log(dict(ev='error', where=where, error=str(exc)[:300]))
            self.end('technical_error')

    # ------------------------------------------------------------------------------------------- start / ready
    def ready(self, side, body):
        # This may wait for a model stream; never hold the world lock here.
        self.clock[side].settle()
        with self.cond:
            if self.phase not in ('prepare', 'review'): return 409, self.reply(side, error='not awaiting start or ready')
            pitch = self.g.idx
            if self.ready_seats[side]: return 409, self.reply(side, error='ready already submitted')
            why, plan = body.get('why', ''), body.get('plan', '')
            if not isinstance(why, str) or not isinstance(plan, str) or len(why) > 2000 or len(plan) > 2000:
                return 400, dict(error='why and plan must be strings of at most 2000 characters')
            if self.phase == 'review' and (not why.strip() or not plan.strip()):
                return 400, dict(error='both review fields required')
            self.joined[side] = True; self.ready_seats[side] = True
            if self.ready_deadline is None:
                window = os.environ.get('START_TIMEOUT_S') if self.phase == 'prepare' else None
                self.ready_deadline = time.monotonic() + float(window or os.environ.get('READY_TIMEOUT_S', '60'))
            if self.phase == 'review':
                self.reviews.append(dict(seat=side, after_pitch=len(self.g.history), why=why, plan=plan))
            self.log(dict(ev='ready', seat=side, why=why, plan=plan))
            if all(self.ready_seats.values()):
                self.resume_at = time.monotonic() + float(os.environ.get('BARRIER_LEAD_S', '.2'))
            self.cond.notify_all()
            # both replies are released by the same resume, not by a seat polling faster
            while self.phase in ('prepare', 'review') and self.g.idx == pitch and not self.g.done:
                self.cond.wait(.5)
            return 200, self.reply(side, accepted='ready')

    # ------------------------------------------------------------------------------------------- act
    def validate(self, side, body):
        role = self.g.role(side)
        kind = body.get('type')
        if kind == 'none':
            return {'type': 'none'}
        if role == 'pitching':
            if kind != 'pitch': raise ValueError('you are pitching: act with {"type":"pitch",...} or {"type":"none"}')
            return bbduel.validate_pitch(body)
        if kind != 'swing': raise ValueError('you are batting: act with {"type":"swing",...} or {"type":"none"}')
        try:
            T, plane, h, sp = (float(body[k]) for k in ('t', 'plane', 'height', 'speed'))
            reach = float(body.get('reach', 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('a swing needs t, plane, height, speed and optionally reach') from exc
        if not np.all(np.isfinite([T, plane, h, sp, reach])): raise ValueError('all swing fields must be finite')
        if not 0. < T <= 2.5: raise ValueError('T must be in (0, 2.5] s from when the act takes effect')
        if not -15. <= plane <= 35.: raise ValueError('PLANE must be in [-15, 35] degrees')
        if not .30 <= h <= 1.40: raise ValueError('HEIGHT must be in [0.30, 1.40] m')
        if not 15. <= sp <= 34.: raise ValueError('SPEED must be in [15, 34] m/s')
        if not -.20 <= reach <= .20: raise ValueError('REACH must be in [-0.20, 0.20] m')
        return {'type': 'swing', 't': T, 'plane': plane, 'height': h, 'speed': sp, 'reach': reach}

    def act(self, side, body):
        arrived = time.monotonic()
        if not self.act_locks[side].acquire(False):
            with self.cond: self.stats[side]['refused_busy'] += 1
            return 429, dict(refused=True, busy=True, error='busy: one act at a time; wait for the previous act\'s reply')
        try:
            with self.cond:
                self.stats[side]['attempts'] += 1
                if self.phase != 'running': return 409, self.reply(side, error='the world is not running')
                dec = self.validate(side, body)
                pitch, j = self.g.idx, self.g.j
            if not self.clock[side].decided_by_model():
                with self.cond:
                    self.stats[side]['refused'] += 1
                    self.log(dict(ev='refused_not_model', seat=side))
                return 429, dict(refused=True, error='refused: no live, metered model session')
            receipt = self.clock[side].last_call()
            prepared = None
            if dec['type'] == 'pitch':
                t_prep = time.monotonic()
                try:
                    prepared = self.pool.submit(bbduel.make_pitch, SEED, j, dec).result(timeout=60)
                except ValueError as exc:
                    return 400, self.reply(side, error=str(exc))
                with self.cond: self.stats[side]['prepare_s'].append(time.monotonic() - t_prep)
            with self.cond:
                if self.phase != 'running' or self.g.idx != pitch:
                    self.stats[side]['dropped'] += 1
                    self.log(dict(ev='act_dropped', seat=side, why='the pitch ended before the act took effect'))
                    return 409, self.reply(side, error='act dropped: the pitch ended before it took effect')
                item = dict(pitch=pitch, decision=dec, prepared=prepared, model_call=receipt, arrived=arrived,
                            result=None)
                self.pending[side] = item
                while item['result'] is None and self.phase == 'running' and self.g.idx == pitch:
                    self.cond.wait(.5)
                if item['result'] is None:
                    self.stats[side]['dropped'] += 1
                    return 409, self.reply(side, error='act dropped: the pitch ended before it took effect')
                res = item['result']
                key = 'pitch' if dec['type'] == 'pitch' or self.g.role(side) == 'pitching' else 'swing'
                return 200, self.reply(side, call='act', took_effect=res['took_effect'], **{key: res['info']})
        except ValueError as exc:
            return 400, dict(error=str(exc))
        finally:
            self.act_locks[side].release()

    def apply_pending(self):
        """At the start of a control step: every queued command takes effect (seat A first, then B)."""
        batch, self.pending = self.pending, {}
        for side in SIDES:
            item = batch.get(side)
            if item is None:
                continue
            if item['pitch'] != self.g.idx:
                self.stats[side]['dropped'] += 1; item['result'] = None; continue
            k, t_rel = self.g.k, self.g.t
            info = self.g.apply(side, item['decision'], item['prepared'])
            self.applied.append([self.g.idx, k, side, item['decision']])
            elapsed = time.monotonic() - item['arrived']
            item['result'] = dict(took_effect=dict(step=k, t_sim=round(k * DT, 4), t_since_release=t_rel,
                                                   wall_s_after_request=round(elapsed, 4)), info=info)
            self.stats[side]['applied'] += 1; self.stats[side]['act_s'].append(elapsed)
            self.log(dict(ev='act_applied', seat=side, k=k, pitch_idx=self.g.idx, decision=item['decision'],
                          model_call=item['model_call'], result=info))

    # ------------------------------------------------------------------------------------------- observe / wait
    def observe(self, side):
        if not self.view_locks[side].acquire(False):
            return 429, dict(error='one observation per seat may be in flight')
        try:
            with self.cond:
                now = self.state(side)
                snaps = self.g.snapshots()
                k_snap, mono = self.g.k, time.monotonic()
                self.stats[side]['observations'] += 1; obs_id = self.stats[side]['observations']
            t = time.monotonic()
            png = self.render[side].render(snaps)
            render_s = time.monotonic() - t
            with self.cond:
                age = time.monotonic() - mono
                self.stats[side]['obs_age_s'].append(age)
                k_reply = self.g.k
                self.log(dict(ev='observe', seat=side, obs_id=obs_id, view_steps=[s['k'] for s in snaps], age_s=age))
                out = self.reply(side, call='observe')
                # the observation: the state when the frames were taken, the frames and their times
                out['observation'] = dict(now, obs_id=obs_id, image_png_b64=base64.b64encode(png).decode(),
                                          view_times=[s['t'] for s in snaps], view_steps=[s['k'] for s in snaps],
                                          view_sim_times=[round(s['k'] * DT, 4) for s in snaps],
                                          t_sim_at_reply=round(k_reply * DT, 4),
                                          obs_age_sim_s=round((k_reply - k_snap) * DT, 4),
                                          obs_age_wall_s=round(age, 4), render_wall_s=round(render_s, 4))
                return 200, out
        finally:
            self.view_locks[side].release()

    def wait(self, side, body):
        duration = float(body.get('dt', 0))
        if not np.isfinite(duration) or not 0 < duration <= 1: return 400, dict(error='dt must be 0..1 game seconds')
        with self.cond:
            target = self.g.k + max(1, int(round(duration / DT))); pitch = self.g.idx
            while self.phase == 'running' and self.g.idx == pitch and self.g.k < target: self.cond.wait(.5)
            return 200, self.reply(side, call='wait')

    # ------------------------------------------------------------------------------------------- the world
    def end(self, reason, forfeiting=None):
        if self.finalizing: return
        if self.segment_start is not None: self.run_wall += time.monotonic() - self.segment_start; self.segment_start = None
        self.phase = 'over'; self.reason = reason; self.forfeit = forfeiting; self.finalizing = True
        self.pending.clear()
        self.log(dict(ev='end', reason=reason, forfeiting=forfeiting, score=self.g.score, k_end=self.g.k))
        self.bc_event('end', reason=reason, forfeiting=forfeiting)
        self.cond.notify_all()
        threading.Thread(target=self.finalize, daemon=True).start()

    def bc_event(self, ev, **fields):
        if self.bc is not None: self.bc.event(ev, self.g.k, score=dict(self.g.score), **fields)

    def pitch_over(self):
        """With the lock held, right after the step that ended the pitch: freeze, judge, review."""
        self.run_wall += time.monotonic() - self.segment_start; self.segment_start = None
        for side in self.pending: self.stats[side]['dropped'] += 1
        self.pending.clear()
        rec = self.g.finish()
        self.last = self.g.public_rec(rec)
        self.log(dict(ev='pitch_over', result=self.last, score=self.g.score))
        if self.bc is not None:
            g = self.g
            how = f"{rec['batter']} batting: {rec.get('type', '')} {rec.get('radar', '')} m/s: {rec['outcome']}" + \
                  (f" ({rec['pa_result']})" if rec.get('pa_result') else '')
            self.bc.event('point', g.k, score=dict(g.score), winner=None, how=how, n=len(g.history),
                          note=f"PA {g.pa + (0 if rec.get('pa_result') else 1)} · count {g.balls}-{g.strikes}",
                          flight=flight(rec.get('batted_samples')))
        if self.g.done:
            self.end('game_over')
        else:
            self.phase = 'review'
            self.ready_deadline = time.monotonic() + float(os.environ.get('READY_TIMEOUT_S', '60'))
            self.log(dict(ev='pause_for_review'))
            self.bc_event('pause')

    def loop(self):
        try:
            while True:
                with self.cond:
                    if self.phase == 'over': return
                    now = time.monotonic()
                    if self.phase in ('prepare', 'review'):
                        if self.resume_at is not None and now >= self.resume_at:
                            epoch = time.time()
                            for clock in self.clock.values(): clock.begin_segment(epoch)
                            if self.phase == 'review': self.g.next_pitch()
                            self.phase = 'running'; self.anchor = (now, self.g.k)
                            self.segment_start = now; self.resume_at = None; self.ready_deadline = None
                            self.ready_seats = {s: False for s in SIDES}
                            self.log(dict(ev='run', started_epoch=epoch, batter=self.g.batter))
                            self.bc_event('run', batter=self.g.batter)
                            self.cond.notify_all()
                        elif self.ready_deadline and now > self.ready_deadline:
                            missing = [s for s in SIDES if not self.ready_seats[s]]
                            self.end('ready_timeout' if all(self.joined.values()) and len(missing) == 1 else 'incomplete',
                                     missing[0] if len(missing) == 1 else None)
                            continue
                        else:
                            self.cond.wait(.01); continue
                    a, k = self.anchor; due = a + (self.g.k - k + 1) * self.period
                delay = due - time.monotonic()
                if delay > 0: time.sleep(min(delay, .02)); continue
                with self.cond:
                    if self.phase != 'running': continue
                    self.apply_pending(); self.g.advance(1); self.run_steps += 1
                    self.lates.append(max(0., time.monotonic() - due))
                    pitch_frame(self.bc, self.g)
                    if self.g.over: self.pitch_over()
                    self.cond.notify_all()
                    if self.g.k % 50 == 0 or self.phase != 'running': self.write_final()
        except Exception as exc: self.failure('world', exc)

    # ------------------------------------------------------------------------------------------- evidence
    def write_final(self):
        with self.cond:
            g = self.g; score = dict(g.score)
            usage = {s: read_usage(self.clock[s].usage_file) for s in SIDES}
            meter = {s: self.clock[s].mode == 'model' and (not u.get('epoch') or not u.get('requests')) for s, u in usage.items()}
            apis = {s: seat_api_errors(self.clock[s].usage_file, u) for s, u in usage.items()}   # model-API errors: transient vs unrecovered (api_errors.py)
            api = {s: a['api_failure'] for s, a in apis.items()}   # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
            dsha = bbduel.decisions_sha(self.applied)
            replay_ok = (self.replay.get('state_sha') == g.state_sha() and self.replay.get('score') == score
                         and self.replay.get('decisions_sha') == dsha and self.replay.get('steps') == g.k
                         and self.replay.get('source_sha') == self.source_sha)
            complete = self.reason == 'game_over' or (self.reason == 'ready_timeout' and self.forfeit in SIDES)
            valid = bool(self.finalized and complete and replay_ok and not self.errors and not any(meter.values())
                         and not any(api.values()))
            win = OTHER[self.forfeit] if self.forfeit else g.winner()
            out = dict(revision=bbduel.REVISION, source_sha=self.source_sha, seed=SEED, first_batter=FIRST,
                       state_sha=g.state_sha(), decisions_sha=dsha, forfeiting=self.forfeit, slowdown=self.slowdown,
                       score=score, winner=win if valid else None, decided_by='forfeit' if self.forfeit else g.decided_by(),
                       reason=self.reason, phase=self.phase, finalized=self.finalized, graded_ready=self.finalized,
                       valid_trial=valid, technical_failure=not valid, timing_policy='report_only', timing_invalid=False,
                       errors=self.errors, meter_error=meter, proxy_error=api, deterministic=bool(replay_ok),
                       transient_api_errors={s: a['transient_api_errors'] for s, a in apis.items()},
                       unrecovered_api_errors={s: a['unrecovered_api_errors'] for s, a in apis.items()},
                       replay_score=self.replay.get('score'), steps=g.k, pitches=len(g.history),
                       plate_appearances=g.pa, pa_results=g.pa_results,
                       pitch_log=[g.public_rec(r) for r in g.history], seats=self.stats, reviews=self.reviews,
                       joined=self.joined, player_modes={s: self.clock[s].mode for s in SIDES}, video=self.video,
                       elapsed_s=time.monotonic() - self.t0,
                       format=dict(pa_per_seat=bbduel.PA_PER_SEAT, extra_pairs=bbduel.EXTRA_PAIRS,
                                   pa_max_pitches=bbduel.PA_MAX_PITCHES),
                       sim_lag=dict(late_max_s=max(self.lates, default=0),
                                    late_p99_s=float(np.percentile(self.lates, 99)) if self.lates else 0,
                                    run_steps=self.run_steps, run_sim_s=self.run_steps * DT, run_wall_s=self.run_wall,
                                    period_s=self.period))
            path = self.data / 'final.json.tmp'; path.write_text(json.dumps(out, default=float)); path.replace(self.data / 'final.json')

    def finalize(self):
        try:
            with self.cond:
                payload = dict(commands=copy.deepcopy(self.applied), k_end=self.g.k, seed=SEED, first_batter=FIRST,
                               source_sha=self.source_sha, revision=bbduel.REVISION, slowdown=self.slowdown)
                (self.data / 'trajectory.json').write_text(json.dumps(payload, default=float))
                # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the JSON; the same commands):
                # pitch, step, seat (0 A, 1 B), kind (0 none, 1 swing, 2 pitch), then T, plane, height, speed, reach
                # (swing) or pitch type index, speed, x, z (pitch)
                kinds, names = {'none': 0, 'swing': 1, 'pitch': 2}, sorted(bbduel.ARSENAL)
                rows = []
                for p, k, s, d in self.applied:
                    vals = ([d['t'], d['plane'], d['height'], d['speed'], d['reach']] if d['type'] == 'swing' else
                            [names.index(d['pitch']), d['speed'], d['x'], d['z'], 0.] if d['type'] == 'pitch' else [0.] * 5)
                    rows.append([p, k, SIDES.index(s), kinds[d['type']]] + vals)
                np.savez(self.data / 'trajectory.npz', commands=np.asarray(rows, dtype=np.float64).reshape(-1, 9),
                         seed=SEED, first_batter=FIRST, k_end=self.g.k, slowdown=self.slowdown)
            subprocess.run([sys.executable, str(HERE / 'replay.py'), str(self.data)], check=True,
                           timeout=float(os.environ.get('RCB_REPLAY_TIMEOUT_S', '300')))
            self.replay = json.loads((self.data / 'replay_check.json').read_text())
            render = os.environ.get('RCB_RENDER_VIDEO', '1') == '1'
            with self.cond:                     # grading readiness does not wait for the optional video
                self.video = 'pending' if render else False
                self.finalized = True; self.write_final()
            if render:
                self.video = False
                try:
                    subprocess.run([sys.executable, str(HERE / 'replay.py'), str(self.data), '--video'], check=True,
                                   timeout=float(os.environ.get('RCB_VIDEO_TIMEOUT_S', '300')),
                                   stdout=subprocess.DEVNULL, stderr=open(self.data / 'replay_video.log', 'w'))
                    self.video = True
                except Exception as exc: self.log(dict(ev='video_error', error=str(exc)[:300]))
        except Exception as exc:
            self.errors.append(dict(where='replay', error=str(exc)[:300]))
        with self.cond:
            self.finalized = True; self.write_final(); self.cond.notify_all()

    def spec(self, side):
        return dict(
            seat=side, protocol='eai-standard-realtime/1.0', revision=bbduel.REVISION,
            player_mode=self.clock[side].mode,
            match=dict(format=f'plate appearances alternate between the seats: one bats, the other pitches; each seat '
                              f'bats {bbduel.PA_PER_SEAT} times; level bases after that: one more each, up to '
                              f'{bbduel.EXTRA_PAIRS} times; still level: the winner of the last pitch wins (no draws)', first_player=FIRST,
                       first_player_meaning='the seat that bats first (plate appearances 1, 3, 5, ...)',
                       pa_per_seat=bbduel.PA_PER_SEAT, extra_pairs=bbduel.EXTRA_PAIRS,
                       pa_max_pitches=bbduel.PA_MAX_PITCHES,
                       score='bases: walk 1, single 1, double 2, home run 4 (no triples)',
                       count='3 strikes = strikeout, 4 balls = walk, a foul is a strike unless there are already 2 '
                             'strikes; a plate appearance reaching 15 pitches is an out',
                       pitching=PITCHING),
            timing=dict(slowdown=self.slowdown, control_dt_s=DT, period_s=self.period,
                        wall_s_per_control_step=self.period, windup_s=list(bbduel.WINDUP),
                        frame_gap_s=0.03, wait_max_s=1.0, policy='report_only',
                        review_limit_s=float(os.environ.get('READY_TIMEOUT_S', '60')),
                        start_window_s=float(os.environ.get('START_TIMEOUT_S', '60'))),
            decision_rule=('program play: your own program may observe and act without a new model response; one act '
                           'per seat in flight' if os.environ.get('RCB_ACT_RULE') == 'program' else
                           'one fresh completed model response per act'),
            swing_rig=dict(pivot=f'(-0.66 + REACH, {bb.PIVOT_Y}, HEIGHT) = the knob', bat_length=bb.L_BAT,
                           time_to_square_s='3.9741 / SPEED after the swing start', sweet_spot_s=bb.S_SS,
                           scatter=dict(bb.SCATTER),
                           command="{'type':'swing','t':T,'plane':PLANE,'height':HEIGHT,'speed':SPEED,'reach':REACH} "
                                   'after the release'),
            ball=dict(mass=bb.M_BALL, radius=bb.R_BALL, air_density=bb.RHO, C_D=bb.CD, spin_decay_s=bb.SPIN_TAU),
            zone=dict(plane='y = 0', x=[-bb.ZONE_X, bb.ZONE_X], z=[bb.ZONE_LO, bb.ZONE_HI],
                      rule='strike if the ball\'s centre crosses y = 0 within the zone grown by the ball radius'),
            field=dict(foul_lines_deg=45, first_base_xy=[round(v, 2) for v in bb.B1], fence_m=bb.FENCE_R, fence_height_m=bb.FENCE_H,
                       fielders={f[0]: dict(xy=[round(v, 2) for v in bb.FIELDER_POS[f[0]]], r0=f[3], v_run=f[4],
                                            t_react=f[5]) for f in bb.FIELDERS}),
            cameras=bb.cam_info(),
            image='2 rows (catcher, side) x 4 columns (frames 30 ms apart, oldest left); tile 480 x 360',
            world='home plate centre = origin, +y to the pitcher / centre field, +x to first base, z up; ground z = 0')


SERVICE = None


def seat_allowed(side, addr):
    hosts = dict(x.split('=', 1) for x in os.environ.get('SEAT_HOSTS', '').split(',') if '=' in x)
    if side not in hosts: return addr in ('127.0.0.1', '::1')
    try: return addr in {a[4][0] for a in socket.getaddrinfo(hosts[side], None)}
    except OSError: return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args): pass

    def send(self, code, value):
        raw = json.dumps(value, default=float).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass

    def setup(self):
        super().setup(); self.connection.settimeout(10)

    def dispatch(self, post=False):
        bits = self.path.strip('/').split('/')
        if len(bits) != 2 or bits[0] not in SIDES or not seat_allowed(bits[0], self.client_address[0]):
            return self.send(403, dict(error='seat not authorized'))
        side, ep = bits; body = {}
        try:
            if post:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 32768: raise ValueError('request too large')
                body = json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body, dict): raise ValueError('object required')
            if post and ep in ('start', 'ready'): code, out = SERVICE.ready(side, body)
            elif post and ep == 'act': code, out = SERVICE.act(side, body)
            elif post and ep == 'wait': code, out = SERVICE.wait(side, body)
            elif ep == 'observe': code, out = SERVICE.observe(side)
            elif not post and ep == 'spec': code, out = 200, SERVICE.spec(side)
            elif not post and ep == 'status':
                with SERVICE.cond: code, out = 200, SERVICE.reply(side, call='status')
            else: code, out = 404, dict(error='unknown endpoint')
        except (ValueError, TypeError, KeyError) as exc: code, out = 400, dict(error=str(exc))
        except Exception as exc:
            SERVICE.failure(ep, exc); code, out = 500, dict(error='technical failure', detail=str(exc)[:200])
        self.send(code, out)

    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch(True)


class BoundedHTTPServer(ThreadingHTTPServer):
    """Cap socket/handler work independently for each seat."""
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slots = {s: threading.BoundedSemaphore(4) for s in SIDES}
        self.arrivals = {s: [] for s in SIDES}

    def process_request(self, request, addr):
        side = next((s for s in SIDES if seat_allowed(s, addr[0])), None)
        if side is not None:
            now = time.monotonic(); self.arrivals[side] = [t for t in self.arrivals[side] if now - t < 1]
        limited = side is not None and len(self.arrivals[side]) >= 20
        if side is None or limited or not self.slots[side].acquire(False):
            try:
                request.settimeout(.1)
                request.sendall(b'HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError: pass
            self.shutdown_request(request); return
        self.arrivals[side].append(time.monotonic())
        try: super().process_request(request, (addr[0], addr[1], side))
        except Exception:
            self.slots[side].release(); raise

    def process_request_thread(self, request, addr):
        try: super().process_request_thread(request, addr[:2])
        finally: self.slots[addr[2]].release()


if __name__ == '__main__':
    SERVICE = Service()
    if BroadcastLog is not None:
        SERVICE.bc = BroadcastLog(every=2, sport='baseball', mode='duel', slowdown=SERVICE.slowdown, dt=DT, seed=SEED,
                                  first_batter=FIRST, players={'A': 'A', 'B': 'B'})
        with SERVICE.cond: pitch_frame(SERVICE.bc, SERVICE.g)      # the scene before the first pitch

    def stop(*args):
        def run():
            with SERVICE.cond: SERVICE.end('collected')
        threading.Thread(target=run, daemon=True).start()
    signal.signal(signal.SIGUSR1, stop)
    (DATA / 'think_calls_A.jsonl').touch(); (DATA / 'think_calls_B.jsonl').touch()
    (DATA / 'server.pid').write_text(str(os.getpid()))
    SERVICE.write_final()
    threading.Thread(target=SERVICE.loop, daemon=True).start()
    print('baseball duel ready', flush=True)
    BoundedHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
