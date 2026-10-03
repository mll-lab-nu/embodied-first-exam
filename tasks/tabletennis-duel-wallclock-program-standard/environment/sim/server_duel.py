"""Two-seat continuous wallclock service; all slow work runs outside the world lock."""
from __future__ import annotations
import base64
import copy
import hashlib
import json
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
import duel
from think_clock import ThinkClock, read_usage, MeterError
from api_errors import seat_api_errors  # noqa: E402
from workers import ProcessWorker, trajectory, affinity
try:                                            # spectator broadcast log (never read back; see broadcast_log.py)
    from broadcast_log import BroadcastLog
except ImportError:  # pragma: no cover
    BroadcastLog = None

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('RCB_DATA', '/data'))
DT = duel.CONTROL_DT


def fingerprint():
    h = hashlib.sha256()
    paths = list(HERE.glob('*.py')) + list((HERE/'scene').rglob('*'))
    paths += [HERE/n for n in ('instance.npz', 'serves_pool.json', 'rally.json')]
    for p in sorted(set(paths)):
        if p.is_file(): h.update(str(p.relative_to(HERE)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


class Service:
    def __init__(self, data=DATA, workers=True):
        self.data = Path(data); self.data.mkdir(parents=True, exist_ok=True)
        self.g = duel.Duel()
        self.source_sha = fingerprint()
        self.cond = threading.Condition(threading.RLock())
        self.log_lock = threading.Lock()
        self.slowdown = float(os.environ.get('SLOWDOWN', '20'))
        if not np.isfinite(self.slowdown) or self.slowdown <= 0: raise ValueError('invalid slowdown')
        self.period = DT*self.slowdown
        self.t0 = time.monotonic()
        self.phase = 'prepare'
        self.joined = {s: False for s in duel.SIDES}
        self.ready_seats = {s: False for s in duel.SIDES}
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
        self.commands = {s: None for s in duel.SIDES}
        self.lates = []; self.run_steps = 0; self.run_wall = 0.
        self.segment_start = None
        self.clock = {s: ThinkClock(usage_file=str(self.data/f'think_usage_{s}.json'),
                          mode=os.environ.get(f'PLAYER_MODE_{s}', os.environ.get('RCB_PLAYER_MODE','model')))
                      for s in duel.SIDES}
        self.act_locks = {s: threading.Lock() for s in duel.SIDES}
        self.view_locks = {s: threading.Lock() for s in duel.SIDES}
        self.stats = {s: dict(attempts=0, applied=0, refused=0, dropped=0, observations=0,
                             plan_s=[], act_s=[], obs_age_s=[]) for s in duel.SIDES}
        self.workers = {}
        self.bc = None                  # the spectator broadcast log (set in __main__)
        if workers:
            try:
                for kind in ('plan','render'):
                    for s in duel.SIDES: self.workers[kind,s] = ProcessWorker(kind,s)
            except Exception:
                self.close(); raise
        self.log(dict(ev='start',revision=duel.REVISION,seed=duel.SEED,first_receiver=duel.FIRST_RECEIVER,
                      source_sha=self.source_sha,slowdown=self.slowdown,timing_policy='report_only',
                      serves=self.g.serve_ids,player_modes={s:self.clock[s].mode for s in duel.SIDES}))

    def bc_frame(self, point_ended=False):
        """With the world lock held, after a control step: the broadcast frame (the point's last state if one ended)."""
        if self.bc is None: return
        g=self.g
        last=g.review_hist[-1] if point_ended and getattr(g,'review_hist',None) else None
        self.bc.frame(g.k,last['qpos'] if last else g.d.qpos,force=point_ended)
        if point_ended:
            p=g.points[-1]
            self.bc.event('point',g.k,score=dict(g.score),winner=p.get('winner'),how=p.get('how'),n=len(g.points))

    def bc_event(self, ev, **fields):
        if self.bc is not None: self.bc.event(ev,self.g.k,score=dict(self.g.score),**fields)

    def close(self):
        for worker in self.workers.values(): worker.close()

    def log(self, event):
        row=dict(ts=time.time(),wall=time.monotonic()-self.t0,step=self.g.k,**event)
        with self.log_lock:
            with (self.data/'episode.jsonl').open('a') as f: f.write(json.dumps(row,default=float)+'\n')

    def state(self, side):
        g=self.g; other=duel.OTHER[side]
        p=g.d.site_xpos[g.site_paddle[side]].copy()
        normal=g.d.site_xmat[g.site_paddle[side]].reshape(3,3)[:,0].copy()
        if side=='B': p,normal=duel.mir(p),duel.mir(normal)
        command=copy.deepcopy(self.commands[side])
        if command: command['contact_in_s']=max(0.,(command['contact_step']-g.k)*DT)
        return dict(phase=self.phase,done=self.phase=='over',reason=self.reason,point=g.rs['point']+1,
                    score=dict(you=g.score[side],opponent=g.score[other]),t_sim=g.k*DT,step=g.k,
                    ball='serve' if g.rs['last_hitter'] is None else 'return',
                    t_since_played=(g.k-g.rs['played_k'])*DT,
                    ready=dict(self.ready_seats),world='running' if self.phase=='running' else 'frozen',
                    serve_in_s=max(0.,(g.rs['launch']-g.k)*DT),ball_in_play=self.phase=='running' and g.in_play(),
                    ball_state='coming to you' if g.rs['expect']==side else 'going to opponent',
                    you_receive_serves=g.rs['receiver']==side,q=g.d.qpos[g.qadr[side]].tolist(),
                    paddle_pos=p.tolist(),paddle_normal=normal.tolist(),command=command,
                    points=[{k:v for k,v in p.items() if k!='receiver'} for p in g.points[-2:]],
                    heard=[dict(event={f'table_{side}':'bounce on your half',f'table_{other}':"bounce on the opponent's half",
                                       f'paddle_{side}':'paddle',f'paddle_{other}':'opponent hit',
                                       f'robot_{side}':'robot',f'robot_{other}':'opponent arm'}.get(x['kind'],x['kind']),
                                t=x['t']-g.rs['played_k']*DT) for x in g.events[-12:]
                           if x['t']>=g.rs['played_k']*DT-.011])

    def failure(self, where, exc):
        with self.cond:
            self.errors.append(dict(where=where,error=str(exc)[:300]))
            self.log(dict(ev='error',where=where,error=str(exc)[:300]))
            self.end('technical_error')

    def ready(self, side, body):
        # This potentially waits for a model stream; never hold the world lock here.
        self.clock[side].settle()
        with self.cond:
            if self.phase not in ('prepare','review'): return 409,dict(error='not awaiting ready',now=self.state(side))
            point=self.g.rs['point']
            if self.ready_seats[side]: return 409,dict(error='ready already submitted')
            why,plan=body.get('why',''),body.get('plan','')
            if not isinstance(why,str) or not isinstance(plan,str) or len(why)>2000 or len(plan)>2000:
                return 400,dict(error='why and plan must be strings of at most 2000 characters')
            if self.phase=='review' and (not why.strip() or not plan.strip()):
                return 400,dict(error='both review fields required')
            self.joined[side]=True; self.ready_seats[side]=True
            if self.ready_deadline is None:
                # the start window (program play: time for the second player to finish preparing) and the review budget
                window=os.environ.get('START_TIMEOUT_S') if self.phase=='prepare' else None
                self.ready_deadline=time.monotonic()+float(window or os.environ.get('READY_TIMEOUT_S','60'))
            if self.phase=='review': self.reviews.append(dict(seat=side,after_point=len(self.g.points),why=why,plan=plan))
            self.log(dict(ev='ready',seat=side,point=point,why=why,plan=plan))
            if all(self.ready_seats.values()):
                self.resume_at=time.monotonic()+float(os.environ.get('BARRIER_LEAD_S','.2'))
                self.log(dict(ev='barrier_scheduled',point=point,resume_wall=self.resume_at-self.t0))
            self.cond.notify_all()
            # Both responses are released by the same start event, not by a seat polling faster.
            while self.phase in ('prepare','review') and self.g.rs['point']==point:
                self.cond.wait(.5)
            return 200,dict(accepted='ready',now=self.state(side))

    def validate(self, body):
        if body.get('type')=='none': return {'type':'none'}
        try:
            if body.get('type')!='act': raise ValueError('use act or none')
            dec={k:[float(x) for x in body[k]] for k in ('pos','normal','vel')}
            T=float(body['t'])
            if any(len(v)!=3 for v in dec.values()) or not np.isfinite([T]+sum(dec.values(),[])).all():
                raise ValueError('finite three-dimensional vectors required')
            if not 0<T<=2.5: raise ValueError('T must be 0 < T <= 2.5 game seconds from effect')
            x,y,z=dec['pos']
            if not (abs(x)<=1.2 and -2.5<=y<=-.5 and 0<=z<=1.2): raise ValueError('position out of range')
            if np.linalg.norm(dec['normal'])<1e-6 or np.linalg.norm(dec['vel'])>8: raise ValueError('invalid normal or speed')
            return dict(type='act',t=T,**dec)
        except (TypeError,KeyError,ValueError) as exc: raise ValueError(str(exc)) from exc

    def act(self, side, body):
        dec=self.validate(body); arrived=time.monotonic()
        if not self.act_locks[side].acquire(False): return 429,dict(error='one act request per seat may be in flight')
        try:
            with self.cond:
                self.stats[side]['attempts']+=1
                if self.phase!='running': return 409,dict(error='world is not running',now=self.state(side))
                point=self.g.rs['point']
            if not self.clock[side].decided_by_model():
                with self.cond:
                    self.stats[side]['refused']+=1
                    self.log(dict(ev='refused_not_model',seat=side,point=point))
                return 429,dict(error='act needs a fresh completed response started after resume, one act per response')
            receipt=self.clock[side].last_call()
            with self.cond:
                if self.phase!='running' or self.g.rs['point']!=point: return 409,dict(error='point ended during response confirmation')
                job=dict(decision=dec,point=point,ordinal=self.stats[side]['attempts'],
                         q=self.g.d.qpos[self.g.qadr[side]].tolist(),target=self.g.target[side].tolist())
                self.log(dict(ev='act_received',seat=side,point=point,decision=dec,model_call=receipt,
                              arrived_wall=arrived-self.t0,planning_started_wall=time.monotonic()-self.t0))
            prepared=None
            if dec['type']=='act': prepared=self.workers['plan',side].call(job)
            with self.cond:
                if prepared: self.stats[side]['plan_s'].append(prepared['worker_s'])
                if self.phase!='running' or self.g.rs['point']!=point:
                    self.stats[side]['dropped']+=1
                    self.log(dict(ev='act_dropped',seat=side,point=point,why='point ended during planning'))
                    return 409,dict(error='point ended during planning',now=self.state(side))
                item=dict(point=point,decision=dec,prepared=prepared,model_call=receipt,arrived=arrived,result=None)
                self.pending[side]=item
                self.log(dict(ev='plan_ready',seat=side,point=point,worker_s=prepared['worker_s'] if prepared else 0))
                while item['result'] is None and self.phase=='running' and self.g.rs['point']==point:
                    self.cond.wait(.5)
                if item['result'] is None: return 409,dict(error='point ended before effect',now=self.state(side))
                return 200,dict(call='act',took_effect=item['result'],now=self.state(side))
        finally:
            self.act_locks[side].release()

    def apply_pending(self):
        # Entire ready batch installs at one boundary; expensive work is already complete.
        batch=self.pending; self.pending={}
        for side,item in batch.items():
            if item['point']!=self.g.rs['point']: self.stats[side]['dropped']+=1; continue
            dec=item['decision']; info={}
            if dec['type']=='none': self.g.plan[side]=[]; self.g.plan_j[side]=0; self.commands[side]=None
            else:
                prev=self.g.actions[side][-2] if (len(self.g.actions[side])>=2 and
                    np.array_equal(self.g.target[side],self.g.actions[side][-1])) else self.g.target[side]
                path,info=trajectory(self.g.target[side],prev,item['prepared'],dec['t'],self.g.JLOW,self.g.JHIGH)
                self.g.plan[side]=path; self.g.plan_j[side]=0
                self.commands[side]=dict(pos=dec['pos'],normal=dec['normal'],vel=dec['vel'],
                                         contact_step=self.g.k+info['contact_steps'])
                info.update(ik_residual=item['prepared']['ik_residual'],
                            speed_scale=item['prepared']['speed_scale'])
            elapsed=time.monotonic()-item['arrived']
            result=dict(step=self.g.k,t_sim=self.g.k*DT,wall_s_after_request=elapsed,**info)
            item['result']=result; self.stats[side]['applied']+=1; self.stats[side]['act_s'].append(elapsed)
            self.log(dict(ev='act_applied',seat=side,k=self.g.k,point=item['point'],decision=dec,
                          model_call=item['model_call'],effect=result))

    def observe(self, side):
        if not self.view_locks[side].acquire(False): return 429,dict(error='one observation per seat may be in flight')
        try:
            with self.cond:
                now=self.state(side)
                hist=self.g.review_hist if self.phase=='review' and hasattr(self.g,'review_hist') else list(self.g.hist)
                if not hist: hist=[dict(k=self.g.k,qpos=self.g.d.qpos.copy(),played_k=self.g.rs['played_k'],
                                       point=self.g.rs['point'],wall_mono=time.monotonic())]
                hist=copy.deepcopy(hist); rs=copy.deepcopy(self.g.rs)
                selected=[hist[max(0,len(hist)-1-b)] for b in reversed(self.g.VIEW_BACK)]
                self.stats[side]['observations']+=1; obs_id=self.stats[side]['observations']
            out=self.workers['render',side].call(dict(snapshots=hist,rs=rs))
            age=max(0.,time.monotonic()-selected[-1]['wall_mono'])
            with self.cond:
                self.stats[side]['obs_age_s'].append(age)
                self.log(dict(ev='observe',seat=side,obs_id=obs_id,view_steps=[x['k'] for x in selected],age_s=age))
            return 200,dict(call='observe',now=now,observation=dict(
                            obs_id=obs_id,image_png_b64=base64.b64encode(out['png']).decode(),
                            view_steps=[x['k'] for x in selected],view_points=[x['point']+1 for x in selected],
                            view_sim_times=[x['k']*DT for x in selected],obs_age_wall_s=age,render_wall_s=out['worker_s']))
        finally: self.view_locks[side].release()

    def wait(self, side, body):
        duration=float(body.get('dt',0))
        if not np.isfinite(duration) or not 0<duration<=1: return 400,dict(error='dt must be 0..1 game seconds')
        with self.cond:
            target=self.g.k+int(np.ceil(duration/DT)); point=self.g.rs['point']
            while self.phase=='running' and self.g.rs['point']==point and self.g.k<target: self.cond.wait(.5)
            return 200,dict(now=self.state(side))

    def end(self, reason, forfeiting=None):
        if self.finalizing: return
        if self.segment_start is not None: self.run_wall+=time.monotonic()-self.segment_start; self.segment_start=None
        self.phase='over'; self.reason=reason; self.forfeit=forfeiting; self.finalizing=True
        self.pending.clear()
        self.log(dict(ev='end',reason=reason,forfeiting=forfeiting))
        self.bc_event('end',reason=reason,winner=duel.OTHER[forfeiting] if forfeiting else self.g.winner)
        self.cond.notify_all()
        threading.Thread(target=self.finalize,daemon=True).start()

    def loop(self):
        affinity('DUEL_WORLD_CPUS')
        try:
            while True:
                with self.cond:
                    if self.phase=='over': return
                    now=time.monotonic()
                    if self.phase in ('prepare','review'):
                        if self.resume_at is not None and now>=self.resume_at:
                            epoch=time.time()
                            for clock in self.clock.values(): clock.begin_segment(epoch)
                            self.phase='running'; self.g.review_done(); self.anchor=(now,self.g.k)
                            self.segment_start=now; self.resume_at=None; self.ready_deadline=None
                            self.ready_seats={s:False for s in duel.SIDES}
                            self.log(dict(ev='run',point=self.g.rs['point'],started_epoch=epoch))
                            self.bc_event('run')
                            self.cond.notify_all()
                        elif self.ready_deadline and now>self.ready_deadline:
                            missing=[s for s in duel.SIDES if not self.ready_seats[s]]
                            self.end('ready_timeout' if all(self.joined.values()) and len(missing)==1 else 'incomplete',
                                     missing[0] if len(missing)==1 else None)
                            continue
                        else: self.cond.wait(.01); continue
                    a,k=self.anchor; due=a+(self.g.k-k+1)*self.period
                delay=due-time.monotonic()
                if delay>0: time.sleep(min(delay,.02)); continue
                with self.cond:
                    if self.phase!='running': continue
                    before=len(self.g.points)
                    self.apply_pending(); self.g.advance(); self.run_steps+=1
                    self.lates.append(max(0.,time.monotonic()-due))
                    self.bc_frame(len(self.g.points)>before)
                    if len(self.g.points)>before:
                        self.log(dict(ev='point',point=self.g.points[-1]))
                        for side in self.pending: self.stats[side]['dropped']+=1
                        self.pending.clear(); self.commands={s:None for s in duel.SIDES}
                        if self.g.done: self.end('match_over')
                        else:
                            self.phase='review'; self.run_wall+=time.monotonic()-self.segment_start
                            self.segment_start=None; self.ready_deadline=time.monotonic()+float(os.environ.get('READY_TIMEOUT_S','60'))
                            self.log(dict(ev='pause_for_review',point=self.g.rs['point']))
                            self.bc_event('pause')
                    self.cond.notify_all()
                    if self.g.k%50==0 or self.phase!='running': self.write_final()
        except Exception as exc: self.failure('world',exc)

    def write_final(self):
        with self.cond:
            g=self.g; score=dict(g.score)
            usage={s:read_usage(self.clock[s].usage_file) for s in duel.SIDES}
            meter={s:self.clock[s].mode=='model' and (not u.get('epoch') or not u.get('requests')) for s,u in usage.items()}
            apis={s:seat_api_errors(self.clock[s].usage_file,u) for s,u in usage.items()}   # model-API errors: transient vs unrecovered (api_errors.py)
            api={s:a['api_failure'] for s,a in apis.items()}   # unrecovered, or more than MAX_TRANSIENT_API_ERRORS
            targets_sha=hashlib.sha256(json.dumps({s:[q.tolist() for q in g.actions[s]] for s in duel.SIDES},sort_keys=True,separators=(',',':')).encode()).hexdigest()
            replay_ok=(self.replay.get('state_sha')==g.state_sha() and self.replay.get('score')==score
                       and (self.forfeit or self.replay.get('winner')==g.winner)
                       and self.replay.get('targets_sha')==targets_sha and self.replay.get('steps')==g.k
                       and self.replay.get('source_sha')==self.source_sha)
            complete=self.reason=='match_over' or (self.reason=='ready_timeout' and self.forfeit in duel.SIDES)
            valid=bool(self.finalized and complete and replay_ok and not self.errors and not any(meter.values()) and not any(api.values()))
            win=duel.OTHER[self.forfeit] if self.forfeit else g.winner
            out=dict(revision=duel.REVISION,source_sha=self.source_sha,seed=duel.SEED,first_receiver=duel.FIRST_RECEIVER,
                     state_sha=g.state_sha(),targets_sha=targets_sha,forfeiting=self.forfeit,
                     slowdown=self.slowdown,score=score,winner=win if valid else None,reason=self.reason,phase=self.phase,
                     finalized=self.finalized,graded_ready=self.finalized,valid_trial=valid,technical_failure=not valid,
                     timing_policy='report_only',timing_invalid=False,errors=self.errors,meter_error=meter,proxy_error=api,
                     transient_api_errors={s:a['transient_api_errors'] for s,a in apis.items()},
                     unrecovered_api_errors={s:a['unrecovered_api_errors'] for s,a in apis.items()},
                     deterministic=bool(replay_ok),replay_score=self.replay.get('score'),steps=g.k,points=g.points,hits=g.hits,
                     seats=self.stats,reviews=self.reviews,joined=self.joined,player_modes={s:self.clock[s].mode for s in duel.SIDES},
                     video=self.video,elapsed_s=time.monotonic()-self.t0,
                     sim_lag=dict(late_max_s=max(self.lates,default=0),late_p99_s=float(np.percentile(self.lates,99)) if self.lates else 0,
                                  run_steps=self.run_steps,run_sim_s=self.run_steps*DT,run_wall_s=self.run_wall,
                                  period_s=self.period))
            path=self.data/'final.json.tmp';path.write_text(json.dumps(out,default=float));path.replace(self.data/'final.json')

    def finalize(self):
        try:
            with self.cond:
                payload=dict(A=[x.tolist() for x in self.g.actions['A']],B=[x.tolist() for x in self.g.actions['B']],
                             seed=duel.SEED,first_receiver=duel.FIRST_RECEIVER,source_sha=self.source_sha,revision=duel.REVISION)
                (self.data/'trajectory.json').write_text(json.dumps(payload))
                # PROTOCOL §4.8: the trajectory also as trajectory.npz (the replay reads the JSON; same actions)
                np.savez(self.data/'trajectory.npz',A=np.asarray(payload['A'],dtype=np.float64),
                         B=np.asarray(payload['B'],dtype=np.float64),seed=duel.SEED,first_receiver=duel.FIRST_RECEIVER)
            subprocess.run([sys.executable,str(HERE/'replay.py'),str(self.data)],check=True,timeout=300)
            self.replay=json.loads((self.data/'replay_check.json').read_text())
            if os.environ.get('RCB_RENDER_VIDEO','1')=='1':
                try:
                    subprocess.run([sys.executable,str(HERE/'replay.py'),str(self.data),'--video'],check=True,timeout=120)
                    self.video=True
                except Exception as exc: self.log(dict(ev='video_error',error=str(exc)))
        except Exception as exc:
            self.errors.append(dict(where='replay',error=str(exc)))
        with self.cond:
            self.finalized=True;self.write_final();self.cond.notify_all()

    def spec(self, side):
        return dict(seat=side,protocol='eai-standard-realtime/1.0',revision=duel.REVISION,
                    timing=dict(slowdown=self.slowdown,control_dt=DT,period_s=self.period,policy='report_only'),
                    frame='your base is (0,-1.75,0), facing +y; your half y<0; table top z=0',
                    cameras=[dict(c,tile_px=[480,360],focal_px=434.6,principal_point_px=[240,180]) for c in duel.match.Match.CAM_INFO],
                    decision_rule=('program play: your own program may observe and act without a new model response; one act per seat in flight'
                                   if os.environ.get('RCB_ACT_RULE')=='program' else 'one fresh completed model response per act, after both players resume'),
                    match=dict(win_points=duel.WIN_POINTS,win_by=duel.WIN_BY,cap_points=duel.CAP_POINTS,
                               expedite_returns=duel.EXPEDITE_RETURNS,first_receiver=duel.FIRST_RECEIVER,
                               format=f'first to {duel.WIN_POINTS}; from {duel.WIN_POINTS-1}:{duel.WIN_POINTS-1} lead by '
                                      f'{duel.WIN_BY}, up to {duel.CAP_POINTS} (at {duel.CAP_POINTS-1}:{duel.CAP_POINTS-1} '
                                      'the next point wins); the receiver changes every point'),
                    win_points=duel.WIN_POINTS)


SERVICE=None


def seat_allowed(side,addr):
    hosts=dict(x.split('=',1) for x in os.environ.get('SEAT_HOSTS','').split(',') if '=' in x)
    if side not in hosts: return addr in ('127.0.0.1','::1')
    try: return addr in {a[4][0] for a in socket.getaddrinfo(hosts[side],None)}
    except OSError: return False


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args): pass
    def send(self,code,value):
        raw=json.dumps(value,default=float).encode();self.send_response(code)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Connection','close');self.end_headers();self.close_connection=True
        try: self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError): pass
    def setup(self):
        super().setup(); self.connection.settimeout(10)
    def dispatch(self,post=False):
        bits=self.path.strip('/').split('/')
        if len(bits)!=2 or bits[0] not in duel.SIDES or not seat_allowed(bits[0],self.client_address[0]):
            return self.send(403,dict(error='seat not authorized'))
        side,ep=bits; body={}
        try:
            if post:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<=size<=32768: raise ValueError('request too large')
                body=json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body,dict): raise ValueError('object required')
            if post and ep in ('start','ready'): code,out=SERVICE.ready(side,body)
            elif post and ep=='act': code,out=SERVICE.act(side,body)
            elif post and ep=='wait': code,out=SERVICE.wait(side,body)
            elif ep=='observe': code,out=SERVICE.observe(side)
            elif not post and ep=='spec': code,out=200,SERVICE.spec(side)
            elif not post and ep=='status':
                with SERVICE.cond: code,out=200,SERVICE.state(side)
            else: code,out=404,dict(error='unknown endpoint')
        except (ValueError,TypeError,KeyError) as exc: code,out=400,dict(error=str(exc))
        except BlockingIOError as exc: code,out=429,dict(error=str(exc))
        except Exception as exc:
            SERVICE.failure(ep,exc);code,out=500,dict(error='technical failure',detail=str(exc)[:200])
        self.send(code,out)
    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch(True)


