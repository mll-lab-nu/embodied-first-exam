"""Agent-ended episodes for the eai-standard/2.2 layer (rcb_limited.py): an optional task feature (PROTOCOL §3 "Agent-ended
episodes", docs/protocol/standard_mode.md "Agent-ended episodes"). A task opts in in its `sim` service's environment:

  RCB_AGENT_END: "1"     the service never shows the task's success, a success never ends the episode, POST /finish (JSON {})
                         ends it, and the state the episode ends in is graded (with the task's settle or hold window)
  RCB_STEP_LIMIT: "<N>"  (only with RCB_AGENT_END) the episode also ends by itself after N control steps (reason
                         "step_limit"), graded as it stands; what one step is, is the adapter's (its /spec and instruction)

Without RCB_AGENT_END nothing here is used: an adapter that imports this module answers exactly as without it.

An adapter (robodojo's sim/server.py is the reference): records the state's success after every control step with
hidden_success() instead of ending the episode, judges the end state in its own finish() for the ends in
END_STATE_REASONS (a settle or hold window, where the task has one, runs from that state), adds final_fields() to
final.json, builds its rcb_limited.Episode with persist=persist(...) and serves with
serve(Service(..., finish=lambda: finish("finished"))) instead of rcb_limited's. Tests: agent_end_selftest.py.
"""
from __future__ import annotations

import os
import time
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
            "sim_crashed_on_call": "error"}   # any other end: "failed" (the task's own failure rule)
SUCCESS_SIGNAL_NOTE = ("hidden: the service never tells you whether you have succeeded and a success does not end the "
                       "episode; POST /finish (JSON {}) ends it and the state at that moment is graded (if you never "
                       "call it, the state when your session ends); after /finish every call is refused (409)")


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
    out = {"success_signal": "hidden", "ended_by": ENDED_BY.get(r, "failed" if r else None),
           "hidden_success_seen": state.get("seen_step") is not None,
           "hidden_success_first_step": state.get("seen_step"), "trial_hidden_success_seen": bool(state.get("trial_seen")),
           "finish_time_s": round(float(ft) - float(t0), 1) if ft and t0 else None}
    if STEP_LIMIT is not None:
        out.update({"step_limit": STEP_LIMIT, **({"steps_used": int(steps_used)} if steps_used is not None else {})})
    return out


def steps_left(used: int) -> dict:
    """The step limit and what is left of it, for every meta and /status (nothing without a step limit)."""
    return {"step_limit": STEP_LIMIT, "steps_left": max(0, STEP_LIMIT - int(used))} if STEP_LIMIT is not None else {}


class Service(L.Service):
    """rcb_limited.Service with finish() (the adapter ends the episode, reason "finished": POST /finish) and hidden_keys
    (meta / status keys that would tell the agent about the task's success or progress, dropped from every answer)."""

    def __init__(self, *, finish: Callable | None = None, hidden_keys=(), **kw):
        super().__init__(**kw)
        self.finish, self.hidden_keys = finish, frozenset(hidden_keys or ())

    def hide(self, d: dict) -> dict:
        """An answer's meta or /status without the adapter's hidden_keys."""
        return {k: v for k, v in d.items() if k not in self.hidden_keys} if ENABLED else d


def make_handler(svc: Service):
    """rcb_limited's handler with, when the feature is on, POST /finish, the 409 after it and the hidden keys dropped."""
    base = L.make_handler(svc)
    if not ENABLED:
        return base

    class H(base):
        def _rcb1(self, meta: dict, parts: list) -> None:
            super()._rcb1(svc.hide(meta), parts)

        def do_GET(self):
            if self.path == "/status":
                st = svc.hide(svc.status())
                return self._json(200, {**st, "resumes": svc.episode.resumes} if svc.episode else st)
            return super().do_GET()

        def do_POST(self):
            E, ep = svc.state, svc.episode
            if self.path not in ("/submit", "/observe", "/kinematics", "/finish") or not (
                    finished(E) or self.path == "/finish"):
                return super().do_POST()
            try:
                self._body()
            except Exception as exc:  # noqa: BLE001
                return self._json(413 if "too large" in str(exc) else 400, {"error": str(exc)[:200]})
            if finished(E) or E.get("done") or E.get("exiting"):
                return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
            with svc.lock:                       # the agent ends the episode: the state it leaves is graded
                if E.get("exiting") or E.get("done"):
                    return self._json(409, {"error": "episode finished", "reason": E.get("reason")})
                cid = ep.call_begin(self.path) if ep else 0
                try:
                    E["finish_t"] = time.time()
                    svc.finish()
                    if ep:
                        ep.checkpoint(E, svc.state_sha, svc.proprio)
                finally:
                    if ep:
                        ep.call_end(cid, self.path)
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
    L.check_spec(svc.spec)
    L.bind(port, make_handler(svc)).serve_forever()
