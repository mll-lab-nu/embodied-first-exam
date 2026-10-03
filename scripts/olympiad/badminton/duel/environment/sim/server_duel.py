"""Two-seat continuous wall-clock badminton service (bduel.py); all slow work runs outside the world lock.

The world thread steps the match at CONTROL_DT x SLOWDOWN of wall time per control step. An act queued at step k_q
takes effect at k_e = k_q + LEAD_STEPS (the stroke planner's lead, at least PLAN_LEAD_S of wall time, as in the match
task); the seat's planner process advances an exact copy of that seat's robot to k_e and plans there, so the result is
bit-identical to planning in the world thread (which the fresh-process replay does from the logged acts). If a plan is
not back by k_e the world waits for it; the lateness is recorded. Frozen phases: before both seats have started and
after each point until both seats are ready (REVIEW limit: READY_TIMEOUT_S, then the missing seat forfeits)."""
from __future__ import annotations
import base64
import hashlib
import json
import math
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
import bduel
import bm
from think_clock import ThinkClock, read_usage, MeterError
from api_errors import seat_api_errors  # noqa: E402
from workers import ProcessWorker, affinity
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog
except ImportError:  # pragma: no cover
    BroadcastLog = None

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('RCB_DATA', '/data'))
DT = bduel.CONTROL_DT
SIDES, OTHER = bduel.SIDES, bduel.OTHER
WAIT_MAX_S = 1.0
REVIEW_MAX_CHARS = 2000


