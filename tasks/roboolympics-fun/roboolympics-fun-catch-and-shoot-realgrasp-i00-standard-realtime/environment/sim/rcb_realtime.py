"""eai-standard/2.3, the standard-realtime mode's protocol: the sim service of HumanoidBench's `-standard-realtime` tasks
(docs/protocol/README.md §4b, docs/protocol/standard_mode.md "Standard-realtime mode"; docs/benchmarks/humanoidbench.md). Entry
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
- A simulator may have several action types (RoboOlympics: `stroke`, `toss`, `mallet`, `stop`, ...), and a plan may
  mix them. A row is only ever combined with a row of its own type: a chunk interpolates from the target of ITS type
  in force before `at` (the simulator's current command of that type when the plan holds another type there), and a
  gap before `at` is filled with held steps (the simulator's hold row, as when the plan has run out) unless the type
  is an interpolable target that is itself in force there (then that target, held). A command that is not a target
  (not interpolable: one row is one control step) is never interpolated and never repeated into a gap.
- /observe with seconds = 0 answers at once; with seconds > 0 it watches the running episode that long (robot time)
  and returns what the cameras saw. It never changes the plan.
- `cameras = []` asks for no images at all (in 2.1 an empty list means every camera): a controller's proprio-only call.

Grading is 2.1's: the verdict is the live episode's (docs/protocol/README.md H.4; owner, 2026-10-17, board 0151), judged by
this service, nothing replayed. Every executed control step's sim row is journaled (trajectory_live.f64) and the graded
episode's rows are saved as the trajectory: the rows the simulator applied, not what was submitted, so the trajectory
reproduces the live run however the timing went (the video is rendered from it). Evidence added (never visible to the agent):
ticks.f64 (per journal row: wall time, and the call whose chunk gave the row, -1 for a held one), calls.jsonl (one line
per call; no calls/NNNNNN/ directories: a controller calls 50 times a second) and submitted.f64 (every row as sent:
call id, then the row). final.json adds realtime, slowdown, held_steps, late_steps, max_queue_wait_s (the longest a
request waited for the simulator thread) and how well the clock was kept: clock_s (wall seconds the clock ran, over the
whole trial), max_lag_s (the furthest a control step ran behind its time), stalls, stalled_s (the wall time the stalls
dropped: the robot stood still that long while the clock should have run) and stalled_share = stalled_s / clock_s; and
what the requests cost: requests_refused (answered 4xx), request_mb (request bodies read) and request_busy_s (simulator
thread time spent on requests). The graders copy the clock's figures into reward.json; none of them decides a verdict.

Threads: the simulator and its GL context belong to the main thread, which runs the clock and, between control steps,
the part of a request that needs the simulator. Everything else about a request happens on its HTTP thread, off the
clock: reading the body, decoding it, every check that does not depend on the episode's state, and encoding the answer.
A request that is refused there (404, 413, a malformed body, a wrong type / shape / dt / camera ...) never reaches the
simulator thread. What a request can cost the clock is bounded:
- JSON text is parsed under this process's interpreter lock (which the simulator thread needs too) only up to
  INLINE_JSON bytes; a body with more of it is parsed by a child process, so a flood of large bodies, refused or not,
  takes no time from the clock. Bodies over LANE_BODY bytes are read, decoded and checked one at a time (one of them
  in memory at a time) and paced (LANE_PACE); while serving, the interpreter switches threads every SWITCH_INTERVAL_S.
- A control step that is due runs before any waiting request. Behind the clock (a long render, a simulator step slower
  than control_dt, a busy host) the missed steps run back to back, skipping none; a waiting request is then served only
  once the clock has caught up, or -- so that a simulator that cannot keep up at all still answers -- after
  BEHIND_PACE times the time the last request of its kind took. Requests therefore queue behind each other, not into
  the clock: an /observe may take longer to answer, the robot's time does not slow down. A request that renders and
  alone takes more than MAX_LAG_S (a stall by itself: CPU rendering) keeps the next rendering request waiting
  BEHIND_PACE times as long, clock on time or not; requests without images (cameras = [], /status) are not held
  back by it, so a controller's loop goes on. Requests can so take at most 1 / (1 + BEHIND_PACE) of the clock's time.
- Cameras are rendered (and the proprioception read) at most once per control step, however many requests and watches
  ask for them: all of them get that step's frames. The pending watches together hold at most max_frames_per_call
  images; a watch that would exceed it is refused (429) until one completes.
More than MAX_LAG_S behind, the service drops the debt instead of fast-forwarding the robot (a stall: counted, and its
seconds added to stalled_s).

A crash resumes the same episode from its last checkpoint (one per second of robot time while the clock runs), paused.
Whose failure it is (owner, 2026-10-17; docs/protocol/standard_mode.md Part 3): once the agent's first command has run (the first
control step that runs a row the agent sent: the "first_command" event), the robot is executing the agent's commands, as inside a
call in 2.1.
- A simulator error raised by a control step after the first command ends the episode "error": the agent's 0
  (sim_error, no infra_error). Before the first command, a request's own failure (a render) and a reset whose scene
  does not rebuild are infrastructure (infra_error = 1).
- A simulator crash -- a process death with a fatal signal's record in crash.log (SIGSEGV, SIGBUS, SIGFPE, SIGILL,
  SIGABRT; rcb_service.deaths) whose crashing thread was inside a control step (_step) -- after the first command is the
  agent's: past RCB_MAX_RESUMES restarts that were all such crashes, the trial ends `sim_crashed_on_call` (the agent's
  0). A kill (SIGKILL, SIGTERM, the OOM killer: no record), a crash outside a control step (building the scene,
  resuming, resetting, rendering, finalizing; a GPU or driver fault there), a crash before the first command and a
  failed resume are infrastructure: `sim_crashed`, `resume_failed` (infra_error).
"""
from __future__ import annotations

