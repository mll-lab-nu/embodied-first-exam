"""Spectator broadcast log: an append-only, compact record of what a broadcast camera needs to draw the match.

The sim service appends one line per drawn frame (every EVERY control steps of game time, plus the last state of every
point) and one line per match event (start, run, point, review pause, end) to /data/broadcast.jsonl. A renderer OUTSIDE
the sim (scripts/olympiad/broadcast.py) tails the file, rebuilds the MuJoCo state from the same scene and draws the
broadcast camera. Nothing in the sim reads this file back: the replay, the grader and the match result do not depend on
it, and any failure here only switches the log off (`RCB_BROADCAST=0` switches it off from the start).

Lines (JSON, one per line):
  {"ev": "hdr", "sport": ..., "mode": "single"|"duel", "slowdown": S, "dt": control step s, "every": n, ...}
  {"k": step, "q": [qpos ...], ...extra}            a frame (extra: per-sport fields the drawing needs, e.g. "o")
  {"ev": "point"|"run"|"pause"|"end"|..., "k": step, ...}
"""
from __future__ import annotations

import json
import os
import time

PATH = os.path.join(os.environ.get("RCB_DATA", "/data"), "broadcast.jsonl")


class BroadcastLog:
    def __init__(self, every: int = 2, digits: int = 5, path: str = PATH, **header):
        self.every = max(1, int(every))
        self.fmt = f"{{:.{int(digits)}f}}"
        self.f = None
        self.last_k = None
        if os.environ.get("RCB_BROADCAST", "1") != "1":
            return
        try:
            self.f = open(path, "a", buffering=1 << 16)
            self._write(json.dumps({"ev": "hdr", "ts": round(time.time(), 3), "every": self.every, **header}))
        except Exception:  # noqa: BLE001  (spectator output only: never disturb the match)
            self.f = None

    def _write(self, line: str) -> None:
        if self.f is None:
            return
        try:
            self.f.write(line + "\n")
            self.f.flush()
        except Exception:  # noqa: BLE001
            self.f = None

    def frame(self, k: int, q, force: bool = False, **extra) -> None:
        """One drawn frame at control step k (only every `every` steps unless forced; never twice for one step)."""
        if self.f is None or k == self.last_k or (not force and k % self.every):
            return
        self.last_k = k
        try:
            fmt = self.fmt.format
            s = '{"k":%d,"q":[%s]' % (k, ",".join(fmt(float(x)) for x in q))
            for key, v in extra.items():
                s += ',"%s":%s' % (key, json.dumps(v if not isinstance(v, float) else round(v, 5)))
            self._write(s + "}")
        except Exception:  # noqa: BLE001
            self.f = None

    SKIP = ("k", "t", "leg_id", "wall_mono", "qpos", "point", "played_k", "flight")

    def snapshot(self, sn: dict, force: bool = False) -> None:
        """A frame from one of the sim's own camera snapshots (the dict its Match.step() keeps for the views: k,
        qpos and whatever else the sport draws, e.g. the ball "b" and the opponent "opp")."""
        if self.f is None or sn is None:
            return
        try:
            extra = {}
            for key, v in sn.items():
                if key in self.SKIP or v is None:
                    continue
                if hasattr(v, "tolist"):
                    v = v.tolist()
                if isinstance(v, (list, tuple)):
                    v = [round(float(x), 5) if isinstance(x, float) else x for x in v]
                elif isinstance(v, float):
                    v = round(v, 5)
                extra[key] = v
            self.frame(int(sn["k"]), sn["qpos"] if sn.get("qpos") is not None else (), force=force, **extra)
        except Exception:  # noqa: BLE001
            self.f = None

    def after_step(self, game, point_ended: bool = False) -> None:
        """After a control step of a match object that keeps camera snapshots in `hist` (and the ended point's in
        `review_hist`): log the newest snapshot; when a point just ended, the point's last snapshot (the new point's
        reset state is not shown as the end of the old one)."""
        if self.f is None:
            return
        try:
            if point_ended:
                rh = getattr(game, "review_hist", None)
                if rh:
                    self.snapshot(rh[-1], force=True)
                return
            h = game.hist[-1] if game.hist else None
            if h is not None and h["k"] == game.k:
                self.snapshot(h)
        except Exception:  # noqa: BLE001
            self.f = None

    def event(self, ev: str, k: int, **fields) -> None:
        if self.f is None:
            return
        try:
            self._write(json.dumps({"ev": ev, "k": int(k), "ts": round(time.time(), 3), **fields}, default=_plain))
        except Exception:  # noqa: BLE001
            self.f = None


def pitch_frame(bc, rt) -> None:
    """Baseball (bbrt.RT / bbduel.Duel): a frame from the pitch clock's own display data (its newest camera snapshot:
    the ball, the swing's parameters and the time since release), every `every` steps of the pitch."""
    if bc is None or bc.f is None or rt.n % bc.every:
        return
    try:
        sn = rt.snapshots()[-1]
        bc.frame(int(sn["k"]), (), force=True, ball=[round(float(x), 4) for x in sn["ball"]],
                 sw=None if sn["swing"] is None else [round(float(x), 5) for x in sn["swing"]], t=round(sn["t"], 4),
                 p=int(sn["pitch"]))
    except Exception:  # noqa: BLE001
        bc.f = None


def flight(samples, step: float = 0.04, t_max: float = 8.0) -> list:
    """A batted ball's flight (bb.judge_batted samples: (t, x, y, z, ...)) every `step` s, for the replay."""
    out, nxt = [], 0.0
    for sm in samples or ():
        if sm[0] >= nxt - 1e-9 and sm[0] <= t_max:
            out.append([round(float(sm[0]), 3)] + [round(float(x), 3) for x in sm[1:4]])
            nxt = sm[0] + step
    if samples and (not out or out[-1][0] < samples[-1][0]) and samples[-1][0] <= t_max:
        out.append([round(float(samples[-1][0]), 3)] + [round(float(x), 3) for x in samples[-1][1:4]])
    return out


def _plain(x):
    try:
        return x.tolist()
    except AttributeError:
        return str(x)
