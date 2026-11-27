"""eai-standard/3.0 sim service for HumanCLAW -- the standard-mode sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `HumanClaw` implements rcb_service.Sim for one frozen episode (hc_core.Session).
The protocol, the episode, crash recovery and the finalize live in rcb_service.py, which imports no simulator.
One action type, `skill`: a row is [action_id, value], one HumanCLAW motion skill, one control step (control_dt =
0.5 s, the 15 frames at 30 Hz a skill moves). The verdict is the live episode's: step() reports HumanCLAW's own rule
(hc_core.Session._finish, at the stop or the last allowed action) and the episode ends there; nothing is replayed to
grade it. The video is the live episode's recorded poses, rendered after the verdict (hc_core.episode_video).
Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE      the frozen episode (the privileged twin's instance.json)
  RCB_TASK_TEXT     one sentence for /spec
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA   the service's own (rcb_service.main)

Agent-ended episodes (PROTOCOL §3): HumanCLAW's episode is agent-ended by its
own rule already (only a stop can succeed, the state at the stop is judged), so the service's finish IS the stop: POST
/finish runs the stop action as the episode's last control step (journaled like any other row), and the end of the
agent's session does too, before the episode is judged (reason "timeout"); a stop the agent sends ends the episode as
/finish does (reason "finished"). The 100th action still ends the episode whatever it is (reason "step_limit",
HumanCLAW's own rule: only a stop can succeed). Nothing tells the agent how the episode went: the verdict is HumanCLAW's
at the stop.
"""
from __future__ import annotations

import os
import sys
import traceback

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hc_core  # noqa: E402
import rcb_service  # noqa: E402
from rcb_service import InstanceMismatch, Refused, main  # noqa: E402

IDLE_ROW = np.array([hc_core.IDLE, 0.0], dtype=np.float64)
STOP_ROW = np.array([1.0, 0.0], dtype=np.float64)      # HumanCLAW's stop (action 1): the agent declares it is done
MAX_CONTROL_STEPS = 20000   # a technical bound only: the episode's own limit is max_steps actions (hc_core)