import collections
import json
import os
import queue
import struct
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import numpy as np

import rcb1
import rcb_service
from rcb_service import MAX_BODY, Recorder, Refused, Service, bad_request

PROTOCOL = "eai-standard/2.3"   # the standard-realtime mode's protocol (PROTOCOL §4b); rcb_service.py itself serves 2.1
MAX_LAG_S = 0.5          # behind the clock by more than this: drop the debt (a stall) instead of catching up
CHECKPOINT_S = 1.0       # robot time between checkpoints while the clock runs (the most a crash loses)
HELD = (None, None, -1)  # a plan entry for a step with nothing planned: the simulator's hold row, taken at that step
# What a request may cost the clock (module docstring, "Threads"):
INLINE_JSON = 1 << 20    # bytes of JSON text parsed in this process; more is parsed by a child process (off the lock)
LANE_BODY = 64 << 10     # bodies above this are decoded and checked one at a time ...
LANE_PACE = 3.0          # ... and the next one waits this many times the CPU time the last one took
BEHIND_PACE = 4.0        # behind the clock: the next request waits this many times the time the last one took
CHILD_TIMEOUT_S = 60.0   # the child process's time for one body
CHILD_MEM = 1 << 30      # ... and its memory above what its interpreter needs (a body that needs more is refused)
SWITCH_INTERVAL_S = 0.001   # the interpreter's thread switch interval while serving (default 0.005): HTTP threads
                            # hand the lock back to the simulator thread within a millisecond
FIELDS = ("type", "dt", "interpolate", "at", "cameras", "video_fps", "video", "include_depth", "note", "seconds")

# The child process that parses a body with more than INLINE_JSON bytes of JSON text (argv: the most elements a valid
# `actions` can have, INLINE_JSON, CHILD_MEM; stdin: the body). It answers with the fields the service reads and the
# actions as float64 -- or only their shape when no action type takes that many -- or the error a malformed body gets.
_CHILD = r"""
import json, struct, sys
FIELDS = %r
def conv(np, obj, lim):
    try:
        a = np.asarray(obj, dtype=np.float64)
    except (TypeError, ValueError):
        return {"kind": "bad"}, b""
    if a.size > lim:
        return {"kind": "shape", "shape": list(a.shape)}, b""
    return {"kind": "array", "dtype": "<f8", "shape": list(a.shape)}, np.ascontiguousarray(a).astype("<f8").tobytes()
def main():
    lim, inline, mem = (int(x) for x in sys.argv[1:4])
    import numpy as np
    try:
        import resource
        with open("/proc/self/statm") as f:
            vm = int(f.read().split()[0]) * resource.getpagesize()
        resource.setrlimit(resource.RLIMIT_AS, (vm + mem, vm + mem))
    except Exception:
        pass
    blob = b""
    try:
        buf = sys.stdin.buffer.read()
        part = None
        if buf[:4] == b"RCB1":
            n = struct.unpack("<I", buf[4:8])[0]
            header = json.loads(buf[8:8 + n].decode())
            off = 8 + n
            meta = header.get("meta", {})
            for p in header["parts"]:
                if p["name"] == "actions":
                    part = (p, off)
                off += p["len"]
        else:
            meta = json.loads(buf or b"{}")
        if not isinstance(meta, dict):
            raise ValueError("the body must be a JSON object or an RCB1 frame")
        desc = {"kind": "none"}
        if part is not None:
            p, off = part
            raw = buf[off:off + p["len"]]
            if p["kind"] == "array":
                a = np.frombuffer(raw, dtype=np.dtype(p["dtype"])).reshape(p["shape"])
                if a.size > lim:
                    desc = {"kind": "shape", "shape": list(a.shape)}
                else:
                    desc, blob = {"kind": "array", "dtype": p["dtype"], "shape": list(a.shape)}, raw
            elif p["kind"] == "json":
                desc, blob = conv(np, json.loads(raw.decode()), lim)
            else:
                desc = {"kind": "bad"}
        elif "actions" in meta:
            desc, blob = conv(np, meta["actions"], lim)
        small = {k: meta[k] for k in FIELDS if k in meta}
        if "note" in small:
            small["note"] = str(small["note"] or "")[:200]
        head = json.dumps({"meta": small, "actions": desc}).encode()
        if len(head) > inline:
            raise ValueError("the request's fields other than the actions take more than %%d bytes" %% inline)
    except MemoryError:
        head, blob = json.dumps({"error": "the body takes too much memory to parse"}).encode(), b""
    except Exception as exc:
        head, blob = json.dumps({"error": str(exc)[:300] or type(exc).__name__}).encode(), b""
    sys.stdout.buffer.write(struct.pack("<I", len(head)) + head + blob)
main()
""" % (FIELDS,)


