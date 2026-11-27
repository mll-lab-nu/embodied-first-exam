"""Agent-ended episodes for the eai-standard/2.2 layer (rcb_limited.py): an optional task feature (PROTOCOL §3 "Agent-ended
episodes", docs/protocol/standard_mode.md "Agent-ended episodes"). A task opts in in its `sim` service's environment:

  RCB_AGENT_END: "1"     the service never shows the task's success, a success never ends the episode, POST /finish (JSON {})
                         ends it, and the state the episode ends in is graded (with the task's settle or hold window); a
                         goal made of moments (key strikes, button presses) or judged at a trigger is judged on those as
                         they happened, as the task's instruction says; a failure rule that ends the episode gives 0
  RCB_STEP_LIMIT: "<N>"  (only with RCB_AGENT_END) the episode also ends by itself after N control steps (reason
                         "step_limit"), graded as it stands; what one step is, is the adapter's (its /spec and instruction).
                         Service enforces it: a /submit (a hold chunk too) stops at the step that reaches the limit
                         (Episode.row_cap: one journaled row per control step), the adapter's finish("step_limit") ends
                         the episode there and the answer says so (done, reason "step_limit", duration_s of the steps
                         run); an adapter that ends the episode at its own cap first is left alone (one end only)

Without RCB_AGENT_END nothing here is used: an adapter that imports this module answers exactly as without it.

An adapter (robodojo's sim/server.py is the reference): records the state's success after every control step with
hidden_success() instead of ending the episode, judges the end state in its own finish() for the ends in
END_STATE_REASONS (a settle or hold window, where the task has one, runs from that state), adds final_fields() to
final.json, builds its rcb_limited.Episode with persist=persist(...) and serves with
serve(Service(..., finish=lambda: finish("finished"), end_step_limit=lambda: finish("step_limit"))) instead of
rcb_limited's: the step limit's end is the same call with reason "step_limit", passed explicitly (a service without it does
not start when RCB_STEP_LIMIT is set); the episode's control steps are its status()["control_steps"] (a service whose
status() does not state them does not start with RCB_STEP_LIMIT either). Tests:
agent_end_selftest.py.
"""
from __future__ import annotations

import os
import time
import traceback
from typing import Callable

import rcb_limited as L

ENABLED = os.environ.get("RCB_AGENT_END") == "1"
STEP_LIMIT = int(os.environ.get("RCB_STEP_LIMIT") or 0) or None
if STEP_LIMIT is not None and (not ENABLED or STEP_LIMIT < 1):
    raise RuntimeError("RCB_STEP_LIMIT needs RCB_AGENT_END=1 and a positive number of steps")
HIDDEN_STATE = ("now_success", "seen_step", "trial_seen", "finish_t")   # kept through a resume (Episode persist)
END_STATE_REASONS = ("finished", "timeout", "step_limit")             # ends judged on the state they leave
# final.json "ended_by" (PROTOCOL §3): the service's end reasons; "session_end" is the end of the agent's session (its
# time limit, its token budget or its own exit: the runner's record says which)
ENDED_BY = {"finished": "finish", "step_limit": "step_limit", "timeout": "session_end", "error": "error",
            "sim_crashed_on_call": "error", "sim_crashed": "error", "resume_failed": "error",
            "instance_mismatch": "error", "call_watchdog": "error"}   # any other end: "failed" (the task's failure rule)
SUCCESS_SIGNAL_NOTE = ("hidden: the service never tells you whether you have succeeded and a success does not end the "
                       "episode; POST /finish (JSON {}) ends it (if you never call it, the end of your session does) and "
                       "the episode is judged then, as the instruction's Goal says: on how things stand at that moment, "
                       "and on any steps the Goal says count as they happen; after /finish every call is refused (409)")


def hidden_success(state: dict, ok, log: Callable | None = None, step: int | None = None) -> None:
    """The task's success as the state now is (after a control step or a call): kept as state["now_success"], never
    latched and never shown; the first one of the episode is logged ("hidden_success")."""
    state["now_success"] = bool(ok)
    if ok and state.get("seen_step") is None:
        state["seen_step"], state["trial_seen"] = (0 if step is None else int(step)), True
        if log is not None:
            log({"ev": "hidden_success", "control_steps": state["seen_step"]})


def finished(state: dict) -> bool:
    """The agent ended the episode with POST /finish: every call after it but GET /spec and /status is a 409."""
    return ENABLED and bool(state.get("done")) and state.get("reason") == "finished"


def persist(keys=()) -> tuple:
    """The adapter's Episode persist keys, with the hidden success's when the feature is on."""
    keys = tuple(keys)
    return keys + tuple(k for k in HIDDEN_STATE if k not in keys) if ENABLED else keys


