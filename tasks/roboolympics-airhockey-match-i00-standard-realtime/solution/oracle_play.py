"""Harbor oracle: the sport's RoboOlympics reference player (builtin_players.Reference, next to this file: camera images
and the documented facts only) driven through the agent's own client (rcb_client.py, eai-standard/2.3).

The reference players were written for RoboOlympics' realtime interface: each step they get a `view` -- the state
(score, the ball's clock, what was heard, the robot's own body) and a tiled PNG of the newest camera frames -- and
return an act body or nothing. This loop builds that view from /observe (a short watch: the frames and one proprio row
per frame), turns the act into a /submit row of the task's action type, and sends `ready` (with the player's review as
the note) once per break. Nothing here reads simulator state the agent could not read.

Timing (table tennis, badminton): the players also have an in-process mode in which an act takes effect exactly at the
observed step. 2.3's `at` makes that exact over HTTP too: the loop picks the control step its command will take effect
at (a margin of LEAD_STEPS after the step it estimates is running now), hands the player the view as of that step (the
step and the times relative to it shifted accordingly; images and frame steps are absolute), and submits the command
with `at` = that step. Host load then delays the command's arrival, never its effect.
"""
from __future__ import annotations

import base64
import io
import math
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import builtin_players as bp  # noqa: E402
from rcb_client import EpisodeOver, Robot  # noqa: E402

NAN = float("nan")
LEAD_STEPS = 5                    # control steps between "now" (estimated) and a command's planned effect: 0.5 s of wall
                                  # time at S = 10 for the player's own computation and the request


def num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def png_b64(rows: list) -> tuple[str, list]:
    """rows of tiles (one row per camera) -> base64 PNG and the tile list."""
    sheet = np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(sheet[..., :3])).save(buf, format="PNG", compress_level=1)
    return base64.b64encode(buf.getvalue()).decode(), []