class BoundedHTTPServer(ThreadingHTTPServer):
    """Cap socket/handler work independently for each authenticated seat."""
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.slots={s:threading.BoundedSemaphore(4) for s in duel.SIDES}
        self.arrivals={s:[] for s in duel.SIDES}
    def process_request(self,request,addr):
        side=next((s for s in duel.SIDES if seat_allowed(s,addr[0])),None)
        if side is not None:
            now=time.monotonic();self.arrivals[side]=[t for t in self.arrivals[side] if now-t<1]
        limited=side is not None and len(self.arrivals[side])>=20
        if side is None or limited or not self.slots[side].acquire(False):
            try:
                request.settimeout(.1)
                request.sendall(b'HTTP/1.1 429 Too Many Requests\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError: pass
            self.shutdown_request(request); return
        self.arrivals[side].append(time.monotonic())
        try: super().process_request(request,(addr[0],addr[1],side))
        except Exception:
            self.slots[side].release(); raise
    def process_request_thread(self,request,addr):
        try: super().process_request_thread(request,addr[:2])
        finally: self.slots[addr[2]].release()


if __name__=='__main__':
    affinity('DUEL_SERVER_CPUS')
    SERVICE=Service()
    if BroadcastLog is not None:
        SERVICE.bc=BroadcastLog(every=2,sport='tabletennis',mode='duel',slowdown=SERVICE.slowdown,dt=DT,seed=duel.SEED,
                                first_receiver=duel.FIRST_RECEIVER,nq=int(SERVICE.g.m.nq),players={'A':'A','B':'B'})
        with SERVICE.cond: SERVICE.bc_frame()   # the scene before the first serve
    def stop(*args):
        with SERVICE.cond: SERVICE.end('collected')
    signal.signal(signal.SIGUSR1,stop)
    (DATA/'server.pid').write_text(str(os.getpid()))
    SERVICE.write_final()
    threading.Thread(target=SERVICE.loop,daemon=True).start()
    print('wallclock duel ready',flush=True)
    BoundedHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
