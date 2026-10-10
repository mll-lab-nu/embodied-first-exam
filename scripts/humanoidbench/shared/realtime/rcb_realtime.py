"""eai-standard/2.3, the standard-realtime mode's protocol: the sim service of HumanoidBench's `-standard-realtime` tasks
(docs/PROTOCOL.md §4b, docs/LIMITED_MODE_PROTOCOL.md "Standard-realtime mode"; docs/benchmarks/humanoidbench.md). Entry
point of the sidecar: `python /srv/rcb_realtime.py` (the adapter is server.py's, unchanged). 2.3 is 2.2 plus the realtime
capability, every 2.2 addition optional: this service is rcb_service's 2.1 service with the capability, and reports
eai-standard/2.3.

It extends rcb_service.Service: the same endpoints, RCB1 frames, budgets (reset, wall clock), evidence, crash recovery
and finalize. Only the time model differs. In standard mode time moves only inside calls; here the episode has a clock:

- An episode starts paused, at the frozen start with the servos holding their starting targets. Its clock starts at its
  first POST /submit or POST /observe with seconds > 0 (again after every reset, and after a crash recovery). From then
  on one control step runs every control_dt x slowdown seconds of wall time, whether or not the agent sends anything,
  until the episode ends; the clock stops there.
- The service keeps a plan: one target row per coming control step. /submit expands its chunk (rows dt apart, `linear`
  or `hold`, exactly as 2.1 does) into control steps and writes it into the plan from control step `at` (default: the
  next one), replacing whatever was planned from there on, and answers at once. A chunk that arrives after its `at`
  loses the rows whose steps are gone (`late_steps`). When the plan runs out the last target is held (zero-order
  hold): a slow agent's robot keeps its last servo targets.
- /observe with seconds = 0 answers at once; with seconds > 0 it watches the running episode that long (robot time)
  and returns what the cameras saw. It never changes the plan.
- `cameras = []` asks for no images at all (in 2.1 an empty list means every camera): a controller's proprio-only call.

Grading is unchanged: every executed control step's sim row is journaled (trajectory_live.f64) and the graded episode's
rows are replayed in a fresh simulator at the end. What is graded is the rows the simulator applied, not what was
submitted, so the replay equals the live run however the timing went. Evidence added (never visible to the agent):
ticks.f64 (per journal row: wall time, and the call whose chunk gave the row, -1 for a held one), calls.jsonl (one line
per call; no calls/NNNNNN/ directories: a controller calls 50 times a second) and submitted.f64 (every row as sent:
call id, then the row). final.json adds realtime, slowdown, max_lag_s, stalls, held_steps, late_steps and
max_queue_wait_s (the longest a request waited for the simulator thread).

Threads: the simulator and its GL context belong to the main thread, which runs the clock and serves every request in
between control steps; the HTTP threads only read, queue and encode. A control step that is due runs before any waiting
request. A service that falls behind (a long render, a simulator step slower than control_dt, a busy host) runs the
missed steps back to back, skipping none, and serves one waiting request after each of them, so a request waits at most
about a step's time; more than MAX_LAG_S behind, it drops the debt instead (a stall, counted) rather than fast-forward the
robot.

A crash resumes the same episode from its last checkpoint (one per second of robot time while the clock runs), paused.
A simulator crash is an infrastructure failure, never the agent's (PROTOCOL §4b, owner 2026-10-08). No call spans a
crash here (submit answers at once), so a crash is never put down to the agent's call: past RCB_MAX_RESUMES restarts the
trial ends `sim_crashed` (infra_error), a failed resume `resume_failed` (infra_error), and a simulator error that ends
the graded episode (reason "error") sets infra_error in final.json too.
"""
from __future__ import annotations

import collections
import json
import os
import queue
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import numpy as np

import rcb_service
from rcb_service import MAX_BODY, Recorder, Refused, Service, bad_request

PROTOCOL = "eai-standard/2.3"   # the standard-realtime mode's protocol (PROTOCOL §4b); rcb_service.py itself serves 2.1
MAX_LAG_S = 0.5          # behind the clock by more than this: drop the debt (a stall) instead of catching up
CHECKPOINT_S = 1.0       # robot time between checkpoints while the clock runs (the most a crash loses)