def final_fields(state: dict, steps_used: int | None = None) -> dict:
    """final.json's record of the feature (evidence only; nothing without it)."""
    if not ENABLED:
        return {}
    t0, ft = state.get("t_first"), state.get("finish_t")
    r = state.get("reason")
    out = {"success_signal": "hidden", "ended_by": ENDED_BY.get(str(r).split(":")[0], "failed") if r else None,
           "hidden_success_seen": state.get("seen_step") is not None,
           "hidden_success_first_step": state.get("seen_step"), "trial_hidden_success_seen": bool(state.get("trial_seen")),
           "finish_time_s": round(float(ft) - float(t0), 1) if ft and t0 else None}
    if STEP_LIMIT is not None:
        out.update({"step_limit": STEP_LIMIT, **({"steps_used": int(steps_used)} if steps_used is not None else {})})
    return out


def steps_left(used: int) -> dict:
    """The step limit and what is left of it, for every meta and /status (nothing without a step limit)."""
    return {"step_limit": STEP_LIMIT, "steps_left": max(0, STEP_LIMIT - int(used))} if STEP_LIMIT is not None else {}


def spec_limit(spec: dict) -> None:
    """With RCB_STEP_LIMIT: /spec.max_control_steps and /spec.budget.steps state the episode's step limit, the lower of
    RCB_STEP_LIMIT and the adapter's own max_control_steps (an adapter cap of its own still ends the episode)."""
    own = spec.get("max_control_steps")
    own = int(own) if isinstance(own, (int, float)) and not isinstance(own, bool) and own > 0 else None
    cap = STEP_LIMIT if own is None else min(STEP_LIMIT, own)
    spec["max_control_steps"] = cap
    if not isinstance(spec.get("budget"), dict):
        spec["budget"] = {}
    spec["budget"]["steps"] = cap


def control_steps(status: dict) -> int | None:
    """status()["control_steps"] as an int, None if it is missing or not a number."""
    n = status.get("control_steps") if isinstance(status, dict) else None
    return int(n) if isinstance(n, (int, float)) and not isinstance(n, bool) else None


class Service(L.Service):
    """rcb_limited.Service with finish() (the adapter ends the episode, reason "finished": POST /finish) and hidden_keys
    (meta / status keys that would tell the agent about the task's success or progress, dropped from every answer).
    With RCB_STEP_LIMIT it enforces the limit around the adapter's submit / observe (a hold chunk runs as an observe
    watch): end_step_limit() (the adapter's finish with reason "step_limit") ends the episode there."""

    def __init__(self, *, finish: Callable | None = None, hidden_keys=(), end_step_limit: Callable | None = None, **kw):
        super().__init__(**kw)
        self.finish, self.hidden_keys = finish, frozenset(hidden_keys or ())
        self.end_step_limit = end_step_limit
        if ENABLED and STEP_LIMIT is not None:
            self.submit, self.observe = self._limited(self.submit), self._limited(self.observe)

    def hide(self, d: dict) -> dict:
        """An answer's meta or /status without the adapter's hidden_keys."""
        return {k: v for k, v in d.items() if k not in self.hidden_keys} if ENABLED else d

    def steps_used(self) -> int:
        """The episode's control steps as the adapter counts them (status()["control_steps"], per episode where the
        adapter has resets). serve() checks that status() states them; a status() that fails or stops stating them
        raises (a simulator error), never a silent count of something else."""
        n = control_steps(self.status())
        if n is None:
            raise RuntimeError("RCB_STEP_LIMIT is set, but status() states no control_steps")
        return n

    def at_step_limit(self) -> bool:
        """The lock held: end the episode (reason "step_limit") if its control steps reached RCB_STEP_LIMIT and nothing
        ended it yet (an adapter with a cap of its own ends it itself, first). True if this call ended it."""
        E = self.state
        if STEP_LIMIT is None or E.get("done") or E.get("exiting") or self.steps_used() < STEP_LIMIT:
            return False
        if self.end_step_limit is None:
            raise RuntimeError("RCB_STEP_LIMIT reached, but this service has no end_step_limit()")
        self.end_step_limit()
        return bool(E.get("done"))

    def _limited(self, call: Callable) -> Callable:
        """submit(meta, A) / observe(meta) under the step limit: the journal stops the call at the limit
        (Episode.row_cap), then the episode ends there and the answer's done / reason / steps_left say so."""
        def limited(*a):
            ep = self.episode
            if ep is not None:
                ep.row_cap = ep.rows + max(0, STEP_LIMIT - self.steps_used())
            try:
                out, blobs = call(*a)
            finally:
                if ep is not None:
                    ep.row_cap = None
            if self.at_step_limit() and isinstance(out, dict):
                E = self.state
                out = {**out, "done": True, "reason": E.get("reason"),
                       **(steps_left(self.steps_used()) if "steps_left" in out else {})}
            return out, blobs
        return limited