class HumanClaw:
    """One frozen HumanCLAW episode behind the rcb_service.Sim contract. The agent gets the head camera and what a
    body feels (how many actions are left, how far the pelvis has risen or dropped); never its position, the
    target's, the map or the score."""

    control_dt = 0.5
    max_control_steps = MAX_CONTROL_STEPS
    cameras = ("ego",)
    depth_cameras = ()
    proprio_layout = ("actions_used", "actions_left", "pelvis_rise_m")
    raw_dim = 2
    end_judgement = "state"              # agent-ended: the state at the stop (HumanCLAW's own rule)
    hidden_keys = ("step_cap",)

    def __init__(self, instance: str, *, task_text: str = ""):
        self.inst = hc_core.load_instance(instance)
        if self.inst.get("digest") and self.inst["digest"] != hc_core.instance_digest(self.inst):
            raise InstanceMismatch(f"{instance} records digest {self.inst['digest']}, its contents hash to "
                                   f"{hc_core.instance_digest(self.inst)}")
        self.s = hc_core.Session(self.inst)
        if self.inst.get("start_sha"):
            self.start_sha = self.inst["start_sha"]
        self.task_text = task_text
        self.cmd = IDLE_ROW.copy()
        self.hw = list(self.s.ego_rgb().shape[:2])

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        return {
            "simulator": "habitat-sim with HumanCLAW Half-Physics (Bullet), MotionDiT motion skills",
            "robot": "a simulated adult human body (SMPL-X neutral body), moved only by its motion skills",
            "task_text": self.task_text,
            "episode": ("ends at your stop action or POST /finish (the same thing: the stop), at the "
                        f"{self.s.max_steps}th action whatever it is, when your session ends (judged as a stop then), "
                        "or on a simulator error; only a stop can succeed, and the state at the stop is what counts"),
            "action_types": {"skill": {
                "dim": 2, "layout": ["action_id", "value"],
                "lower": [0.0, -120.0], "upper": [7.0, 120.0],
                "actions": {
                    "0": "walk forward; value = stride in m: 0.2, 0.4 or 0.6 (nothing else)",
                    "1": "stop; value 0. Ends the episode: you declare you are done (only a stop can succeed)"
                         + "; POST /finish is the same stop",
                    "2": "turn in place; value = signed degrees, + left (counter-clockwise from above), - right; "
                         "|value| clamped to [10, 120]; 0 is refused",
                    "3": "climb up one step; value 0",
                    "4": "sit down; value = target pelvis height in m, clamped to [0.15, 0.85]",
                    "5": "step back; value = m, clamped to [0.10, 0.60]",
                    "6": "side step; value = signed m, + left, - right; |value| clamped to [0.10, 0.50]; 0 is refused",
                    "7": "walk down one step; value 0"},
                "units": "one row = one motion skill = one control step (control_dt); the body moves through it under "
                         "physics, so where it ends up is close to, not exactly, what was asked",
                "dtype": "values are rounded to 4 decimals; action_id must be a whole number 0-7",
                "semantics": "dt must be control_dt (a row cannot span several steps); interpolate is ignored; a "
                             "row that is invalid refuses the whole request (400) and nothing runs; clamped values "
                             "are reported in `clipped`. A hold chunk (/submit with no rows, interpolate \"hold\", "
                             "seconds n) lets n seconds pass with the body standing still: no action is used",
                "limit": f"{self.s.max_steps} actions per episode, the stop included; the {self.s.max_steps}th "
                         "action ends the episode whatever it is"}},
            "cameras": {"ego": {"mounted": "head, looking forward and slightly down", "hfov_deg": 90.0,
                                "hw": self.hw, "note": "the image after the last action (one per action)"}},
            "proprio": {"actions_used": "actions run so far this episode (stop included)",
                        "actions_left": "actions still allowed this episode",
                        "pelvis_rise_m": "how far the pelvis is above its height at the start, m (negative when "
                                         "lower, e.g. sitting)"},
        }

    def interpolable(self, typ: str) -> bool:
        return False

    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]:
        return {c: self.s.ego_rgb() for c in cameras}, {}

    def proprio(self) -> np.ndarray:
        n = self.s.n_actions
        return np.array([n, self.s.max_steps - n, self.s.pelvis_rise()], dtype=np.float32)

    def clip(self, typ: str, rows: np.ndarray) -> tuple[np.ndarray, list]:
        out, report = [], []
        for i, row in enumerate(np.asarray(rows, dtype=np.float64)):
            try:
                r, notes = hc_core.clip_row(row)
            except hc_core.BadAction as exc:
                raise Refused(400, {"error": f"row {i}: {exc}", "row": i, "nothing_ran": True}) from None
            out.append(r)
            report += [{"row": i, "index": 1, "reason": n} for n in notes]
        return np.asarray(out, dtype=np.float64), report

    def to_sim(self, typ: str, row: np.ndarray) -> np.ndarray:
        return np.asarray(row, dtype=np.float64)

    def command(self, typ: str) -> np.ndarray:
        return self.cmd

    def hold(self) -> tuple[str, np.ndarray]:
        return "skill", IDLE_ROW

    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]:
        if self.s.done:                  # (agent-ended: the stop after the episode's end is no action)
            return True, bool(self.s.result and self.s.result["success"]), {"step_cap": True}
        out = self.s.act(row)
        if int(row[0]) != hc_core.IDLE:
            self.cmd = np.asarray(row, dtype=np.float64)
            self.stopped = int(row[0]) == 1
        # agent-ended: the episode's end is HumanCLAW's own (a stop, or the 100th action), judged as it stands there
        return bool(out["done"]), bool(out["success"]), ({"step_cap": True} if out["done"] else {})

    stopped = False                      # the last action was a stop

    def reset(self) -> None:
        self.s.reset()
        self.cmd = IDLE_ROW.copy()
        self.stopped = False

    def state_sha(self) -> str:
        return self.s.state_sha()

    def live_verdict(self, rows: np.ndarray, success: bool) -> dict:
        """HumanCLAW's own record of the live episode (its paper metrics), for final.json."""
        r = self.s.result or {}
        s = (r.get("metrics") or {}).get("success") or {}
        return {"success": bool(r.get("success", False)) if success else False, "rule": r.get("rule"),
                "actions_used": int(self.s.n_actions), "ended_by_stop": bool(s.get("active_stop", False)),
                "final_body_target_aabb_distance_m": s.get("final_body_target_aabb_distance_m"),
                "n_sit": s.get("n_sit"), "geo_nav_sr_20cm": s.get("geo_nav_sr_20cm"),
                "geo_interact_sr": s.get("geo_interact_sr")}

    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None:
        rows = np.asarray(rows, dtype=np.float64).reshape(-1, 2)
        actions = rows[rows[:, 0] != hc_core.IDLE]
        np.savez(path, rows=rows, actions=actions.astype(np.float64),
                 meta=np.array(__import__("json").dumps(meta)))

    def render_video(self, rows: np.ndarray, path: str) -> None:
        rows = np.asarray(rows, dtype=np.float64).reshape(-1, 2)
        if int((rows[:, 0] != hc_core.IDLE).sum()) != self.s.n_actions:
            raise RuntimeError("the rows are not the live episode's")
        hc_core.episode_video(self.s, path)