def fingerprint():
    h = hashlib.sha256()
    paths = list(HERE.glob('*.py')) + list((HERE/'scene').rglob('*'))
    for p in sorted(set(paths)):
        if p.is_file(): h.update(str(p.relative_to(HERE)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def validate(body):
    """The match task's act (bm racket state at contact), in the seat's own frame."""
    if body.get('type') == 'none': return {'type': 'none'}
    try:
        if body.get('type', 'act') != 'act': raise ValueError('use act or none')
        T = float(body['t']); pos = [float(x) for x in body['pos']]
        nrm = [float(x) for x in body['normal']]; vel = [float(x) for x in body['vel']]
    except (TypeError, KeyError, ValueError):
        raise ValueError('act needs T (s from when the act takes effect until contact), pos [x, y, z] (racket-head '
                         'centre at contact), normal [nx, ny, nz] (string-face normal) and vel [vx, vy, vz] (head velocity '
                         'at contact, m/s); or {"type": "none"}')
    if len(pos) != 3 or len(nrm) != 3 or len(vel) != 3 or not np.all(np.isfinite(pos + nrm + vel + [T])):
        raise ValueError('pos, normal and vel must have 3 finite numbers each')
    if np.linalg.norm(nrm) < 1e-6: raise ValueError('normal must be a non-zero vector')
    if not 0.0 < T <= 5.0: raise ValueError('T must be in (0, 5.0] s from when the act takes effect')
    if not (abs(pos[0]) <= 3.4 and -7.5 <= pos[1] <= -0.3 and 0.2 <= pos[2] <= 3.0):
        raise ValueError('pos out of range: |x| <= 3.4, -7.5 <= y <= -0.3, 0.2 <= z <= 3.0')
    if np.linalg.norm(vel) > 8.0: raise ValueError('vel too large: |vel| <= 8 m/s')
    return {'type': 'act', 't': T, 'pos': pos, 'normal': nrm, 'vel': vel}


class Service:
    def __init__(self, data=DATA, workers=True):
        self.data = Path(data); self.data.mkdir(parents=True, exist_ok=True)
        self.w = bduel.World()
        self.source_sha = fingerprint()
        self.cond = threading.Condition(threading.RLock())
        self.log_lock = threading.Lock()
        self.slowdown = float(os.environ.get('SLOWDOWN', '20'))
        if not np.isfinite(self.slowdown) or self.slowdown <= 0: raise ValueError('invalid slowdown')
        self.period = DT*self.slowdown
        self.plan_lead_s = float(os.environ.get('WALLCLOCK_PLAN_LEAD_S', '0.4'))
        self.lead = max(1, int(math.ceil(self.plan_lead_s/self.period - 1e-9)))
        self.plan_timeout = float(os.environ.get('RCB_PLAN_TIMEOUT_S', '30'))
        self.t0 = time.monotonic()
        self.phase = 'prepare'
        self.joined = {s: False for s in SIDES}
        self.ready_seats = {s: False for s in SIDES}
        self.ready_deadline = None
        self.resume_at = None
        self.anchor = None
        self.reason = None
        self.forfeit = None
        self.finalized = False
        self.finalizing = False
        self.errors = []
        self.replay = {}
        self.video = False
        self.reviews = []
        self.pending = {}
        self.act_seq = 0
        self.plan_mismatch = 0
        self.lates = []; self.plan_wait = []; self.run_steps = 0; self.run_wall = 0.
        self.segment_start = None
        self.modes = {s: os.environ.get(f'PLAYER_MODE_{s}', os.environ.get('RCB_PLAYER_MODE', 'model')) for s in SIDES}
        self.clock = {s: ThinkClock(usage_file=str(self.data/f'think_usage_{s}.json'), mode=self.modes[s]) for s in SIDES}
        self.act_locks = {s: threading.Lock() for s in SIDES}
        self.view_locks = {s: threading.Lock() for s in SIDES}
        self.stats = {s: dict(attempts=0, applied=0, refused=0, refused_busy=0, dropped=0, observations=0,
                             plan_s=[], act_s=[], obs_age_s=[]) for s in SIDES}
        self.workers = {}
        self.bc = None                  # the spectator broadcast log (set in __main__)
        if workers:
            try:
                for s in SIDES:
                    for kind in ('plan', 'render'):
                        self.workers[kind, s] = ProcessWorker(kind, s)
            except Exception:
                self.close(); raise
        self.log(dict(ev='start', revision=bduel.REVISION, seed=bduel.SEED, first_receiver=bduel.FIRST_RECEIVER,
                      source_sha=self.source_sha, slowdown=self.slowdown, period_s=self.period, lead_steps=self.lead,
                      plan_lead_s=self.plan_lead_s, timing_policy='report_only', player_modes=self.modes,
                      act_rule=os.environ.get('RCB_ACT_RULE', 'per_response')))

    def bc_event(self, ev, **fields):
        if self.bc is not None: self.bc.event(ev, self.w.k, score=dict(self.w.score), **fields)

    def close(self):
        for worker in self.workers.values(): worker.close()

    def log(self, event):
        row = dict(ts=time.time(), wall=time.monotonic()-self.t0, step=self.w.k, **event)
        with self.log_lock:
            with (self.data/'episode.jsonl').open('a') as f: f.write(json.dumps(row, default=float)+'\n')

    # ------------------------------------------------------------------ what a seat knows without looking
    def state(self, side):
        w = self.w; rs = w.rs; other = OTHER[side]; me = w.sides[side]; ph = me.s
        c, n, _ = ph.racket_state()
        live = rs['state'] == 'live'
        ball = ('not yet served' if rs['state'] == 'ready' else 'dead' if not live
                else 'coming to you' if rs['expect'] == side else 'going to the opponent')
        heard = []
        if rs['state'] != 'ready':
            for e in w.events:
                if e['kind'] == 'hit':
                    heard.append(dict(event='you hit the shuttle' if e['side'] == side else 'the opponent hit the shuttle',
                                      t=round((e['k']-rs['launch'])*DT, 3)))
            heard.insert(0, dict(event='the machine served', t=0.0))
        la = me._last_act; active = me.plan_j < len(me.plan)
        k_hit = la.get('k_hit') if la else None
        command = ({'contact_in_s': round((k_hit-w.k)*DT, 3) if k_hit is not None and k_hit >= w.k else 'passed',
                    'phase': 'approach' if k_hit is not None and w.k < k_hit else 'follow_through',
                    'pos': la.get('racket_pos'), 'normal': la.get('racket_normal'), 'vel': la.get('racket_vel'),
                    'stroke': la.get('stroke')} if active and la else
                   'none (the robot returns to / holds the ready pose, the base to its home)')
        out = dict(phase=self.phase, done=self.phase == 'over', reason=self.reason, point=rs['point']+1,
                   score=dict(you=w.score[side], opponent=w.score[other]), t_sim=round(w.k*DT, 4), step=w.k,
                   world='running' if self.phase == 'running' else 'frozen', ready=dict(self.ready_seats),
                   you_receive_serve=rs['receiver'] == side, serve=rs['serve'],
                   ball_state=ball, ball_in_play=self.phase == 'running' and live,
                   serve_in_s=round(max(0., (rs['launch']-w.k)*DT), 3) if rs['state'] == 'ready' else None,
                   t_since_played=round((w.k-rs['played_k'])*DT, 3) if rs['state'] != 'ready' else None,
                   heard=heard, robot_base_xy=[round(float(x), 3) for x in ph.d.qpos[ph.qa[:2]]],
                   q_arm=[round(float(x), 4) for x in ph.d.qpos[ph.qa[2:]]],
                   racket_pos=[round(float(x), 3) for x in c], racket_normal=[round(float(x), 3) for x in n],
                   command=command,
                   points=[{k: (v if k != 'score' else dict(you=v[side], opponent=v[other])) for k, v in p.items()
                            if k in ('point', 'winner', 'how', 'score', 'let')} for p in w.points[-2:]])
        it = self.pending.get(side)
        if it: out['pending_act'] = dict(act_id=it['act_id'], takes_effect_at_step=it['k_e'])
        return out

    def failure(self, where, exc):
        with self.cond:
            if self.finalizing:            # after the match (the workers are closed): not a failure of the match
                self.log(dict(ev='late_request_error', where=where, error=str(exc)[:300])); return
            self.errors.append(dict(where=where, error=str(exc)[:300]))
            self.log(dict(ev='error', where=where, error=str(exc)[:300]))
            self.end('technical_error')

    # ------------------------------------------------------------------ start / review barrier
    def ready(self, side, body):
        # This potentially waits for a model stream; never hold the world lock here.
        self.clock[side].settle()
        with self.cond:
            if self.phase not in ('prepare', 'review'): return 409, dict(error='not awaiting ready', now=self.state(side))
            point = self.w.rs['point']
            if self.ready_seats[side]: return 409, dict(error='ready already submitted')
            why, plan = body.get('why', ''), body.get('plan', '')
            if not isinstance(why, str) or not isinstance(plan, str) or len(why) > REVIEW_MAX_CHARS or len(plan) > REVIEW_MAX_CHARS:
                return 400, dict(error=f'why and plan must be strings of at most {REVIEW_MAX_CHARS} characters')
            if self.phase == 'review' and (not why.strip() or not plan.strip()):
                return 400, dict(error='both review fields required: WHY (why the point was won or lost) and PLAN')
            self.joined[side] = True; self.ready_seats[side] = True
            if self.ready_deadline is None:
                window = os.environ.get('START_TIMEOUT_S') if self.phase == 'prepare' else None
                self.ready_deadline = time.monotonic()+float(window or os.environ.get('READY_TIMEOUT_S', '60'))
            if self.phase == 'review':
                self.reviews.append(dict(seat=side, after_point=len(self.w.points), why=why, plan=plan))
            self.log(dict(ev='ready', seat=side, point=point, why=why, plan=plan))
            if all(self.ready_seats.values()):
                self.resume_at = time.monotonic()+float(os.environ.get('BARRIER_LEAD_S', '.2'))
                self.log(dict(ev='barrier_scheduled', point=point, resume_wall=self.resume_at-self.t0))
            self.cond.notify_all()
            # Both responses are released by the same start event, not by a seat polling faster.
            while self.phase in ('prepare', 'review') and self.w.rs['point'] == point:
                self.cond.wait(.5)
            return 200, dict(accepted='ready', now=self.state(side),
                             note=f'the world is running: the next serve comes {bduel.READY_STEPS*DT:.1f} s of game time '
                                  f'after the resume' if self.phase == 'running' else None)

    # ------------------------------------------------------------------ act
    def act(self, side, body):
        dec = validate(body); arrived = time.monotonic()
        if not self.act_locks[side].acquire(False):
            with self.cond: self.stats[side]['refused_busy'] += 1
            return 429, dict(refused=True, busy=True,
                             error="busy: one act at a time; wait for the previous act's reply before sending another")
        try:
            with self.cond:
                self.stats[side]['attempts'] += 1
                if self.phase != 'running': return 409, dict(error='the world is not running', now=self.state(side))
                point = self.w.rs['point']
            if not self.clock[side].decided_by_model():
                with self.cond:
                    self.stats[side]['refused'] += 1
                    self.log(dict(ev='refused_not_model', seat=side, point=point))
                return 429, dict(error='act needs a fresh completed model response started after resume, one act per response')
            receipt = self.clock[side].last_call()
            with self.cond:
                if self.phase != 'running' or self.w.rs['point'] != point:
                    return 409, dict(error='the point ended during response confirmation', now=self.state(side))
                self.act_seq += 1
                k_q = self.w.k
                item = dict(act_id=self.act_seq, side=side, decision=dec, point=point, k_q=k_q, k_e=k_q+self.lead,
                            plan=None, result=None, dropped=False, arrived=arrived, model_call=receipt)
                snap = bduel.snapshot(self.w.sides[side])
                self.pending[side] = item
                self.log(dict(ev='act_received', seat=side, act_id=item['act_id'], point=point, decision=dec,
                              k_queued=k_q, k_effect=item['k_e'], model_call=receipt, arrived_wall=arrived-self.t0))
            try:
                out = self.workers['plan', side].call(dict(snap=snap, k_e=item['k_e'], decision=dec))
            except Exception as exc:  # noqa: BLE001  (the world thread falls back to planning inline)
                out = dict(error=repr(exc)[:200])
            with self.cond:
                item['plan'] = out
                self.cond.notify_all()
                while item['result'] is None and not item['dropped'] and self.phase == 'running':
                    self.cond.wait(.5)
                if item['result'] is None:
                    return 409, dict(error='act dropped before it took effect (the point ended first)', now=self.state(side))
                return 200, dict(call='act', act_id=item['act_id'], took_effect=item['result']['took_effect'],
                                 stroke=item['result'].get('stroke'), command=item['result'].get('command'),
                                 now=self.state(side))
        finally:
            self.act_locks[side].release()

    def apply_due(self):
        """At the start of a control step (cond held): the acts due now take effect (A, then B; the replay does the
        same). Waits (releasing the lock) for a plan not yet back from its planner process."""
        waited = 0.0
        for side in SIDES:
            item = self.pending.get(side)
            if not item or item['k_e'] != self.w.k: continue
            t0 = time.monotonic()
            got = self.cond.wait_for(lambda: item['plan'] is not None or self.phase != 'running', timeout=self.plan_timeout)
            waited += time.monotonic()-t0
            if self.phase != 'running': return waited
            sd = self.w.sides[side]
            pr = item['plan'] or {}
            src = 'planner'
            if got and 'res' in pr and pr['key'] == sd.state_key():
                info = bduel.install(sd, pr['res'])
            else:                               # never expected: the copy diverged or the planner failed; plan here
                self.plan_mismatch += 1; src = 'inline ' + str(pr.get('error', 'key mismatch'))[:80]
                info = bduel.apply_inline(sd, item['decision'])
            del self.pending[side]
            self.plan_wait.append(time.monotonic()-t0)
            dec = item['decision']
            elapsed = time.monotonic()-item['arrived']
            res = dict(took_effect=dict(step=self.w.k, t_sim=round(self.w.k*DT, 4), steps_after_request=self.w.k-item['k_q'],
                                        wall_s_after_request=round(elapsed, 4)))
            if dec['type'] == 'none':
                res['command'] = 'cleared: the robot returns to the ready pose, the base home'
            else:
                res['stroke'] = {k: info.get(k) for k in ('stroke', 'base', 'n_swing_steps_available', 'n_swing_steps',
                                                          'ik_residual', 'blade_error_m', 'normal_error_deg',
                                                          'speed_scale', 'racket_vel_delivered', 'T_from_now')}
            item['result'] = res
            st = self.stats[side]; st['applied'] += 1; st['act_s'].append(elapsed)
            if pr.get('plan_s') is not None: st['plan_s'].append(pr['plan_s'])
            self.log(dict(ev='act_applied', seat=side, k=self.w.k, act_id=item['act_id'], point=item['point'],
                          decision=dec, k_queued=item['k_q'], plan_source=src, plan_wait_ms=round(1e3*(time.monotonic()-t0), 2),
                          model_call=item['model_call']))
        return waited

    def drop_pending(self, why):
        for side, item in list(self.pending.items()):
            item['dropped'] = True; self.stats[side]['dropped'] += 1
            self.log(dict(ev='act_dropped', seat=side, act_id=item['act_id'], why=why))
        self.pending.clear()

    # ------------------------------------------------------------------ observe / wait
    def observe(self, side):
        if not self.view_locks[side].acquire(False): return 429, dict(error='one observation per seat may be in flight')
        try:
            with self.cond:
                now = self.state(side)
                if self.phase == 'over': return 200, dict(now=now, note='the match is over')
                hist = list(self.w.review_hist or []) if self.phase == 'review' else list(self.w.hist)
                if not hist: hist = [self.w.snap()]
                selected = [dict(hist[max(0, len(hist)-1-b)]) for b in reversed(bduel.VIEW_BACK)]
                self.stats[side]['observations'] += 1; obs_id = self.stats[side]['observations']
            out = self.workers['render', side].call(dict(snapshots=selected))
            age = max(0., time.monotonic()-selected[-1]['wall_mono'])
            with self.cond:
                self.stats[side]['obs_age_s'].append(age)
                self.log(dict(ev='observe', seat=side, obs_id=obs_id, view_steps=[x['k'] for x in selected], age_s=age))
                t_reply = round(self.w.k*DT, 4)
            # the same shape as the match task: the image and its frame data under `observation`
            return 200, dict(call='observe', now=now, observation=dict(
                obs_id=obs_id, image_png_b64=base64.b64encode(out['png']).decode(),
                view_steps=[x['k'] for x in selected], view_points=[x['point']+1 for x in selected],
                view_sim_times=[round(x['k']*DT, 4) for x in selected],
                view_times=[round((x['k']-x['played_k'])*DT, 3) for x in selected],
                t_sim_at_reply=t_reply, obs_age_wall_s=age, render_wall_s=out['worker_s']))
        finally: self.view_locks[side].release()

    def wait(self, side, body):
        try: duration = float(body.get('dt', 0))
        except (TypeError, ValueError): duration = float('nan')
        if not np.isfinite(duration) or not 0 < duration <= WAIT_MAX_S:
            return 400, dict(error=f'dt must be in (0, {WAIT_MAX_S:g}] game seconds')
        with self.cond:
            target = self.w.k+max(1, int(round(duration/DT))); point = self.w.rs['point']
            while self.phase == 'running' and self.w.rs['point'] == point and self.w.k < target: self.cond.wait(.5)
            return 200, dict(now=self.state(side))

    # ------------------------------------------------------------------ the world thread
    def end(self, reason, forfeiting=None):
        if self.finalizing: return
        if self.segment_start is not None: self.run_wall += time.monotonic()-self.segment_start; self.segment_start = None
        self.phase = 'over'; self.reason = reason; self.forfeit = forfeiting; self.finalizing = True
        self.drop_pending('match over')
        self.log(dict(ev='end', reason=reason, forfeiting=forfeiting, score=self.w.score, k_end=self.w.k))
        self.bc_event('end', reason=reason, forfeiting=forfeiting)
        self.cond.notify_all()
        threading.Thread(target=self.finalize, daemon=True).start()

    def loop(self):
        affinity('DUEL_WORLD_CPUS')
        try:
            while True:
                with self.cond:
                    if self.phase == 'over': return
                    now = time.monotonic()
                    if self.phase in ('prepare', 'review'):
                        if self.resume_at is not None and now >= self.resume_at:
                            epoch = time.time()
                            for clock in self.clock.values(): clock.begin_segment(epoch)
                            self.phase = 'running'; self.anchor = (now, self.w.k)
                            self.segment_start = now; self.resume_at = None; self.ready_deadline = None
                            self.ready_seats = {s: False for s in SIDES}
                            self.log(dict(ev='run', point=self.w.rs['point'], started_epoch=epoch))
                            self.bc_event('run')
                            self.cond.notify_all()
                        elif self.ready_deadline and now > self.ready_deadline:
                            missing = [s for s in SIDES if not self.ready_seats[s]]
                            self.end('ready_timeout' if all(self.joined.values()) and len(missing) == 1 else 'incomplete',
                                     missing[0] if len(missing) == 1 else None)
                            continue
                        else: self.cond.wait(.01); continue
                    a, k = self.anchor; due = a+(self.w.k-k+1)*self.period
                delay = due-time.monotonic()
                if delay > 0: time.sleep(min(delay, .02)); continue
                with self.cond:
                    if self.phase != 'running': continue
                    before = len(self.w.points)
                    self.apply_due()
                    if self.phase != 'running': continue
                    self.w.advance(); self.run_steps += 1
                    self.lates.append(max(0., time.monotonic()-due))
                    if self.bc is not None:
                        self.bc.after_step(self.w, len(self.w.points) > before)
                        for p in self.w.points[before:]:
                            self.bc.event('point', self.w.k, score=dict(self.w.score), winner=p.get('winner'),
                                          how=p.get('how'), n=len(self.w.points))
                    if len(self.w.points) > before:
                        self.log(dict(ev='point', point=self.w.points[-1]))
                        self.drop_pending('the point ended')
                        if self.w.done:
                            self.end('match_over')          # a winner always (bm.MAX_HITS cap: leader, else last point)
                        else:
                            self.phase = 'review'; self.run_wall += time.monotonic()-self.segment_start
                            self.segment_start = None
                            self.ready_deadline = time.monotonic()+float(os.environ.get('READY_TIMEOUT_S', '60'))
                            self.log(dict(ev='pause_for_review', point=self.w.rs['point']))
                            self.bc_event('pause')
                    self.cond.notify_all()
                    if self.w.k % 50 == 0 or self.phase != 'running': self.write_final()
        except Exception as exc: self.failure('world', exc)

    # ------------------------------------------------------------------ evidence
    def write_final(self):
        with self.cond:
            w = self.w; score = dict(w.score)
            usage = {s: read_usage(self.clock[s].usage_file) for s in SIDES}
            meter = {s: self.clock[s].mode == 'model' and (not u.get('epoch') or not u.get('requests')) for s, u in usage.items()}
            apis = {s: seat_api_errors(self.clock[s].usage_file, u) for s, u in usage.items()}   # model-API errors: transient vs unrecovered (api_errors.py)
            api = {s: a['api_failure'] for s, a in apis.items()}   # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
            targets_sha = w.targets_sha() if self.finalized else None
            replay_ok = (self.replay.get('state_sha') == w.state_sha() and self.replay.get('score') == score
                         and self.replay.get('targets_sha') == targets_sha and self.replay.get('steps') == w.k
                         and self.replay.get('source_sha') == self.source_sha and self.replay.get('winner') == self.w.winner)
            complete = self.reason == 'match_over' or (self.reason == 'ready_timeout' and self.forfeit in SIDES)
            valid = bool(self.finalized and complete and replay_ok and not self.errors and not any(meter.values())
                         and not any(api.values()))
            win = OTHER[self.forfeit] if self.forfeit else self.w.winner
            L = self.lates
            out = dict(revision=bduel.REVISION, source_sha=self.source_sha, seed=bduel.SEED,
                       first_receiver=bduel.FIRST_RECEIVER, state_sha=w.state_sha(), targets_sha=targets_sha,
                       forfeiting=self.forfeit, slowdown=self.slowdown, lead_steps=self.lead, score=score,
                       winner=win if valid else None, reason=self.reason, phase=self.phase, finalized=self.finalized,
                       graded_ready=self.finalized, valid_trial=valid, technical_failure=not valid,
                       timing_policy='report_only', timing_invalid=False, errors=self.errors, meter_error=meter,
                       proxy_error=api, deterministic=bool(replay_ok),
                       transient_api_errors={s: a['transient_api_errors'] for s, a in apis.items()},
                       unrecovered_api_errors={s: a['unrecovered_api_errors'] for s, a in apis.items()}, replay_score=self.replay.get('score'),
                       steps=w.k, points=w.points, hits=w.hits, seats=self.stats, reviews=self.reviews,
                       joined=self.joined, player_modes=self.modes, video=self.video, plan_mismatch=self.plan_mismatch,
                       elapsed_s=time.monotonic()-self.t0,
                       sim_lag=dict(late_max_s=max(L, default=0), late_p99_s=float(np.percentile(L, 99)) if L else 0,
                                    plan_wait_max_s=max(self.plan_wait, default=0), run_steps=self.run_steps,
                                    run_sim_s=self.run_steps*DT, run_wall_s=self.run_wall, period_s=self.period))
            path = self.data/'final.json.tmp'; path.write_text(json.dumps(out, default=float)); path.replace(self.data/'final.json')

    def finalize(self):
        try:
            with self.cond:
                acts = self.w.actions()
                payload = dict(A=acts['A'], B=acts['B'], seed=bduel.SEED, first_receiver=bduel.FIRST_RECEIVER,
                               source_sha=self.source_sha, revision=bduel.REVISION, k_end=self.w.k)
                (self.data/'trajectory.json').write_text(json.dumps(payload))
                # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the logged acts; same targets)
                np.savez(self.data/'trajectory.npz', A=np.asarray(acts['A'], dtype=np.float64),
                         B=np.asarray(acts['B'], dtype=np.float64), seed=bduel.SEED, first_receiver=bduel.FIRST_RECEIVER)
            subprocess.run([sys.executable, str(HERE/'replay.py'), str(self.data)], check=True,
                           timeout=float(os.environ.get('RCB_REPLAY_TIMEOUT_S', '300')))
            self.replay = json.loads((self.data/'replay_check.json').read_text())
            self.close()           # the match is over: free the workers' processes and threads before the video
            if os.environ.get('RCB_RENDER_VIDEO', '1') == '1':       # optional: a failure does not affect the verdict
                try:
                    subprocess.run([sys.executable, str(HERE/'replay.py'), str(self.data), '--video'], check=True,
                                   timeout=float(os.environ.get('RCB_VIDEO_TIMEOUT_S', '300')))
                    self.video = True
                except Exception as exc: self.log(dict(ev='video_error', error=str(exc)[:300]))
        except Exception as exc:
            self.errors.append(dict(where='replay', error=str(exc)[:300]))
        with self.cond:
            self.finalized = True; self.write_final(); self.cond.notify_all()

    def spec(self, side):
        return dict(seat=side, protocol='eai-standard-realtime/1.0', revision=bduel.REVISION,
                    simulator='mujoco 3.3.7 (robots) + point-mass shuttle with quadratic drag',
                    robot='franka-panda on an x-y sliding base + badminton racket',
                    base=dict(max_speed_mps=bduel.BASE_VMAX, max_accel_mps2=bduel.BASE_AMAX, home_xy=[0.0, -4.0]),
                    match=dict(win_points=bduel.WIN_POINTS, two_point_lead_from=bduel.WIN_POINTS - 1,
                               cap_points=bduel.CAP_POINTS, scoring='rally point', first_player=bduel.FIRST_RECEIVER,
                               first_receiver=bduel.FIRST_RECEIVER,
                               serves='a neutral machine on the server side\'s half serves into the receiver\'s diagonal '
                                      'service court; the receiver changes every point'),
                    timing=dict(slowdown=self.slowdown, control_dt_s=DT, period_s=self.period, wall_s_per_control_step=self.period,
                                wait_max_s=WAIT_MAX_S, act_lead_steps=self.lead, act_lead_game_s=round(self.lead*DT, 4),
                                act_lead_wall_s=round(self.lead*self.period, 4), policy='report_only',
                                rule=f'the world runs at 1/{self.slowdown:g} of real speed; an act queued at control step k '
                                     f'takes effect at step k + {self.lead}; the robot keeps its current command until then'),
                    review=dict(limit_s=float(os.environ.get('READY_TIMEOUT_S', '60')),
                                start_window_s=float(os.environ.get('START_TIMEOUT_S', '0') or 0)),
                    frame='your frame: x to your right, y towards the opponent, z up; your half y < 0, your home (0, -4.0)',
                    cameras=[dict(c, fovy_deg=45.0, tile_px=[480, 360], focal_px=434.6, principal_point_px=[240, 180],
                                  image_right='forward x up') for c in bm.Match.cam_info()],
                    image='2 rows (behind, side) x 4 columns (camera frames 60 ms apart, oldest left); tile 480 x 360',
                    world='floor z = 0; singles court |x| <= 2.59, |y| <= 6.70 (lines in); net plane y = 0, top z = 1.524 m, '
                          f'posts at x = +-3.05; your half y < 0. Robot base home (0, -4.0), base speed <= {bduel.BASE_VMAX:g} m/s',
                    shuttle=dict(model='point mass, gravity 9.81 + quadratic drag: dv/dt = g - K |v| v',
                                 K_per_m=round(bm.K_DRAG, 4), terminal_speed_mps=bm.V_TERM,
                                 bounce='none: the rally ends when it reaches the floor'),
                    decision_rule=('program play: your own program may observe and act without a new model response; one act per seat in flight'
                                   if os.environ.get('RCB_ACT_RULE') == 'program' else 'one fresh completed model response per act, after both players resume'))


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
                with SERVICE.cond: code, out = 200, SERVICE.state(side)
            else: code, out = 404, dict(error='unknown endpoint (GET spec status observe; POST start ready act wait)')
        except (ValueError, TypeError, KeyError) as exc: code, out = 400, dict(error=str(exc))
        except BlockingIOError as exc: code, out = 429, dict(error=str(exc))
        except Exception as exc:
            if isinstance(exc, MeterError) and not SERVICE.finalizing:
                SERVICE.errors.append(dict(where='meter', error=str(exc)[:300]))
            SERVICE.failure(ep, exc); code, out = 500, dict(error='technical failure', detail=str(exc)[:200])
        self.send(code, out)
    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch(True)


class BoundedHTTPServer(ThreadingHTTPServer):
    """Cap socket/handler work independently for each authenticated seat."""
    daemon_threads = True
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slots = {s: threading.BoundedSemaphore(4) for s in SIDES}
        self.arrivals = {s: [] for s in SIDES}
    def process_request(self, request, addr):
        side = next((s for s in SIDES if seat_allowed(s, addr[0])), None)
        if side is not None:
            now = time.monotonic(); self.arrivals[side] = [t for t in self.arrivals[side] if now-t < 1]
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
    affinity('DUEL_SERVER_CPUS')
    SERVICE = Service()
    if BroadcastLog is not None:
        SERVICE.bc = BroadcastLog(every=2, sport='badminton', mode='duel', slowdown=SERVICE.slowdown, dt=DT,
                                  seed=bduel.SEED, first_receiver=bduel.FIRST_RECEIVER, players={'A': 'A', 'B': 'B'})
        with SERVICE.cond: SERVICE.bc.snapshot(SERVICE.w.snap(), force=True)   # the scene before the first serve
    def stop(*args):
        def run():
            with SERVICE.cond: SERVICE.end('collected')
        threading.Thread(target=run, daemon=True).start()
    signal.signal(signal.SIGUSR1, stop)
    SERVICE.write_final()
    threading.Thread(target=SERVICE.loop, daemon=True).start()
    (DATA/'server.pid').write_text(str(os.getpid()))
    print(f'badminton duel ready (slowdown x{SERVICE.slowdown:g}, act lead {SERVICE.lead} steps)', flush=True)
    BoundedHTTPServer(('0.0.0.0', int(os.environ.get('RCB_PORT', '8000'))), Handler).serve_forever()