def make_handler(svc: Service):
    """rcb_limited's handler with, when the feature is on, POST /finish, the 409 after it and the hidden keys dropped."""
    base = L.make_handler(svc)
    if not ENABLED:
        return base

    class H(base):
        def _rcb1(self, meta: dict, parts: list) -> None:
            super()._rcb1(svc.hide(meta), parts)

        def _drain(self) -> None:
            """Read a request body without parsing it (POST /finish): a bad or oversized Content-Length is still refused."""
            try:
                n = int(self.headers.get("Content-Length", 0))
            except ValueError:
                n = -1
            if n < 0:
                raise ValueError("bad Content-Length")
            if n > L.MAX_BODY:
                raise ValueError("request too large")
            while n > 0:
                got = self.rfile.read(min(n, 1 << 20))
                if not got:
                    break
                n -= len(got)

        def _end(self, end: Callable):
            """The lock held: an end of the episode by the service (end(): the adapter's finish(), or at_step_limit()),
            journaled as a call. Its failure is a simulator error (§4.6): on_submit_error() ends the episode with
            reason "error" (if that fails too, the episode is marked ended "error" here) and the answer is a 500; the
            state is checkpointed either way. None, or the (500, JSON) to answer."""
            E, ep = svc.state, svc.episode
            cid = ep.call_begin(self.path) if ep else 0
            err = None
            try:
                end()
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc(); E["error"] = repr(exc)
                svc.log({"ev": "error", "path": self.path, "error": repr(exc)})
                try:
                    svc.on_submit_error(exc)             # ends the episode, reason "error"
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                if not E.get("done"):                    # last resort: the end failed and so did the error's end
                    E["done"], E["reason"] = True, "error"
                    E.setdefault("t_end", time.time())
                err = (500, {"error": "simulator error", "detail": repr(exc)[:200]})
            finally:
                if ep:
                    try:
                        ep.checkpoint(E, svc.state_sha, svc.proprio)
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
                    ep.call_end(cid, self.path)
            return err

        def do_GET(self):
            if self.path == "/status":
                st = svc.hide(svc.status())
                return self._json(200, {**st, "resumes": svc.episode.resumes} if svc.episode else st)
            if self.path.startswith("/operations/") and finished(svc.state):   # 2.4: after /finish every call but
                E = svc.state                                                  # GET /spec and /status is a 409
                return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
            return super().do_GET()

        def do_POST(self):
            E, ep = svc.state, svc.episode
            if STEP_LIMIT is not None and self.path == "/submit" and not E.get("done") and svc.lock.acquire(blocking=False):
                err = None                       # a limit reached without an end (a step outside a call): end it now,
                try:                             # so the /submit is a 409 (never waits: a call in progress checks
                    try:                         # the limit itself when it ends)
                        due = not E.get("exiting") and svc.steps_used() >= STEP_LIMIT
                    except Exception:  # noqa: BLE001   the count failed: at_step_limit() fails the same way, in _end
                        due = True
                    if due:
                        err = self._end(svc.at_step_limit)
                finally:
                    svc.lock.release()
                if err is not None:
                    try:
                        self._drain()            # the request's body, unread (the answer is the error, not a 409)
                    except Exception:  # noqa: BLE001
                        pass
                    return self._json(*err)
            if self.path not in ("/submit", "/observe", "/kinematics", "/finish") or not (
                    finished(E) or self.path == "/finish"):
                return super().do_POST()
            try:
                if self.path == "/finish":       # its body is optional and ignored (read and dropped, never parsed)
                    self._drain()
                else:
                    self._body()
            except Exception as exc:  # noqa: BLE001
                return self._json(413 if "too large" in str(exc) else 400, {"error": str(exc)[:200]})
            if finished(E) or E.get("done") or E.get("exiting"):
                return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
            with svc.lock:                       # the agent ends the episode: the state it leaves is graded
                if E.get("exiting") or E.get("done"):
                    return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
                E["finish_t"] = time.time()
                err = self._end(svc.finish)
                if err is not None:
                    return self._json(*err)
                return self._json(200, {"ok": True, **svc.hide(svc.status())})
    return H


def serve(svc: Service, port: int = 8000) -> None:
    """rcb_limited.serve with this module's handler; with the feature on, an adapter without finish() refuses to start
    (fail closed) and /spec states the success signal."""
    svc.spec.setdefault("on_service_error", L.ON_SERVICE_ERROR)
    if svc.episode is not None:
        svc.spec.setdefault("max_call_wall_s", svc.episode.max_call_wall_s)
    if ENABLED:
        if getattr(svc, "finish", None) is None:
            raise RuntimeError("RCB_AGENT_END=1, but this service has no finish(): it does not implement agent-ended episodes")
        svc.spec["success_signal"] = SUCCESS_SIGNAL_NOTE
        if STEP_LIMIT is not None and getattr(svc, "end_step_limit", None) is None:
            raise RuntimeError("RCB_STEP_LIMIT is set, but this service has no end_step_limit(): pass "
                               "Service(end_step_limit=lambda: finish(\"step_limit\"))")
        if STEP_LIMIT is not None and control_steps(svc.status()) is None:
            raise RuntimeError("RCB_STEP_LIMIT is set, but this service's status() states no control_steps: the "
                               "step limit counts them")
        if STEP_LIMIT is not None:           # /spec states the limit in force (PROTOCOL §3: budget.steps =
            spec_limit(svc.spec)             # max_control_steps = N), whatever the adapter's own spec says
    L.check_spec(svc.spec)
    L.bind(port, make_handler(svc)).serve_forever()
