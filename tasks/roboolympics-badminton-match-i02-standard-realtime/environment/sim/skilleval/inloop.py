"""The skill in the loop (docs/construction_zh.md step 3 "技能在环", low level): during the match the player's
competition program sends skill calls (e.g. `hit {t, pos, normal, vel}`) and the platform lowers each call with the
player's OWN implementation of the skill (the deliverable, /app/output/skill/<module>.py) running sandboxed
(skilleval/skillhost.py: in a generated task the seat's own skill container, reached over a Unix socket; in tests and
core.local.play a process of the simulator's). So the skill tested after the match (skilleval/evaluate.py) is the
skill that played it: every call records the sha256 of the skill's files.

    layer = layer_from_env(JointLayer(), CONTRACTS, decl, spec=skill_spec, control_dt=DT, raw_allowed=..., ...)
    # None unless RCB_SKILL_INLOOP_<seat> names the seat's skill: "unix:/skillipc/A/skill.sock" (generated tasks,
    # tools/generate.py) or a directory (tests, pilots); RCB_SKILL_INLOOP_LOG: a directory for inloop_<seat>.jsonl;
    # RCB_SKILL_INLOOP_TIMING: "wall" (default: the match service) or "free" (core.local.play: no wall clock)

The rules (InLoopLayer; sport.toml [modes.low.inloop], skilleval/declare.py):
  skill calls   the contract's skills: the request is checked against the contract (400 if invalid; `entity` kept for
                a seat with several robots); the skill gets the seat's state (state_of: by default the whitelisted
                observation, no images, with `step`, the control step the state was taken at, and `entity`) and the
                public spec (with `timing`); its answer is checked by the low level's own parser; an error, a time-out,
                None or an invalid answer lowers to `noop` (nothing changes; counted, the reason in the reply)
  other acts    types in `free` always pass; the others only when raw_allowed(seat, match, cmd) (the sport decides,
                e.g. no ball in play; the 2-argument form raw_allowed(seat, match) is accepted too); otherwise
                refused (409): the core skill cannot be bypassed with joint commands
  step()        every step_every control steps (the core's per-step `tick`), with the seat's state
  time          timing "wall" (the match service, #90 decision 6: the skill's compute counts in match time): a skill
                call is taken off the world's lock (the core's snapshot / prepare path: the world runs on while it
                computes) and takes effect at the first control step after it returns; step() runs in a background
                thread and its command takes effect at the first step after it returns (dropped if the unit ended);
                loading runs in that thread too; from a skill call's arrival until its command takes effect no
                step() runs (one computed on an older state is dropped), so the call's plan meets the target it
                expected. `t` counts from state["step"] (the step the call arrived), as in the API test. Timing "free"
                (core.local.play, tests): every call is synchronous, the world waits
  code          loaded at a unit's start (a point) and kept for the unit; at the next unit's start the skill directory
                is hashed again and the process restarted only if the files changed (the player may improve its skill
                between points); the process runs on a private copy of the files
  log           per call: unit, the step it was called at (k) and the step when it returned (k_done), function, sha256
                of the files, wall time, ok / error (`calls`; JSON lines in `log_path`); per load: unit, sha256, ok
"""

from __future__ import annotations

import inspect
import json
import os
import threading
import time
from pathlib import Path

from core.observe import filter_fields
from core.spec import whitelist
from core.sport import Refused

from .sandbox import SkillError
from .skillhost import RemoteHost, SkillHost, files_sha

__all__ = ["InLoop", "InLoopLayer", "files_sha", "layer_from_env"]


def _host(skill):
    if hasattr(skill, "refresh") and hasattr(skill, "call"):
        return skill
    s = str(skill)
    return RemoteHost(s[len("unix:"):]) if s.startswith("unix:") else SkillHost(s)


def _q(xs, p):
    return xs[min(len(xs) - 1, int(p * len(xs)))]