class _Job:
    """One HTTP request, handed from its HTTP thread to the simulator's thread and back."""

    def __init__(self, method: str, path: str, body: bytes = b"", content_length: int | None = None, req: tuple = ()):
        self.method, self.path, self.body, self.content_length = method, path, body, content_length
        self.req = req                   # (route, checked request) from RealtimeService.front(); () = not looked at yet
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


class _Views:
    """The simulator as the Recorders see it: the cameras are rendered, and the proprioception read, at most once per
    control step, however many requests and watches ask (each gets that step's arrays; nobody writes into them). The
    state they show changes only with a control step or a reset, which is what the cache is keyed by."""

    def __init__(self, svc: "RealtimeService"):
        self._svc, self._sim = svc, svc.sim
        self._key, self._rgb, self._dep, self._prop = None, {}, {}, None

    def __getattr__(self, name):
        return getattr(self._sim, name)

    def _fresh(self) -> None:
        key = (self._svc.journal_rows, self._svc.resets)
        if key != self._key:
            self._key, self._rgb, self._dep, self._prop = key, {}, {}, None

    def images(self, cameras, depth):
        self._fresh()
        want = depth and set(self._sim.depth_cameras)
        need = [c for c in cameras if c not in self._rgb or (want and c in want and c not in self._dep)]
        if need:
            rgb, dep = self._sim.images(list(dict.fromkeys(need)), depth)
            self._rgb.update(rgb)
            self._dep.update(dep)
        return {c: self._rgb[c] for c in cameras}, ({c: self._dep[c] for c in cameras if c in self._dep} if depth else {})

    def proprio(self):
        self._fresh()
        if self._prop is None:
            self._prop = self._sim.proprio()
        return self._prop