class Bridge:
    def __init__(self):
        self.r = Robot()
        self.spec = self.r.spec()
        self.sport = self.spec["sport"]
        self.layout = self.spec["proprio_layout"]
        self.dt = float(self.spec["control_dt"])
        self.period = float(self.spec["timing"]["wall_s_per_control_step"])
        self.cams = list(self.spec["cameras"])
        rules = self.spec.get("rules") or {}
        cams = []
        for name in self.cams:
            c = dict(self.spec["cameras"][name], name=name)
            if self.sport == "airhockey":
                c.update(width=c["hw"][1], height=c["hw"][0])
            cams.append(c)
        self.exact = self.sport in ("tabletennis", "badminton")      # the in-process timing mode (module docstring)
        ref = {"cameras": cams, "action_level": self.spec["match"]["action_level"],
               "timing": {"period_s": None if self.exact else self.period}, **rules}
        self.player = bp.Reference(ref, "A", 0)
        self.reviewed_break = None
        self.n_obs = 0
        self.hist: list = []                 # (match step, proprio row, {cam: image}) of recent observations
        self.spacing = {"tabletennis": 4, "badminton": 6}.get(self.sport, 1)   # 40 / 60 ms, as RoboOlympics' views
        self.running = False
        # how often the loop looks (control steps): badminton at RoboOlympics' own client cadence (an observation, then
        # `wait 0.05`): a player that re-plans its stroke at every step keeps the arm from ever finishing a swing
        self.every = {"badminton": 5}.get(self.sport, 1)
        # badminton: a command waits `lead_steps` after its step (stroke_pending_effect_step shows it then); before
        # that it is still in the service's plan, which the proprio does not show: the loop marks it pending itself
        self.lead = int(((self.spec.get("rules") or {}).get("act") or {}).get("lead_steps", 0))
        self.pending_until = -1

    # ------------------------------------------------------------------ one view
    def rows(self, res) -> list[dict]:
        P = np.asarray(res.proprio, float).reshape(-1, len(self.layout))
        return [dict(zip(self.layout, map(float, row))) for row in P]

    def state(self, p: dict, shift: int = 0) -> dict:
        """The player's state as of `shift` control steps after the proprio row p (relative times shifted)."""
        p = dict(p)
        for k in ("t_since_played",):
            if k in p and not math.isnan(p[k]):
                p[k] += shift * self.dt
        for k in ("serve_opens_in_s", "serve_deadline_in_s", "stroke_contact_in_s"):
            if k in p and not math.isnan(p[k]):
                p[k] -= shift * self.dt
        if "serve_opens_in_s" in p and not math.isnan(p["serve_opens_in_s"]):
            p["serve_opens_in_s"] = max(0.0, p["serve_opens_in_s"])
        st = {"step": int(p["match_step"]) + shift, "world": "frozen" if p["break"] > 0.5 else "running",
              "done": p["finished"] > 0.5}
        if self.sport == "tabletennis":
            heard = [{"event": ev, "t": p[f"heard_{k}_t"]} for k, ev in
                     (("opp_bounce", "bounce on the opponent's half"), ("own_bounce", "bounce on your half"),
                      ("net", "net"), ("paddle", "paddle"), ("robot", "robot"), ("floor", "floor"))
                     if not math.isnan(p[f"heard_{k}_t"])]
            st.update(point=int(p["point"]), ball="serve" if p["ball_is_serve"] > 0.5 else "opponent's return",
                      t_since_played=p["t_since_played"], ball_in_play=p["ball_in_play"] > 0.5, heard=heard,
                      ball_state="coming to you" if p["ball_coming"] > 0.5 else
                      "going to the opponent" if p["ball_going"] > 0.5 else "dead")
        elif self.sport == "badminton":
            phase = {0: "waiting", 1: "open", 2: "tossed", 3: "done"}.get(int(p["serve_phase"]) if not
                                                                          math.isnan(p["serve_phase"]) else -1)
            sv = {"phase": phase, "court": "right" if p["serve_court_right"] > 0.5 else "left",
                  "opens_in_s": num(p["serve_opens_in_s"]), "deadline_in_s": num(p["serve_deadline_in_s"])}
            if not math.isnan(p["serve_tossed_at_step"]):
                sv["tossed_at_step"] = int(p["serve_tossed_at_step"])
            notes = "; ".join(n for n, k in (("head speed limited", "stroke_head_speed_limited"),
                                             ("pose not delivered", "stroke_pose_not_delivered")) if p[k] > 0.5)
            st.update(point=int(p["point"]), score={"you": int(p["score_you"]), "opponent": int(p["score_opponent"])},
                      you_serve=p["you_serve"] > 0.5, serve=sv, robot_base_xy=[p["base_x"], p["base_y"]],
                      t_since_played=num(p["t_since_played"]),
                      ball_state="coming to you" if p["ball_coming"] > 0.5 else
                      "going to the opponent" if p["ball_going"] > 0.5 else
                      "tossed: yours to hit (your serve)" if p["ball_tossed"] > 0.5 else
                      "not yet served" if p["ball_not_served"] > 0.5 else "dead")
            if p["stroke_active"] > 0.5:
                st["command"] = {"contact_in_s": p["stroke_contact_in_s"], "stroke": notes}
            if not math.isnan(p["stroke_pending_effect_step"]):
                st["pending_commands"] = [{"takes_effect_at_step": int(p["stroke_pending_effect_step"])}]
        else:
            st.update(rally=int(p["rally"]), t_play=p["t_play"],
                      own={"mallet_xyz": [p["mallet_x"], p["mallet_y"], p["mallet_z"]]})
        return st

    def observe(self):
        """Air hockey: watch 0.05 s (the players' cadence) and take the last image. Table tennis, badminton: the
        current images at once (the clock is started by a short watch first), kept in a history from which the view
        takes four frames about SPACING control steps apart, newest last, as RoboOlympics' observation did."""
        if self.sport == "airhockey":
            res = self.r.get_obs(cameras=self.cams, seconds=0.05, video="none")
            return res, self.rows(res), {c: res.last[c][None] for c in self.cams}
        res = self.r.get_obs(cameras=self.cams, seconds=0 if self.running else 0.05, video="frames")
        self.running = True
        rows = self.rows(res)
        k = int(rows[-1]["match_step"])
        if not self.hist or self.hist[-1][0] != k:
            self.hist.append((k, rows[-1], {c: res.frames[c][-1] for c in self.cams}))
            self.hist = self.hist[-40:]
        sel, last = [], None
        for k, row, fr in reversed(self.hist):
            if last is None or last - k >= self.spacing:
                sel.append((k, row, fr))
                last = k
            if len(sel) == 4:
                break
        sel.reverse()
        return res, [r for _, r, _ in sel], {c: np.stack([fr[c] for _, _, fr in sel]) for c in self.cams}

    def view(self, res, rows, frames, shift: int = 0) -> tuple[dict, dict, dict]:
        now = rows[-1]
        st = self.state(now, shift)
        n = min(len(rows), min(len(f) for f in frames.values()))
        rows, frames = rows[-n:], {c: f[-n:] for c, f in frames.items()}
        self.n_obs += 1
        ob = {"view_steps": [int(p["match_step"]) for p in rows],
              "view_sim_times": [round(p["match_step"] * self.dt, 4) for p in rows]}
        if not self.exact:
            ob.update(obs_id=self.n_obs, obs_age_wall_s=0.0, render_wall_s=0.0)
        if self.sport == "airhockey":
            img = frames[self.cams[0]][-1]
            ob["image_png_b64"], _ = png_b64([[img]])
            ob["tiles"] = [{"camera": self.cams[0], "x": 0, "y": 0, "width": img.shape[1], "height": img.shape[0]}]
        else:
            ob["image_png_b64"], _ = png_b64([[f for f in frames[c]] for c in self.cams])
        return st, ob, now

    # ------------------------------------------------------------------ one action
    def send(self, body: dict, at=None) -> None:
        t = body.get("type")
        if t == "act":
            row = [body["t"], *body["pos"], *body["normal"], *body["vel"]]
            self.r.submit("stroke", [row], at=at)
        elif t == "toss":
            self.r.submit("toss", [[*body["pos"], float(body.get("height", 0.0))]], at=at)
        elif t == "target":
            self.r.submit("mallet", [[body["x"], body["y"]]], at=at)
        elif t == "none":
            self.r.submit("stop" if self.sport == "airhockey" else "rest", [[0.0]], at=at)

    def run(self) -> dict:
        t_last = 0.0
        while True:
            time.sleep(max(0.0, t_last + self.every * self.period - time.monotonic()))   # one view per `every` steps
            t_last = time.monotonic()
            try:
                res, rows, frames = self.observe()
            except EpisodeOver:
                break
            t_reply = time.monotonic()
            if res.meta.get("done"):
                break
            at = shift = None
            if self.exact:                     # the step the command will take effect at, and the view as of then
                at = math.ceil(res.meta["control_steps"] + 0.5) + LEAD_STEPS
                at = max(at, math.ceil(res.meta["control_steps"] + (time.monotonic() - t_reply) / self.period)
                         + LEAD_STEPS)
                shift = at - int(res.meta["control_steps"])
            st, ob, now = self.view(res, rows, frames, shift or 0)
            if st["world"] == "frozen":
                key = int(now["match_step"])            # the match stands still in a break: one key per break
                if key != self.reviewed_break:
                    self.reviewed_break = key
                    f = getattr(self.player, "review", None)
                    why, plan = f(now) if f else ("played as planned", "same plan")
                    try:
                        self.r.submit("ready", [[1.0]], note=f"WHY: {why} PLAN: {plan}"[:200])
                    except EpisodeOver:
                        break
                continue
            if self.sport == "badminton" and res.meta["control_steps"] <= self.pending_until:
                st["pending_commands"] = [{"takes_effect_at_step": int(now["match_step"]) + self.pending_until
                                           - int(res.meta["control_steps"]) + 1}]
            body = self.player.act({"state": st, "observation": ob})
            if body:
                if at is not None:
                    self.pending_until = at + self.lead
                try:
                    self.send(body, at)
                except EpisodeOver:
                    break
        return self.r.status()


if __name__ == "__main__":
    t0 = time.time()
    out = Bridge().run()
    print({"status": out, "wall_s": round(time.time() - t0, 1)})