class InLoop:
    """One seat's skill for a match (see the module docstring): a host (SkillHost / RemoteHost) plus the call log."""

    def __init__(self, skill, module: str, spec: dict, timeouts: dict | None = None, load_timeout_s: float = 30.0,
                 log_path=None):
        self.host = _host(skill)
        self.module = module
        self.host.configure(module, spec, timeouts, load_timeout_s)
        self.calls: list[dict] = []
        self.loads: list[dict] = []
        self.errors: dict = {}                 # function -> failed calls
        self.log_path = Path(log_path) if log_path else None
        self.unit = None
        self.sha = None
        self._lock = threading.Lock()          # one host operation at a time (a skill process answers one call)
        self._log_lock = threading.Lock()

    def _log(self, rec: dict):
        if self.log_path is None:
            return
        with self._log_lock, open(self.log_path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def refresh(self, unit):
        """At the start of a unit: reload if the files changed."""
        if unit == self.unit:
            return
        self.unit = unit
        with self._lock:
            rec = self.host.refresh(unit)
            self.sha = self.host.status().get("sha256")
        if rec is not None:
            self.loads.append(rec)
            self._log({"op": "load", **rec})

    def has(self, fn: str) -> bool:
        return self.host.has(fn)

    def status(self) -> dict:
        return self.host.status()

    def call(self, fn: str, *args, state: dict, k: int, k_now=None):
        """The skill's answer (None on an error or a time-out); every call is logged (`last` is its record)."""
        rec = {"op": "call", "unit": self.unit, "k": int(k), "fn": fn, "sha256": self.sha}
        t0 = time.monotonic()
        with self._lock:
            try:
                ret = self.host.call(fn, list(args), state)
                rec["ok"] = True
            except SkillError as e:
                ret, rec["ok"], rec["error"] = None, False, f"{e.kind}: {str(e)[:600]}"
                if e.kind == "host":
                    rec["host_error"] = True
        rec["wall_s"] = round(time.monotonic() - t0, 5)
        rec["k_done"] = int(k_now()) if k_now is not None else int(k)
        if not rec["ok"]:
            self.errors[fn] = self.errors.get(fn, 0) + 1
        self.calls.append(rec)
        self._log(rec)
        return ret

    @property
    def last(self) -> dict:
        return self.calls[-1] if self.calls else {}

    def summary(self) -> dict:
        out = {"loads": self.loads, "calls": len(self.calls),
               "sha256": sorted({c["sha256"] for c in self.calls if c["sha256"]}),
               "host_errors": sum(1 for c in self.calls if c.get("host_error"))}
        for fn in sorted({c["fn"] for c in self.calls}):
            cs = [c for c in self.calls if c["fn"] == fn]
            w = sorted(c["wall_s"] for c in cs)
            lat = sorted(c["k_done"] - c["k"] for c in cs)
            out[fn] = {"n": len(w), "errors": self.errors.get(fn, 0),
                       "wall_p50_s": _q(w, .5), "wall_p95_s": _q(w, .95), "wall_max_s": w[-1],
                       "steps_p50": _q(lat, .5), "steps_p95": _q(lat, .95), "steps_max": lat[-1]}
        return out

    def close(self):
        with self._lock:
            self.host.close()


class _Worker:
    """Timing "wall": the seat's skill operations in a background thread, in order: loads first, then skill calls
    (the act's thread waits for its own), then step() calls (one at a time). A skill call supersedes step(): from its
    arrival until its command has taken effect (call_pending; InLoopLayer.lower clears it) no step() is started and
    the answer of one computed on an older state is dropped (gen), so the skill call's plan meets the target it
    expected (a step() command applied meanwhile would change the target in force under it)."""

    def __init__(self, loop: InLoop, k_now):
        self.loop, self.k_now = loop, k_now
        self.cv = threading.Condition()
        self.jobs: list[dict] = []
        self.step_job = None                   # the step() queued or running
        self.step_out = None                   # (unit, answer) of the last step() that returned
        self.gen = 0                           # bumped by every skill call: older step() answers are dropped
        self.call_pending = False              # a skill call arrived and its command has not taken effect yet
        self.closed = False
        threading.Thread(target=self._run, daemon=True, name="inloop").start()

    def _insert(self, job: dict):
        """Before the queued step() calls (they give way), after the loads and the earlier skill calls."""
        i = next((n for n, j in enumerate(self.jobs) if j["kind"] == "step"), len(self.jobs))
        self.jobs.insert(i, job)
        self.cv.notify_all()

    def refresh(self, unit):
        with self.cv:
            self.step_out, self.call_pending = None, False
            if self.step_job is not None and not self.step_job.get("started"):
                self.jobs.remove(self.step_job)
                self.step_job = None
            self._insert({"kind": "refresh", "unit": unit})

    def begin_call(self):
        """A skill call arrived (under the world's lock, at its snapshot): no step() answer from before it is applied
        and no step() starts until its command has taken effect."""
        with self.cv:
            self.gen += 1
            self.call_pending, self.step_out = True, None
            if self.step_job is not None and not self.step_job.get("started"):
                self.jobs.remove(self.step_job)
                self.step_job = None

    def call(self, fn, args, state, k):
        job = {"kind": "call", "fn": fn, "args": args, "state": state, "k": k, "done": False}
        with self.cv:
            self.call_pending = True
            self._insert(job)
            while not job["done"]:
                self.cv.wait(0.5)
        return job["ret"], job["rec"]

    def submit_step(self, fn, state, k, unit) -> bool:
        with self.cv:
            if self.closed or self.call_pending or self.step_job is not None or self.step_out is not None:
                return False
            self.step_job = {"kind": "step", "fn": fn, "state": state, "k": k, "unit": unit, "gen": self.gen}
            self.jobs.append(self.step_job)
            self.cv.notify_all()
            return True

    def take_step(self, unit):
        with self.cv:
            out, self.step_out = self.step_out, None
        return out[1] if out is not None and out[0] == unit else None

    def _run(self):
        while True:
            with self.cv:
                while not self.jobs and not self.closed:
                    self.cv.wait(1.0)
                if self.closed:
                    for j in self.jobs:                  # release any waiting act
                        j.update(done=True, ret=None, rec={"ok": False, "error": "host: closed"})
                    self.cv.notify_all()
                    return
                job = self.jobs.pop(0)
                job["started"] = True
            ret = None
            try:
                if job["kind"] == "refresh":
                    self.loop.refresh(job["unit"])
                else:
                    args = job.get("args", [])
                    ret = self.loop.call(job["fn"], *args, state=job["state"], k=job["k"], k_now=self.k_now)
                    job["rec"] = self.loop.last
            except Exception as e:  # noqa: BLE001  (never leave a waiting act hanging)
                ret, job["rec"] = None, {"ok": False, "error": f"host: {type(e).__name__}: {e}"}
            with self.cv:
                if job["kind"] == "call":
                    job.update(ret=ret, done=True)
                elif job["kind"] == "step" and self.step_job is job:
                    self.step_job = None
                    if job["gen"] == self.gen and not self.call_pending:
                        self.step_out = (job["unit"], ret)
                self.cv.notify_all()

    def effect(self):
        """The skill call's command has taken effect (or failed): step() may run again."""
        with self.cv:
            self.call_pending = False

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()


class InLoopLayer:
    """The low level with the core skill(s) lowered by the player's own implementation (see the module docstring)."""

    level = "low"
    worker = None
    delay_steps = 0

    def __init__(self, low, contracts: dict, loops: dict, decl: dict, raw_allowed=None, noop=None, step_every: int = 2,
                 step_fn: str = "step", free=(), state_of=None, timing: str = "free"):
        if timing not in ("wall", "free"):
            raise ValueError("timing must be 'wall' or 'free'")
        self.low, self.contracts, self.loops = low, contracts, loops
        self.allowed = whitelist(decl)
        self.raw_allowed = raw_allowed or (lambda seat, match, cmd=None: True)
        try:
            self._raw3 = len(inspect.signature(self.raw_allowed).parameters) >= 3
        except (TypeError, ValueError):
            self._raw3 = False
        self.noop = noop or {"type": "hold"}
        self.step_every, self.step_fn = int(step_every), step_fn
        self.free = frozenset(free)
        self.state_of = state_of
        self.timing = timing
        self.failures: list[str] = []
        self._units: dict = {}
        self._workers: dict = {}

    # ------------------------------------------------------------------ helpers
    def _worker(self, seat, match) -> _Worker:
        w = self._workers.get(seat)
        if w is None:
            w = self._workers[seat] = _Worker(self.loops[seat], lambda m=match: m.k)
        return w

    def _ensure_unit(self, seat, match):
        """At the first contact with a new unit: (re)load the seat's skill (in the background with timing wall)."""
        u = match.unit()
        if seat in self._units and self._units[seat] == u:
            return
        self._units[seat] = u
        if self.timing == "wall":
            self._worker(seat, match).refresh(u)
        else:
            self.loops[seat].refresh(u)

    def _state(self, seat, match, cmd=None):
        if self.state_of is not None:
            st = dict(self.state_of(seat, match, cmd))
        else:
            st, _ = filter_fields(match.observe(seat), self.allowed)
        st["step"] = int(match.k)
        if cmd is not None and cmd.get("entity") is not None:
            st["entity"] = cmd["entity"]
        return st

    def _raw_ok(self, seat, match, cmd) -> bool:
        return bool(self.raw_allowed(seat, match, cmd) if self._raw3 else self.raw_allowed(seat, match))

    def _lowered(self, seat, ret, match, what, cmd=None):
        """(the low-level command, None) or (None, why)."""
        if ret is None:
            return None, "the skill gave no command"
        if isinstance(ret, dict) and cmd and cmd.get("entity") is not None and "entity" not in ret:
            ret = {**ret, "entity": cmd["entity"]}
        try:
            return self.low.parse(seat, ret, match, {}), None
        except Refused as e:
            why = f"{what}: the low level refused the skill's command: {e}"[:400]
            self.failures.append(why)
            return None, why

    # ------------------------------------------------------------------ the action layer
    def schema(self, match, seat):
        return {**self.low.schema(match, seat), **{c.name: c.request_schema()[c.name] for c in self.contracts.values()}}

    def parse(self, seat, body, match, ctx):
        t = body.get("type") if isinstance(body, dict) else None
        c = self.contracts.get(t)
        if c is not None:
            req = {k: body.get(k) for k in c.args}
            why = c.valid_request(req)
            if why:
                raise Refused(why)
            cmd = {"type": c.name, **req}
            if body.get("entity") is not None:
                ents = [str(e) for e in (match.entities(seat) if hasattr(match, "entities") else [])]
                if ents and str(body["entity"]) not in ents:
                    raise Refused(f"entity must be one of {ents}")
                cmd["entity"] = body["entity"]
            return cmd
        cmd = self.low.parse(seat, body, match, ctx)
        if t in self.free or self._raw_ok(seat, match, cmd):
            return cmd
        raise Refused(f"skill in the loop: the core skill is played through your own implementation; send "
                      f"{sorted(self.contracts)} (this command only while no ball is in play"
                      + (f"; {sorted(self.free)} at any time)" if self.free else ")"), 409)

    def snapshot(self, seat, cmd, match, ordinal):
        c = self.contracts.get(cmd.get("type"))
        if c is None:
            snap = getattr(self.low, "snapshot", None)
            job = snap(seat, cmd, match, ordinal) if snap else None
            return None if job is None else {"low": job}
        if seat not in self.loops:
            return None
        self._ensure_unit(seat, match)
        if self.timing == "wall":
            self._worker(seat, match).begin_call()
        return {"seat": seat, "skill": c.name, "args": c.args_of(cmd), "state": self._state(seat, match, cmd),
                "k": int(match.k), "match": match}

    def prepare(self, job):
        if "low" in job:
            return {"low": self.low.prepare(job["low"])}
        seat, loop = job["seat"], self.loops[job["seat"]]
        if self.timing == "wall":
            ret, rec = self._worker(seat, job["match"]).call(job["skill"], job["args"], job["state"], job["k"])
        else:
            ret = loop.call(job["skill"], *job["args"], state=job["state"], k=job["k"])
            rec = loop.last
        return {"ret": ret, "rec": rec}

    def lower(self, seat, cmd, prepared, match):
        c = self.contracts.get(cmd.get("type"))
        if c is None:
            p = prepared["low"] if isinstance(prepared, dict) and "low" in prepared else prepared
            return self.low.lower(seat, cmd, p, match)
        if seat not in self.loops:
            return dict(self.noop), {"skill": c.name, "ok": False, "skill_failed": True,
                                     "error": "no skill in the loop for this seat"}
        if prepared is None:                     # no snapshot / prepare (the turn protocol, direct calls): now
            self._ensure_unit(seat, match)
            loop = self.loops[seat]
            ret = loop.call(c.name, *c.args_of(cmd), state=self._state(seat, match, cmd), k=match.k)
            prepared = {"ret": ret, "rec": loop.last}
        rec = prepared.get("rec") or {}
        if seat in self._workers:
            self._workers[seat].effect()         # from the next step on, step() sees the call's command in force
        low, why = self._lowered(seat, prepared.get("ret"), match, c.name, cmd)
        info = {"skill": c.name, "sha256": rec.get("sha256"), "wall_s": rec.get("wall_s"), "k_call": rec.get("k"),
                "ok": low is not None}
        if low is None:
            return dict(self.noop), {**info, "skill_failed": True, "error": rec.get("error") or why}
        return low, info

    def tick(self, seat, match):
        """Every control step (core): step() every step_every steps; its command (or None)."""
        loop = self.loops.get(seat)
        if loop is None:
            return None
        self._ensure_unit(seat, match)
        due = match.k % self.step_every == 0 and loop.has(self.step_fn)
        if self.timing == "free":
            if not due:
                return None
            ret = loop.call(self.step_fn, state=self._state(seat, match), k=match.k)
            return None if ret is None else self._lowered(seat, ret, match, self.step_fn)[0]
        w = self._worker(seat, match)
        ret = w.take_step(match.unit())
        out = None if ret is None else self._lowered(seat, ret, match, self.step_fn)[0]
        if due:
            w.submit_step(self.step_fn, self._state(seat, match), int(match.k), match.unit())
        return out

    def reply(self, seat, cmd, info, match):
        if cmd.get("type") in self.contracts:
            loop = self.loops.get(seat)
            st = loop.status() if loop else {}
            return {"skill": {**{k: info[k] for k in ("skill", "sha256", "wall_s", "k_call", "ok", "skill_failed",
                                                      "error") if info.get(k) is not None},
                              "status": {"sha256": st.get("sha256"), "loaded": st.get("loaded"),
                                         "load_error": st.get("load_error"),
                                         "step_errors": loop.errors.get(self.step_fn, 0) if loop else 0}}}
        return self.low.reply(seat, cmd, info, match)

    def summary(self) -> dict:
        return {seat: loop.summary() for seat, loop in self.loops.items()}

    def close(self):
        for w in self._workers.values():
            w.close()
        for loop in self.loops.values():
            loop.close()


def layer_from_env(low, contracts: dict, decl: dict, *, spec, control_dt: float, seats=("A", "B"), raw_allowed=None,
                   state_of=None, environ=None):
    """The InLoopLayer of a sport's low level when the environment names a seat's skill (else None: the sport keeps
    its own low level). decl = the sport's sport.toml ([modes.low] deliverable and time limits, [modes.low.inloop]
    skills / step_every / free / noop); spec = the public spec a call gets (dict or callable), to which `timing` is
    added (control_dt, slowdown, period_s, compute_counts)."""
    env = os.environ if environ is None else environ
    lo = (decl.get("modes") or {}).get("low") or {}
    il = lo.get("inloop") or {}
    srcs = {s: env.get(f"RCB_SKILL_INLOOP_{s}") for s in seats}
    if not srcs.get(seats[0]) and env.get("RCB_SKILL_INLOOP"):
        srcs[seats[0]] = env["RCB_SKILL_INLOOP"]                    # the single-seat shorthand (pilots)
    srcs = {s: v for s, v in srcs.items() if v}
    if not srcs:
        return None
    timing = env.get("RCB_SKILL_INLOOP_TIMING", "wall")
    module = Path(lo["deliverable"]["path"]).stem
    tl = {k: float(v) for k, v in (lo["deliverable"].get("time_limits_s") or {}).items()}
    try:
        slow = float(env.get("RO_SLOWDOWN") or 0) or None
    except ValueError:
        slow = None
    sp = dict(spec() if callable(spec) else spec)
    counts = timing == "wall"
    sp["timing"] = {"control_dt": float(control_dt), "slowdown": slow if counts else None,
                    "period_s": round(float(control_dt) * slow, 6) if (counts and slow) else None,
                    "compute_counts": counts,
                    "note": ("your call computes while the world runs (1 wall second = 1 / slowdown game seconds); "
                             "its command takes effect at the first control step after it returns; t counts from "
                             "state['step'], the step your call arrived" if counts else
                             "the world waits for every call (local play)")}
    logd = env.get("RCB_SKILL_INLOOP_LOG")
    loops = {s: InLoop(v, module, sp, timeouts=tl, load_timeout_s=tl.get("load", 30.0),
                       log_path=(Path(logd) / f"inloop_{s}.jsonl") if logd else None) for s, v in srcs.items()}
    skills = list(il.get("skills") or lo.get("implements") or contracts)
    return InLoopLayer(low, {k: contracts[k] for k in skills}, loops, decl, raw_allowed=raw_allowed,
                       noop=dict(il.get("noop") or {"type": "noop"}), step_every=int(il.get("step_every", 2)),
                       free=tuple(il.get("free") or ()), state_of=state_of, timing=timing)