class _Job:
    """One HTTP request, handed from its HTTP thread to the simulator's thread and back."""

    def __init__(self, method: str, path: str, body: bytes, content_length: int | None = None):
        self.method, self.path, self.body, self.content_length = method, path, body, content_length
        self.queued = time.monotonic()
        self.done = threading.Event()
        self.reply: tuple = ()           # ("raw", code, ctype, body) | ("rcb1", meta, parts) | ("rec", meta, Recorder)

    def finish(self, *reply) -> None:
        self.reply = reply
        self.done.set()


class _Watch:
    """A pending /observe with seconds > 0: completes once its control steps have run (or the episode ended)."""

    def __init__(self, job: _Job, rec: Recorder, start: int, steps: int, cameras: list[str], obs_id: int):
        self.job, self.rec, self.cameras, self.obs_id = job, rec, cameras, obs_id
        self.start, self.end = start, start + steps


class RealtimeService(Service):
    """rcb_service.Service with the realtime clock (module docstring)."""

    def __init__(self, sim, *, slowdown: float | None = None, **kw):
        self.slowdown = float(os.environ.get("RCB_SLOWDOWN") or 1.0) if slowdown is None else float(slowdown)
        if not self.slowdown > 0:
            raise ValueError("RCB_SLOWDOWN must be > 0")
        self.wall_dt = sim.control_dt * self.slowdown
        self.max_ahead = int(round(float(kw.get("max_chunk_s", 10.0)) / sim.control_dt))   # how far ahead `at` may be
        self.plan: collections.deque = collections.deque()   # (type, row, call id) for each coming control step
        self.running = False
        self.anchor_t = self.anchor_n = 0                  # the clock: control step anchor_n was due at anchor_t
        self.watches: list[_Watch] = []
        self.q: queue.Queue = queue.Queue()
        self.max_lag = self.lag = 0.0
        self.stalls = self.held_steps = self.late_steps = 0
        self.max_queue_wait = 0.0
        self._ticks: list[tuple[float, float]] = []        # (wall time, call id) per journal row not yet on disk
        super().__init__(sim, **kw)
        self.ticks_path = os.path.join(self.data, "ticks.f64")
        self.ckpt_every = max(1, int(round(CHECKPOINT_S / sim.control_dt)))

    # ------------------------------------------------------------------ spec, status, evidence
    def _spec(self) -> dict:
        spec = super()._spec()
        spec["protocol"] = PROTOCOL
        cdt = self.sim.control_dt
        spec["timing"] = {
            "realtime": True, "slowdown": self.slowdown, "control_dt": cdt,
            "wall_s_per_control_step": cdt * self.slowdown,
            "clock": "an episode starts paused; its clock starts at its first submit or observe with seconds > 0 (also "
                     "after a reset) and then runs one control step every wall_s_per_control_step seconds, whatever "
                     "you do, until the episode ends",
            "submit": "answers at once: the chunk (rows dt apart, linear or hold) becomes the plan from control step "
                      "`at` (default: the next one), replacing what was planned from there; rows for steps already "
                      "gone are dropped (meta.late_steps); after the plan's last row that target is held",
            "observe": "seconds = 0: now, at once; seconds > 0: watches the running episode that long and returns what "
                       "the cameras saw; never changes the plan",
            "max_ahead_steps": self.max_ahead,
            "no_images": "cameras = [] returns no images, only proprioception (the fastest call)"}
        return spec

    def _realtime_counters(self) -> dict:
        return {"running": self.running, "planned_steps": len(self.plan), "lag_s": round(self.lag, 4)}

    def status(self) -> dict:
        return {**super().status(), **self._realtime_counters()}

    def meta(self) -> dict:
        return {**super().meta(), **self._realtime_counters()}

    def _timing_record(self) -> dict:
        return {"protocol": PROTOCOL, "realtime": 1, "slowdown": self.slowdown, "max_lag_s": round(self.max_lag, 4),
                "stalls": self.stalls, "held_steps": self.held_steps, "late_steps": self.late_steps,
                "max_queue_wait_s": round(self.max_queue_wait, 4)}

    def _write_final(self) -> None:
        self.verdict.update(self._timing_record())   # final.json merges the verdict; none of these keys is a verdict's
        if self.reason == "error":                   # a simulator error ended the graded episode: infrastructure (§4b)
            self.verdict["infra_error"] = 1
        else:                                        # (an episode that erred and was reset away is not graded)
            self.verdict.pop("infra_error", None)
        super()._write_final()

    def _checkpoint(self, ev: str, **kw) -> None:
        if self._ticks:                              # the tick log first: a crash in between leaves it too long
            with open(self.ticks_path, "ab") as f:
                f.write(np.asarray(self._ticks, dtype=np.float64).tobytes())
            self._ticks = []
        super()._checkpoint(ev, **kw)

    def _save_call(self, meta: dict, actions: np.ndarray | None) -> None:
        keep = ("type", "n_rows", "dt", "interpolate", "at", "start_step", "late_steps", "planned_steps", "seconds",
                "control_steps", "episode", "done", "reason", "n_clipped", "lag_s", "note")
        line = {"call": self.calls, "ts": time.time(), **{k: meta[k] for k in keep if k in meta}}
        with open(os.path.join(self.data, "calls.jsonl"), "a") as f:
            f.write(json.dumps(line) + "\n")
        if actions is not None:
            rows = np.concatenate([np.full((len(actions), 1), float(self.calls)), actions], axis=1)
            with open(os.path.join(self.data, "submitted.f64"), "ab") as f:
                f.write(np.asarray(rows, dtype=np.float64).tobytes())

    # ------------------------------------------------------------------ start, clock
    def start(self) -> None:
        super().start()
        rows = np.fromfile(self.ticks_path, dtype=np.float64) if os.path.exists(self.ticks_path) else np.zeros(0)
        n = self.journal_rows
        if rows.size > 2 * n:                        # the steps a crash lost from the journal go from the tick log too
            rows[: 2 * n].tofile(self.ticks_path)
        elif rows.size < 2 * n:                      # (an older tick log, short of the journal: pad it as unknown)
            np.concatenate([rows, np.full(2 * n - rows.size, np.nan)]).tofile(self.ticks_path)
        self.running = False                         # a resumed episode waits, paused, for the agent's next call

    def _start_clock(self) -> None:
        if not self.running and not self.done and not self.stopping:
            self.running, self.anchor_t, self.anchor_n = True, time.monotonic(), len(self.episode)
            self.log("clock_start", control_steps=len(self.episode), episode=self.resets + 1)

    def _stop_clock(self, why: str) -> None:
        if self.running:
            self.running = False
            self.log("clock_stop", why=why, control_steps=len(self.episode), max_lag_s=round(self.max_lag, 4))
        self.plan.clear()

    def _end(self, reason: str) -> None:
        super()._end(reason)
        self._stop_clock(reason)                     # pending watches are completed by whoever ended it, after this

    def due_in(self, now: float) -> float | None:
        """Seconds until the next control step is due (<= 0: due now); None while the clock is stopped."""
        if not self.running or self.done or self.stopping:
            return None
        return self.anchor_t + (len(self.episode) - self.anchor_n) * self.wall_dt - now

    def tick(self) -> None:
        """One control step of the clock: the plan's row for it, or the held target."""
        now = time.monotonic()
        lag = -(self.due_in(now) or 0.0)
        if lag > MAX_LAG_S:                          # far behind: re-anchor rather than rush the robot through the debt
            self.stalls += 1
            self.log("stall", behind_s=round(lag, 3), control_steps=len(self.episode))
            self.anchor_t, self.anchor_n, lag = now, len(self.episode), 0.0
        self.lag, self.max_lag = max(lag, 0.0), max(self.max_lag, lag)
        if self.plan:
            typ, row, src = self.plan.popleft()
        else:
            (typ, row), src = self.sim.hold(), -1
            self.held_steps += 1
        before = self.journal_rows
        self._ticks.append((time.time(), float(src)))
        try:
            self._step(typ, row)
        except Exception as exc:  # noqa: BLE001 -- it ran and failed: the episode ends, as on hardware
            traceback.print_exc()
            if self.journal_rows == before:
                self._ticks.pop()
            self.log("error", path="clock", error=repr(exc)[:500])
            self._end("error")
            self._release_watches()
            return
        for w in list(self.watches):
            w.rec.step()
            if self.done or len(self.episode) >= w.end:
                self._complete_watch(w)
        if not self.done and len(self.episode) % self.ckpt_every == 0:
            self._checkpoint("tick")

    # ------------------------------------------------------------------ requests (simulator thread)
    def dispatch(self, job: _Job) -> None:
        """Serve one queued request; a watch finishes later, from tick()."""
        self.max_queue_wait = max(self.max_queue_wait, time.monotonic() - job.queued)
        try:
            self.first_request()
            path = urlparse(job.path).path
            if job.method == "GET" and path in ("/spec", "/status"):
                return job.finish("raw", *self._reply_json(200, self.spec if path == "/spec" else self.status()))
            routes = {"/submit": self._rt_submit, "/observe": self._rt_observe}
            if self.reset_budget:
                routes["/reset"] = self._rt_reset
            if job.method != "POST" or path not in routes:
                return job.finish("raw", *self._reply_json(404, {"error": "no such endpoint"}))
            if (len(job.body) if job.content_length is None else job.content_length) > MAX_BODY:
                return job.finish("raw", *self._reply_json(413, {"error": f"request body over {MAX_BODY} bytes"}))
            try:
                meta, parts = self._decode(job.body)
            except Exception as exc:  # noqa: BLE001 -- any malformed body is the caller's error
                return job.finish("raw", *self._reply_json(400, {"error": f"malformed body: {exc}"[:300]}))
            try:
                routes[path](meta, parts, job)
            except Refused as exc:                   # 400 (bad_request), 409: nothing changed
                job.finish("raw", *self._reply_json(exc.code, exc.body))
            except Exception as exc:  # noqa: BLE001 -- it ran and failed: the episode ends, as on hardware
                traceback.print_exc()
                self.log("error", path=path, error=repr(exc)[:500])
                self._end("error")
                self._release_watches()
                if not job.done.is_set():
                    job.finish("raw", *self._reply_json(500, {"error": "simulator error", "detail": repr(exc)[:200]}))
        except Exception as exc:  # noqa: BLE001 -- never leave an HTTP thread waiting forever
            traceback.print_exc()
            if not job.done.is_set():
                job.finish("raw", *self._reply_json(500, {"error": "service error", "detail": repr(exc)[:200]}))

    def _view_rt(self, meta: dict, default_video: str) -> tuple[list[str], int, str, bool]:
        """2.1's _view, plus cameras = [] for no images."""
        none = isinstance(meta.get("cameras"), list) and not meta["cameras"]
        cams, fps, video, depth = self._view(meta, default_video)
        return ([], fps, "none", False) if none else (cams, fps, video, depth)

    def _planned(self, step: int, nxt: int, typ: str) -> np.ndarray:
        """The target in force at control step `step` (>= nxt - 1) as things stand: the plan's row for it, else the
        plan's last row (held), else -- nothing planned, or a step already run -- the current command."""
        i = step - nxt
        if i < 0 or not self.plan:
            return np.asarray(self.sim.command(typ), dtype=np.float64)
        return np.asarray(self.plan[min(i, len(self.plan) - 1)][1], dtype=np.float64)

    def _rt_submit(self, meta: dict, parts: dict, job: _Job) -> None:
        if self.done or self.stopping:
            raise self._conflict()
        nxt = len(self.episode)
        with bad_request():
            typ = meta.get("type")
            if not isinstance(typ, str) or typ not in self.types:
                raise ValueError(f"type must be one of {sorted(self.types)}")
            try:
                A = np.asarray(parts["actions"]["data"] if "actions" in parts else meta.get("actions"),
                               dtype=np.float64)
            except (TypeError, ValueError, KeyError):
                raise ValueError("send the actions as an RCB1 array part `actions` or a JSON list of rows") from None
            dim = int(self.types[typ]["dim"])
            if A.ndim != 2 or A.shape[0] < 1 or A.shape[1] != dim:
                raise ValueError(f"{typ} actions must be (T, {dim}) with T >= 1, got {list(A.shape)}")
            if not np.all(np.isfinite(A)):
                raise ValueError("actions contain NaN or inf")
            cdt = self.sim.control_dt
            try:
                dt = cdt if meta.get("dt") is None else float(meta["dt"])
            except (TypeError, ValueError):
                raise ValueError("dt must be a number of seconds") from None
            k = round(dt / cdt) if np.isfinite(dt / cdt) else 0
            if k < 1 or abs(k * cdt - dt) > 1e-9:
                raise ValueError(f"dt must be a positive whole multiple of control_dt = {cdt} s (never rounded)")
            if k > 1 and not self.sim.interpolable(typ):
                raise ValueError(f"{typ}: one row is one control step, so dt must be control_dt = {cdt} s")
            if len(A) * k * cdt > self.max_chunk_s + 1e-9:
                raise ValueError(f"the chunk covers {len(A) * k * cdt:g} s: "
                                 f"more than max_chunk_s = {self.max_chunk_s:g}")
            interp = meta.get("interpolate", "linear")
            if interp not in ("linear", "hold"):
                raise ValueError("interpolate must be linear or hold")
            at = meta.get("at")
            if at is not None:
                if isinstance(at, bool) or not isinstance(at, (int, float)) or at != int(at) or at < 0:
                    raise ValueError("at must be a control step of this episode (an integer >= 0), "
                                     "or null for the next one")
                at = int(at)
                if at - nxt > self.max_ahead:
                    raise ValueError(f"at = {at} is more than max_ahead_steps = {self.max_ahead} control steps ahead "
                                     f"of the next one ({nxt})")
            at = nxt if at is None else at
            cams, fps, video, depth = self._view_rt(meta, "none")
        rows, clipped = self.sim.clip(typ, A)
        prev = self._planned(at - 1, nxt, typ)     # linear starts from the target in force just before `at`
        steps = []
        for row in rows:
            for j in range(1, k + 1):
                steps.append(row if interp == "hold" else prev + (row - prev) * (j / k))
            prev = row
        late = max(0, nxt - at)
        keep = at - nxt if at > nxt else 0
        self.calls += 1
        self.rows += len(A)
        head = list(self.plan)[:keep]
        if len(head) < keep:                         # a gap before `at`: the target in force then is held through it
            fill = self._planned(at - 1, nxt, typ)
            head += [(typ, fill, -1)] * (keep - len(head))
        self.plan = collections.deque(head + [(typ, s, self.calls) for s in steps[late:]])
        self.late_steps += min(late, len(steps))
        self._start_clock()
        rec = Recorder(self.sim, cams, fps, depth, "none")
        rec.start()
        rec.finish()
        out = {**self.meta(), "chunk_id": self.calls, "type": typ, "n_rows": int(len(A)), "dt": dt,
               "interpolate": interp, "at": at, "start_step": max(at, nxt), "late_steps": late,
               "plan_end_step": nxt + len(self.plan), "clipped": clipped[:200], "n_clipped": len(clipped), "ok": True}
        self._save_call({**out, "note": str(meta.get("note") or "")[:200]}, A)
        job.finish("rec", out, rec)

    def _rt_observe(self, meta: dict, parts: dict, job: _Job) -> None:
        with bad_request():
            try:
                seconds = float(meta.get("seconds") or 0.0)
            except (TypeError, ValueError):
                raise ValueError("seconds must be a number") from None
            if not 0.0 <= seconds <= self.max_watch_s:
                raise ValueError(f"seconds must be in [0, {self.max_watch_s:g}]")
            cams, fps, video, depth = self._view_rt(meta, "frames")
            n = int(round(seconds / self.sim.control_dt)) if not (self.done or self.stopping) else 0
            rec = Recorder(self.sim, cams, fps, depth, video if n or video != "mp4" else "frames")   # no time: no video
            self._frame_budget(rec, n)
        self.calls += 1
        rec.start()
        if not n:
            rec.finish()
            out = {**self.meta(), "obs_id": self.calls, "seconds": 0.0, "control_steps_watch": 0, "ok": True}
            self._save_call(out, None)
            return job.finish("rec", out, rec)
        self._start_clock()
        self.watches.append(_Watch(job, rec, len(self.episode), n, cams, self.calls))

    def _complete_watch(self, w: _Watch) -> None:
        self.watches.remove(w)
        w.rec.finish()
        ran = max(0, min(len(self.episode), w.end) - w.start)
        out = {**self.meta(), "obs_id": w.obs_id, "seconds": round(ran * self.sim.control_dt, 4),
               "control_steps_watch": ran, "ok": True}
        self._save_call(out, None)
        w.job.finish("rec", out, w.rec)

    def _release_watches(self) -> None:
        for w in list(self.watches):
            self._complete_watch(w)

    def _rt_reset(self, meta: dict, parts: dict, job: _Job) -> None:
        self._release_watches()
        out, prts = self._reset(meta, parts)         # 2.1's reset: checks, abandons the episode, a new one (paused)
        self._stop_clock("reset")
        job.finish("rcb1", {**out, **self._realtime_counters()}, prts)

    # ------------------------------------------------------------------ the loop (simulator thread) and HTTP
    def poll(self) -> None:
        """After SIGUSR1: end the episode, answer the pending watches, finalize (Service.poll, plus the watches)."""
        if self.stopping and not self.finalized:
            if not self.done:
                self._end("timeout")
            self._release_watches()
            self._finalize()

    def loop(self, until: threading.Event | None = None) -> None:
        """The simulator thread: control steps when due, requests in between, the wrap-up after SIGUSR1."""
        while until is None or not until.is_set():
            self.poll()
            wait = self.due_in(time.monotonic())
            if wait is not None and wait <= 0:
                self.tick()
                # Behind the clock (a simulator step slower than control_dt, or a busy host), a step is due again at
                # once: serve one waiting request between steps, or no request would be served until the next stall.
                try:
                    job = self.q.get_nowait()
                except queue.Empty:
                    continue
            else:
                try:
                    job = self.q.get(timeout=0.25 if wait is None else min(wait, 0.25))
                except queue.Empty:
                    continue
            self.dispatch(job)

    def submit_job(self, job: _Job) -> tuple[int, str, bytes]:
        """From an HTTP thread: queue the request, wait for the simulator thread, encode the answer here."""
        self.q.put(job)
        job.done.wait()
        kind, *rest = job.reply
        if kind == "raw":
            return tuple(rest)
        meta, payload = rest                         # a Recorder's parts are encoded here, off the simulator's thread
        return self._reply_rcb1(meta, payload.parts() if kind == "rec" else payload)

    def http_server(self, address: tuple[str, int]) -> ThreadingHTTPServer:
        svc = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 120

            def log_message(self, *a):
                pass

            def _send(self, code: int, ctype: str, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send(*svc.submit_job(_Job("GET", self.path, b"")))

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return self._send(*svc._reply_json(400, {"error": "bad Content-Length"}))
                if n > MAX_BODY:                     # refused unread: drop the connection with it
                    self.close_connection = True
                    return self._send(*svc.submit_job(_Job("POST", self.path, b"", content_length=n)))
                self._send(*svc.submit_job(_Job("POST", self.path, self.rfile.read(n))))

        class Server(ThreadingHTTPServer):
            daemon_threads = True

        return Server(address, Handler)

    def serve(self, port: int = 8000) -> None:
        import signal
        signal.signal(signal.SIGUSR1, self.on_sigusr1)
        srv = self.bind(port)
        threading.Thread(target=srv.serve_forever, name="http", daemon=True).start()
        print(f"{rcb_service.PROTOCOL} sim service (realtime, slowdown {self.slowdown:g}) ready on :{port}", flush=True)
        self.loop()


def main(build, port: int = 8000) -> None:
    """rcb_service.main -- the start count, back-off, startup watchdog, resume -- with this service in place of
    Service (RCB_SLOWDOWN: 1 = real time), and eai-standard/2.3 in everything it logs and writes."""
    rcb_service.Service = RealtimeService
    rcb_service.PROTOCOL = PROTOCOL
    rcb_service.main(build, port)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import server  # noqa: E402 -- the HumanoidBench adapter; picks the GL backend and restores the reward on import

    main(server.build)