class RealtimeService(Service):
    """rcb_service.Service with the realtime clock (module docstring)."""

    def __init__(self, sim, *, slowdown: float | None = None, **kw):
        self.slowdown = float(os.environ.get("RCB_SLOWDOWN") or 1.0) if slowdown is None else float(slowdown)
        if not self.slowdown > 0:
            raise ValueError("RCB_SLOWDOWN must be > 0")
        self.wall_dt = sim.control_dt * self.slowdown
        self.max_ahead = int(round(float(kw.get("max_chunk_s", 10.0)) / sim.control_dt))   # how far ahead `at` may be
        self.plan: collections.deque = collections.deque()   # (type, row, call id) per coming control step, or HELD
        self.running = False
        self.anchor_t = self.anchor_n = 0                  # the clock: control step anchor_n was due at anchor_t
        self.watches: list[_Watch] = []
        self.q: queue.Queue = queue.Queue()
        self.max_lag = self.lag = 0.0
        self.stalls = self.held_steps = self.late_steps = 0
        self.stalled_s = 0.0                               # wall time the stalls dropped
        self.clock_s = 0.0                                 # wall time the clock ran, up to its last start
        self._clock_t0 = 0.0                               # ... and when that was
        self.max_queue_wait = 0.0
        self.requests_refused, self.request_bytes, self.request_busy_s = 0, 0, 0.0
        self._ticks: list[tuple[float, float]] = []        # (wall time, call id) per journal row not yet on disk
        self.commanded = False                             # a row the agent planned has run (the first command)
        super().__init__(sim, **kw)
        self.ticks_path = os.path.join(self.data, "ticks.f64")
        self.ckpt_every = max(1, int(round(CHECKPOINT_S / sim.control_dt)))
        # the HTTP threads' side (front()): what they need of the simulator is read once, here
        self.views = _Views(self)
        self._interp = {t: bool(sim.interpolable(t)) for t in self.types}
        self._max_rows = int((self.max_chunk_s + 1e-9) / sim.control_dt)      # of any chunk that can be valid
        self._max_elems = max([self._max_rows * int(v["dim"]) for v in self.types.values()] or [0])
        self._spec_reply: tuple | None = None
        self._t_seen: float | None = None                  # the first request's time, as its HTTP thread saw it
        self._stat_lock, self._lane, self._child_lock = threading.Lock(), threading.Lock(), threading.Lock()
        self._lane_free_at = 0.0
        # the simulator thread's side (loop()): requests by kind -- True: it renders cameras, False: it does not
        self._gate = {True: 0.0, False: 0.0}               # behind the clock, none of the kind is served before this
        self._render_gate = 0.0                            # ... and no rendering request before this, behind or not
        self._held: collections.deque = collections.deque()   # requests taken from the queue before their time

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

    def _clock_seconds(self) -> float:
        """Wall seconds the clock has run, over the whole trial."""
        return self.clock_s + (time.monotonic() - self._clock_t0 if self.running else 0.0)

    def _timing(self) -> dict:
        """The counters a checkpoint keeps (and _resume restores)."""
        return {"max_lag_s": self.max_lag, "stalls": self.stalls, "stalled_s": self.stalled_s,
                "clock_s": self._clock_seconds(), "held_steps": self.held_steps, "late_steps": self.late_steps,
                "max_queue_wait_s": self.max_queue_wait, "requests_refused": self.requests_refused,
                "request_bytes": self.request_bytes, "request_busy_s": self.request_busy_s}

    def _timing_record(self) -> dict:
        clock = self._clock_seconds()
        return {"protocol": PROTOCOL, "realtime": 1, "slowdown": self.slowdown, "max_lag_s": round(self.max_lag, 4),
                "stalls": self.stalls, "stalled_s": round(self.stalled_s, 3), "clock_s": round(clock, 3),
                "stalled_share": round(min(1.0, self.stalled_s / clock), 4) if clock > 0 else 0.0,
                "held_steps": self.held_steps, "late_steps": self.late_steps,
                "max_queue_wait_s": round(self.max_queue_wait, 4), "requests_refused": self.requests_refused,
                "request_mb": round(self.request_bytes / 1e6, 3), "request_busy_s": round(self.request_busy_s, 3)}

    def _write_final(self) -> None:
        self.verdict.update(self._timing_record())   # final.json merges the verdict; none of these keys is a verdict's
        super()._write_final()                       # infra_error for an "error" only when error_infra (rcb_service)

    def _checkpoint(self, ev: str, **kw) -> None:
        if self._ticks:                              # the tick log first: a crash in between leaves it too long
            with open(self.ticks_path, "ab") as f:
                f.write(np.asarray(self._ticks, dtype=np.float64).tobytes())
            self._ticks = []
        super()._checkpoint(ev, **kw, timing=self._timing())

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

    def _resume(self, ev: list[dict]) -> None:
        """Service._resume, with the realtime counters as of the checkpoint the episode resumes from (what the lost
        steps had added goes with them): final.json's stalls, stalled_s, clock_s, held_steps, late_steps, max_lag_s,
        max_queue_wait_s and the request counters cover the whole trial, not only the part after the last restart."""
        cp = next((e for e in reversed(ev) if "state_sha" in e and "journal_rows" in e), {})
        t = cp.get("timing") if isinstance(cp.get("timing"), dict) else {}
        self.stalls, self.held_steps, self.late_steps, self.requests_refused, self.request_bytes = (
            int(t.get(k) or 0) for k in ("stalls", "held_steps", "late_steps", "requests_refused", "request_bytes"))
        self.max_lag, self.max_queue_wait, self.stalled_s, self.clock_s, self.request_busy_s = (
            float(t.get(k) or 0.0) for k in ("max_lag_s", "max_queue_wait_s", "stalled_s", "clock_s", "request_busy_s"))
        self.commanded = any(e["ev"] == "first_command" for e in ev)
        self.error_infra = bool(cp.get("error_infra", True))   # (before 2026-10-17 every "error" was infrastructure)
        super()._resume(ev)

    def _agent_crashes(self, ev: list[dict], died: list[dict], in_calls: int) -> int:
        """The deaths since the episode began that were simulator crashes inside a control step (a fatal signal's
        record whose crashing thread is in _step: not building the scene, resuming, resetting, rendering, finalizing)
        after the agent's first command: the robot was running its commands, as inside a call in 2.1 (owner,
        2026-10-17). A GPU or driver fault outside the step stays infrastructure too."""
        first = [e["ts"] for e in ev if e["ev"] == "first_command"]
        return sum(1 for d in died if d["fatal_signal"] and d["in_step"] and first and first[0] < d["restart_ts"])

    def _start_clock(self) -> None:
        if not self.running and not self.done and not self.stopping:
            self.running, self.anchor_t, self.anchor_n = True, time.monotonic(), len(self.episode)
            self._clock_t0 = self.anchor_t
            self.log("clock_start", control_steps=len(self.episode), episode=self.resets + 1)

    def _stop_clock(self, why: str) -> None:
        if self.running:
            self.clock_s = self._clock_seconds()
            self.running = False
            self.log("clock_stop", why=why, control_steps=len(self.episode), max_lag_s=round(self.max_lag, 4),
                     stalls=self.stalls, stalled_s=round(self.stalled_s, 3), clock_s=round(self.clock_s, 3))
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
        self.max_lag = max(self.max_lag, lag)
        if lag > MAX_LAG_S:                          # far behind: re-anchor rather than rush the robot through the debt
            self.stalls += 1
            self.stalled_s += lag                    # the robot stood still this long while its clock should have run
            self.log("stall", behind_s=round(lag, 3), control_steps=len(self.episode))
            self.anchor_t, self.anchor_n, lag = now, len(self.episode), 0.0
        self.lag = max(lag, 0.0)
        typ, row, src = self.plan.popleft() if self.plan else HELD
        if typ is None:                              # nothing planned for this step (the plan ran out, or a gap in it)
            typ, row = self.sim.hold()
            self.held_steps += 1
        elif src >= 0 and not self.commanded:        # the first control step that runs a row the agent sent: from
            self.commanded = True                    # here the robot runs its commands (logged first: a crash in this
                                                     # step is after it; a gap's held target, call -1, is not one)
            self.log("first_command", control_steps=len(self.episode), journal_rows=self.journal_rows, call=int(src))
        before = self.journal_rows
        self._ticks.append((time.time(), float(src)))
        try:
            self._step(typ, row)
        except Exception as exc:  # noqa: BLE001 -- it ran and failed: the episode ends, as on hardware
            traceback.print_exc()
            if self.journal_rows == before:
                self._ticks.pop()
            self.log("error", path="clock", error=repr(exc)[:500], agent=self.commanded)
            self.error_infra = not self.commanded    # after the first command: the agent's commands raised it
            self._end("error")
            self._release_watches()
            return
        for w in list(self.watches):
            w.rec.step()
            if self.done or len(self.episode) >= w.end:
                self._complete_watch(w)
        if not self.done and len(self.episode) % self.ckpt_every == 0:
            self._checkpoint("tick")

    # ------------------------------------------------------------------ requests, off the clock (HTTP threads)
    def first_request(self) -> None:
        if self.t0 is None:
            self.t0 = self._t_seen or time.time()    # when its HTTP thread saw it (front), logged by this thread
            self.log("first_request", t0=self.t0)

    def _count(self, refused: int = 0, read: int = 0) -> None:
        with self._stat_lock:
            self.requests_refused += refused
            self.request_bytes += read

    def _refusal(self, exc: Refused) -> tuple:
        self._count(refused=1)
        return ("reply", *self._reply_json(exc.code, exc.body))

    def front(self, method: str, path: str, n: int = 0, read=None) -> tuple:
        """Everything about a request that needs no simulator, on the caller's thread (an HTTP thread): the route, the
        body (`read(n)`, called only for a body that will be decoded), its decoding, and every check that does not
        depend on the episode's state. Returns ("reply", status, content type, body) for a request that ends here --
        every refusal but the ones only the episode's state can decide (409, an `at` too far ahead, too many frames) --
        or (route, checked request) for the simulator thread."""
        if self._t_seen is None:
            with self._stat_lock:
                self._t_seen = self._t_seen or time.time()
        path = urlparse(path).path
        if method == "GET" and path == "/spec":      # fixed for the service's life
            if self._spec_reply is None:
                self._spec_reply = self._reply_json(200, self.spec)
            return ("reply", *self._spec_reply)
        if method == "GET" and path == "/status":
            return ("/status", None)
        if method != "POST" or path not in ("/submit", "/observe") + (("/reset",) if self.reset_budget else ()):
            return self._refusal(Refused(404, {"error": "no such endpoint"}))
        if n < 0:
            return self._refusal(Refused(400, {"error": "bad Content-Length"}))
        if n > MAX_BODY:
            return self._refusal(Refused(413, {"error": f"request body over {MAX_BODY} bytes"}))
        try:
            if n <= LANE_BODY:
                body = read(n) if n else b""
                self._count(read=len(body))
                return (path, self._prepare(path, body))
            with self._lane:                         # large bodies: one at a time (also in memory: the next one is
                wait = self._lane_free_at - time.monotonic()   # read when this one is done), paced by what the last took
                if wait > 0:
                    time.sleep(wait)
                body = read(n)
                self._count(read=len(body))
                t = time.thread_time()
                try:
                    return (path, self._prepare(path, body))
                finally:
                    self._lane_free_at = time.monotonic() + LANE_PACE * (time.thread_time() - t)
        except Refused as exc:
            # After a body that cannot be read at all, what the simulator thread answers before it looks at a
            # request's fields (409) comes first here too.
            return self._refusal(exc if getattr(exc, "malformed", False) else self._state_refusal(path) or exc)

    def _state_refusal(self, path: str) -> Refused | None:
        """The refusal a request to `path` gets whatever it says, as things stand (read without the simulator thread:
        a request that races the episode's end may get either answer, as it always could)."""
        if path == "/submit" and (self.done or self.stopping):
            return self._conflict()
        if path == "/reset":
            try:
                self._reset_view({})
            except Refused as exc:
                return exc
        return None

    def _prepare(self, path: str, body: bytes):
        try:
            meta, actions = self._decode_rt(body)
        except Exception as exc:  # noqa: BLE001 -- any malformed body is the caller's error
            refused = Refused(400, {"error": f"malformed body: {exc}"[:300]})
            refused.malformed = True
            raise refused from None
        if path == "/submit":
            return self._check_submit(meta, actions)
        if path == "/observe":
            return self._check_observe(meta)
        with bad_request():                          # /reset: its view; the budget is the simulator thread's to check
            self._view(meta, "frames")
        return meta

    def _decode_rt(self, body: bytes) -> tuple[dict, object]:
        """Service._decode for this service: (meta, the actions as sent -- the RCB1 part `actions`, else meta's -- or
        None). Only the part the service reads is decoded. More than INLINE_JSON bytes of JSON text go to the child."""
        actions, part = None, None
        if body[:4] == rcb1.MAGIC:
            (n,) = struct.unpack("<I", body[4:8])
            if n > INLINE_JSON:
                return self._decode_child(body)
            header = json.loads(body[8:8 + n].decode())
            meta, off = header.get("meta", {}), 8 + n
            for p in header["parts"]:
                if p["name"] == "actions":
                    part = (p, off)
                off += p["len"]
        else:
            if len(body) > INLINE_JSON:
                return self._decode_child(body)
            meta = json.loads(body or b"{}")
        if not isinstance(meta, dict):
            raise ValueError("the body must be a JSON object or an RCB1 frame")
        if part is not None:
            p, off = part
            blob = body[off:off + p["len"]]
            if p["kind"] == "array":
                actions = np.frombuffer(blob, dtype=np.dtype(p["dtype"])).reshape(p["shape"])
            elif p["kind"] == "json":
                if len(blob) > INLINE_JSON:
                    return self._decode_child(body)
                actions = json.loads(blob.decode())
            else:
                actions = blob
        else:
            actions = meta.get("actions")
        return meta, actions

    def _decode_child(self, body: bytes) -> tuple[dict, object]:
        """_decode_rt by the child process (_CHILD): the same answer, without holding this process's interpreter lock
        for the time a large JSON text takes to parse. One at a time."""
        with self._child_lock:
            try:
                env = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
                out = subprocess.run([sys.executable, "-c", _CHILD, str(self._max_elems), str(INLINE_JSON),
                                      str(CHILD_MEM)], input=body, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=CHILD_TIMEOUT_S, env=env).stdout
                (n,) = struct.unpack("<I", out[:4])
                head, blob = json.loads(out[4:4 + n].decode()), out[4 + n:]
            except Exception as exc:  # noqa: BLE001 -- no child, no answer: refused; never parsed on the clock's lock
                raise ValueError(f"more than {INLINE_JSON} bytes of JSON text, which this service could not parse "
                                 f"({type(exc).__name__}): send the rows as an RCB1 array part") from None
        if "error" in head:
            raise ValueError(head["error"])
        d = head["actions"]
        if d["kind"] == "array":
            actions = np.frombuffer(blob, dtype=np.dtype(d["dtype"])).reshape(d["shape"])
        elif d["kind"] == "shape":                   # more elements than any action type takes: its shape is all that
            shape = tuple(int(x) for x in d["shape"])   # matters (it is refused for it), so none of them came back
            actions = np.lib.stride_tricks.as_strided(np.zeros(1), shape=shape, strides=(0,) * len(shape),
                                                      writeable=False)
        else:
            actions = None if d["kind"] == "none" else b"?"     # b"?": not numbers (refused as such)
        return head["meta"], actions

    def _check_submit(self, meta: dict, actions) -> dict:
        """/submit's checks that do not depend on the episode's state; the chunk, ready for the simulator thread."""
        with bad_request():
            typ = meta.get("type")
            if not isinstance(typ, str) or typ not in self.types:
                raise ValueError(f"type must be one of {sorted(self.types)}")
            dim = int(self.types[typ]["dim"])
            cdt = self.sim.control_dt

            def shape_ok(a) -> None:                 # before any pass over the rows: a refusal costs nothing
                if a.ndim != 2 or a.shape[0] < 1 or a.shape[1] != dim:
                    raise ValueError(f"{typ} actions must be (T, {dim}) with T >= 1, got {list(a.shape)}")
                if a.shape[0] > self._max_rows:
                    raise ValueError(f"the chunk covers {a.shape[0] * cdt:g} s: "
                                     f"more than max_chunk_s = {self.max_chunk_s:g}")

            if isinstance(actions, np.ndarray):
                shape_ok(actions)
            elif isinstance(actions, list) and len(actions) > self._max_rows:
                raise ValueError(f"the chunk covers {len(actions) * cdt:g} s: "
                                 f"more than max_chunk_s = {self.max_chunk_s:g}")
            try:
                A = np.asarray(actions, dtype=np.float64)
            except (TypeError, ValueError, KeyError):
                raise ValueError("send the actions as an RCB1 array part `actions` or a JSON list of rows") from None
            shape_ok(A)
            if not np.all(np.isfinite(A)):
                raise ValueError("actions contain NaN or inf")
            try:
                dt = cdt if meta.get("dt") is None else float(meta["dt"])
            except (TypeError, ValueError):
                raise ValueError("dt must be a number of seconds") from None
            k = round(dt / cdt) if np.isfinite(dt / cdt) else 0
            if k < 1 or abs(k * cdt - dt) > 1e-9:
                raise ValueError(f"dt must be a positive whole multiple of control_dt = {cdt} s (never rounded)")
            if k > 1 and not self._interp[typ]:
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
            return {"type": typ, "actions": A, "dt": dt, "k": k, "interpolate": interp, "at": at,
                    "view": self._view_rt(meta, "none"), "note": str(meta.get("note") or "")[:200]}

    def _check_observe(self, meta: dict) -> dict:
        with bad_request():
            try:
                seconds = float(meta.get("seconds") or 0.0)
            except (TypeError, ValueError):
                raise ValueError("seconds must be a number") from None
            if not 0.0 <= seconds <= self.max_watch_s:
                raise ValueError(f"seconds must be in [0, {self.max_watch_s:g}]")
            return {"seconds": seconds, "view": self._view_rt(meta, "frames")}

    # ------------------------------------------------------------------ requests (simulator thread)
    def dispatch(self, job: _Job) -> None:
        """Serve one queued request; a watch finishes later, from tick(). A job that front() has not seen (handed over
        whole: tests, tools) is taken through it here."""
        self.max_queue_wait = max(self.max_queue_wait, time.monotonic() - job.queued)
        try:
            if not job.req:
                n = len(job.body) if job.content_length is None else job.content_length
                job.req = self.front(job.method, job.path, n, lambda _n: job.body)
            self.first_request()
            route = job.req[0]
            if route == "reply":
                return job.finish("raw", *job.req[1:])
            if route == "/status":
                return job.finish("raw", *self._reply_json(200, self.status()))
            try:
                {"/submit": self._rt_submit, "/observe": self._rt_observe,
                 "/reset": self._rt_reset}[route](job.req[1], job)
            except Refused as exc:                   # 409, or a 400 only the episode's state decides: nothing changed
                self._count(refused=1)
                job.finish("raw", *self._reply_json(exc.code, exc.body))
            except Exception as exc:  # noqa: BLE001 -- it ran and failed: the episode ends, as on hardware
                traceback.print_exc()
                self.log("error", path=route, error=repr(exc)[:500])
                if not self.done:                    # a request's own work failed (a render, a reset's rebuild), not
                    self.error_infra = True          # a control step of the agent's commands: infrastructure
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

    def _in_force(self, step: int, nxt: int, typ: str) -> np.ndarray | None:
        """The `typ` row in force at control step `step` (>= nxt - 1) as things stand: the plan's row for it, else the
        plan's last row before it (held); with nothing planned up to there, or a step already run, the simulator's
        current command of that type. None when the row in force there is of ANOTHER action type: rows of different
        types have different layouts and are never combined, and what that row leaves in force for `typ` is not
        known before it runs."""
        for i in range(min(step - nxt, len(self.plan) - 1), -1, -1):
            t, row, _ = self.plan[i]
            if t is not None:                        # (a held step leaves in force what was before it)
                return np.asarray(row, dtype=np.float64) if t == typ else None
        return np.asarray(self.sim.command(typ), dtype=np.float64)

    def _rt_submit(self, req: dict, job: _Job) -> None:
        """A checked chunk (_check_submit) into the plan: what depends on the episode's state, and the planning."""
        if self.done or self.stopping:
            raise self._conflict()
        nxt = len(self.episode)
        typ, A, dt, k, interp, at = (req[x] for x in ("type", "actions", "dt", "k", "interpolate", "at"))
        cams, fps, video, depth = req["view"]
        if at is not None and at - nxt > self.max_ahead:
            raise Refused(400, {"error": f"at = {at} is more than max_ahead_steps = {self.max_ahead} control steps "
                                         f"ahead of the next one ({nxt})"})
        at = nxt if at is None else at
        late = max(0, nxt - at)
        keep = at - nxt if at > nxt else 0
        try:
            with bad_request():                      # planning runs nothing: whatever fails here changed nothing (400)
                rows, clipped = self.sim.clip(typ, A)
                rows = np.asarray(rows, dtype=np.float64)
                target = self._interp[typ]           # a target can be interpolated and held; a command cannot
                held = self._in_force(at - 1, nxt, typ) if target else None
                if held is not None and held.shape != rows.shape[1:]:
                    held = None                      # (an adapter whose command() has not the type's layout)
                if target and interp == "linear":    # linear starts from the target in force just before `at`
                    prev = np.asarray(self.sim.command(typ), dtype=np.float64) if held is None else held
                    if rows.ndim != 2 or prev.shape != rows.shape[1:]:
                        raise ValueError(f"{typ}: cannot interpolate rows of shape {list(rows.shape[1:])} from the "
                                         f"command in force, of shape {list(prev.shape)}; send interpolate='hold'")
                    steps = []
                    for row in rows:
                        steps += [prev + (row - prev) * (j / k) for j in range(1, k + 1)]
                        prev = row
                else:                                # hold; and a command stands for itself, one row one control step
                    steps = [row for row in rows for _ in range(k)]
                head = list(self.plan)[:keep]
                if len(head) < keep:
                    # A gap before `at`. A target of this type in force there is held through it (rows of call -1).
                    # Anything else -- a command (repeating it would issue it again at every step of the gap), or a
                    # plan that holds another action type there -- leaves the gap to the simulator's hold row, as
                    # when the plan has run out.
                    head += [HELD if held is None else (typ, held, -1)] * (keep - len(head))
        except Refused as exc:                       # the request itself passed its checks: keep it on the record
            self.log("plan_refused", type=typ, at=at, error=str(exc)[:300])
            raise
        self.calls += 1
        self.rows += len(A)
        self.plan = collections.deque(head + [(typ, s, self.calls) for s in steps[late:]])
        self.late_steps += min(late, len(steps))
        self._start_clock()
        rec = Recorder(self.views, cams, fps, depth, "none")
        rec.start()
        rec.finish()
        out = {**self.meta(), "chunk_id": self.calls, "type": typ, "n_rows": int(len(A)), "dt": dt,
               "interpolate": interp, "at": at, "start_step": max(at, nxt), "late_steps": late,
               "plan_end_step": nxt + len(self.plan), "clipped": clipped[:200], "n_clipped": len(clipped), "ok": True}
        self._save_call({**out, "note": req["note"]}, A)
        job.finish("rec", out, rec)

    def _rt_observe(self, req: dict, job: _Job) -> None:
        with bad_request():
            seconds, (cams, fps, video, depth) = req["seconds"], req["view"]
            n = int(round(seconds / self.sim.control_dt)) if not (self.done or self.stopping) else 0
            rec = Recorder(self.views, cams, fps, depth, video if n or video != "mp4" else "frames")   # no time: no video
            self._frame_budget(rec, n)
        if n:
            # Every pending watch holds its images until it completes: together they stay within the per-call frame
            # budget, or concurrent watches could exhaust the sidecar's memory (an OOM kill is no crash record, so it
            # would count as infrastructure: a free retry). Nothing ran: a 429 to retry once a watch completes.
            pending = sum(w.rec.images_per_call(w.end - w.start) for w in self.watches)
            if pending + rec.images_per_call(n) > self.max_frames:
                raise Refused(429, {"error": f"the pending watches already hold up to {pending} images and this one "
                                             f"would add {rec.images_per_call(n)}: more than max_frames_per_call = "
                                             f"{self.max_frames} in flight; wait for a watch to complete, or ask for "
                                             "fewer cameras or a lower video_fps", "images_in_flight": pending})
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

    def _rt_reset(self, meta: dict, job: _Job) -> None:
        self._reset_view(meta)                       # a refused reset (409, 400) changes nothing: the watches go on
        self._release_watches()
        out, prts = self._reset(meta, {})            # 2.1's reset: abandons the episode, a new one (paused)
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

    @staticmethod
    def _renders(job: _Job) -> bool:
        """Does serving this request render cameras? (What a request without images costs is bounded by its checks.)"""
        route, req = (job.req + (None, None))[:2]
        if route in ("/submit", "/observe"):
            return bool(req["view"][0])
        return route == "/reset" and not (isinstance(req.get("cameras"), list) and not req["cameras"])

    def _may_serve(self, job: _Job, behind: bool, now: float) -> bool:
        if not self.running or self.done or self.stopping:
            return True                              # no clock to keep
        kind = self._renders(job)
        return not (kind and now < self._render_gate) and not (behind and now < self._gate[kind])

    def _take(self, behind: bool, timeout: float) -> _Job | None:
        """The next request to serve now, waiting up to `timeout` for one: the oldest held one whose time has come,
        else the queue's next -- which is held instead, if its time has not come."""
        now = time.monotonic()
        for job in self._held:
            if self._may_serve(job, behind, now):
                self._held.remove(job)
                return job
        if self._held and self.running:              # do not sleep past a held request's time
            gates = [self._gate[k] for k in (True, False)] + [self._render_gate]
            timeout = min([timeout] + [g - now for g in gates if g > now])
        try:
            job = self.q.get(timeout=timeout) if timeout > 0 else self.q.get_nowait()
        except queue.Empty:
            return None
        if job.req and not self._may_serve(job, behind, time.monotonic()):
            self._held.append(job)
            return None
        return job

    def loop(self, until: threading.Event | None = None) -> None:
        """The simulator thread: control steps when due, requests in between, the wrap-up after SIGUSR1."""
        while until is None or not until.is_set():
            self.poll()
            if self.t0 is None and self._t_seen is not None:
                self.first_request()                 # a request that ended on its HTTP thread started the trial's time
            wait = self.due_in(time.monotonic())
            if wait is not None and wait <= 0:
                self.tick()
                # Behind the clock still (the next step is due at once): the steps come first. A waiting request is
                # served once the clock has caught up -- so requests queue behind each other, not into the clock --
                # or, for a simulator that cannot keep up by itself, BEHIND_PACE times the last request's time after
                # it (a cheap request: at once, one per step; a long render: a fifth of the time at most).
                wait = self.due_in(time.monotonic())
                job = self._take(wait is not None and wait <= 0, 0.0)
            else:
                job = self._take(False, 0.25 if wait is None else min(wait, 0.25))
            if job is None:
                continue
            kind, t = bool(job.req) and self._renders(job), time.monotonic()
            self.dispatch(job)
            now = time.monotonic()
            self.request_busy_s += now - t
            self._gate[kind] = now + BEHIND_PACE * (now - t)
            if kind and now - t > MAX_LAG_S:         # a stall by itself: the next render waits, clock on time or not
                self._render_gate = self._gate[kind]

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
                self._serve("GET", 0)

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if not 0 <= n <= MAX_BODY:           # refused unread: drop the connection with it
                    self.close_connection = True
                self._serve("POST", n)

            def _serve(self, method: str, n: int) -> None:
                try:
                    req = svc.front(method, self.path, n, self.rfile.read)   # all that needs no simulator: here
                except OSError:                      # the client went away mid-body
                    raise
                except Exception as exc:  # noqa: BLE001 -- never an HTTP thread's traceback instead of an answer
                    traceback.print_exc()
                    req = ("reply", *svc._reply_json(500, {"error": "service error", "detail": repr(exc)[:200]}))
                self._send(*(req[1:] if req[0] == "reply" else svc.submit_job(_Job(method, self.path, req=req))))

        class Server(ThreadingHTTPServer):
            daemon_threads = True

        return Server(address, Handler)

    def serve(self, port: int = 8000) -> None:
        import signal
        signal.signal(signal.SIGUSR1, self.on_sigusr1)
        srv = self.bind(port)
        sys.setswitchinterval(SWITCH_INTERVAL_S)     # the HTTP threads give the simulator thread its turn quickly
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
