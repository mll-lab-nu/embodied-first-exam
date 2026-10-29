"""eai-standard/2.1 sim service for HumanCLAW -- the standard-mode sidecar's entry point (`python /srv/server.py`).

The simulator-specific half only: `HumanClaw` implements rcb_service.Sim for one frozen episode (hc_core.Session).
The protocol, the episode, crash recovery and the finalize live in rcb_service.py, which imports no simulator.
One action type, `skill`: a row is [action_id, value], one HumanCLAW motion skill, one control step (control_dt =
0.5 s, the 15 frames at 30 Hz a skill moves). The verdict is the live episode's: step() reports HumanCLAW's own rule
(hc_core.Session._finish, at the stop or the last allowed action) and the episode ends there; nothing is replayed to
grade it. The video is the live episode's recorded poses, rendered after the verdict (hc_core.episode_video).
Settings come from environment/docker-compose.yaml:
  RCB_INSTANCE      the frozen episode (the privileged twin's instance.json)
  RCB_TASK_TEXT     one sentence for /spec
  RCB_EPISODE       what ends an episode, for /spec (the instruction's words)
  RCB_RESET_BUDGET, RCB_WALL_CLOCK_S, RCB_DATA   the service's own (rcb_service.main)
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hc_core  # noqa: E402
from rcb_service import InstanceMismatch, Refused, main  # noqa: E402

IDLE_ROW = np.array([hc_core.IDLE, 0.0], dtype=np.float64)
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

    def __init__(self, instance: str, *, task_text: str = "", episode: str = ""):
        self.inst = hc_core.load_instance(instance)
        if self.inst.get("digest") and self.inst["digest"] != hc_core.instance_digest(self.inst):
            raise InstanceMismatch(f"{instance} records digest {self.inst['digest']}, its contents hash to "
                                   f"{hc_core.instance_digest(self.inst)}")
        self.s = hc_core.Session(self.inst)
        if self.inst.get("start_sha"):
            self.start_sha = self.inst["start_sha"]
        self.task_text, self.episode = task_text, episode
        self.cmd = IDLE_ROW.copy()
        self.hw = list(self.s.ego_rgb().shape[:2])

    # ------------------------------------------------------------------ the rcb_service.Sim contract
    def spec(self) -> dict:
        return {
            "simulator": "habitat-sim with HumanCLAW Half-Physics (Bullet), MotionDiT motion skills",
            "robot": "a simulated adult human body (SMPL-X neutral body), moved only by its motion skills",
            "task_text": self.task_text, "episode": self.episode,
            "action_types": {"skill": {
                "dim": 2, "layout": ["action_id", "value"],
                "lower": [0.0, -120.0], "upper": [7.0, 120.0],
                "actions": {
                    "0": "walk forward; value = stride in m: 0.2, 0.4 or 0.6 (nothing else)",
                    "1": "stop; value 0. Ends the episode: you declare you are done (only a stop can succeed)",
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
                             "are reported in `clipped`. /observe with seconds > 0 lets time pass with the body "
                             "standing still: no action is used",
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
        out = self.s.act(row)
        if int(row[0]) != hc_core.IDLE:
            self.cmd = np.asarray(row, dtype=np.float64)
        return bool(out["done"]), bool(out["success"]), {}

    def reset(self) -> None:
        self.s.reset()
        self.cmd = IDLE_ROW.copy()

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


def build() -> HumanClaw:
    env = os.environ.get
    return HumanClaw(env("RCB_INSTANCE", "/srv/instance.json"), task_text=env("RCB_TASK_TEXT", ""),
                     episode=env("RCB_EPISODE", ""))


if __name__ == "__main__":
    main(build)