# ---------------------------------------------------------------- agent-ended episodes: the finish is HumanCLAW's stop
_service_end = rcb_service.Service._end


def _agent_finish(self) -> dict:
    """POST /finish: the stop action, run as the episode's last control step (it ends the episode, judged there). The
    stop is a real step: a simulator error in it ends the episode as "error" and answers 500, as on every other call
    that ran (the layer's /finish route answers only Refused, so the error is handed to it as one with code 500)."""
    if self.done or self.stopping:
        raise self._conflict()
    self._closing = "finished"
    try:
        self._step("skill", STOP_ROW)
    except rcb_service.Refused:
        raise
    except Exception as exc:  # noqa: BLE001 -- it ran and failed: the episode ends, never a success
        traceback.print_exc()
        self.log("error", path="/finish", error=repr(exc)[:500])
        self._closing = None
        self._end("error")
        raise rcb_service.Refused(500, {"error": "simulator error", "detail": repr(exc)[:200]}) from None
    finally:
        self._closing = None
    if not self.done:                    # (HumanCLAW always ends at a stop; never left running)
        self._end("finished")
    return {"ok": True, **self.status()}


def _end(self, reason: str) -> None:
    """The end of the agent's session is a stop too (run first, then judged); an end HumanCLAW makes itself (a stop, the
    100th action) is "finished" when its last action was a stop, else "step_limit"."""
    if not self.done:
        if reason == "timeout" and not self.sim.s.done and not getattr(self, "_closing", None):
            self._closing = "timeout"
            try:
                self._step("skill", STOP_ROW)
            except Exception as exc:  # noqa: BLE001 -- a stop that fails: the episode ends as it stands (no success)
                self.log("stop_at_session_end_error", error=repr(exc)[:300])
            finally:
                self._closing = None
            if self.done:
                return
        elif reason == "step_limit" and self.sim.s.done:
            reason = getattr(self, "_closing", None) or ("finished" if self.sim.stopped else "step_limit")
    _service_end(self, reason)


rcb_service.Service._agent_finish = _agent_finish
rcb_service.Service._end = _end


def build() -> HumanClaw:
    env = os.environ.get
    return HumanClaw(env("RCB_INSTANCE", "/srv/instance.json"), task_text=env("RCB_TASK_TEXT", ""))


if __name__ == "__main__":
    main(build)
