"""The reference check of tools/check stage 5 (docs/screening/README.md "Reference check", sport.toml [reference]):
one match-wallclock match of the reference (builtin_players.Reference) against the scripted opponent at a level,
played the way the step-4 screening plays it (docs/screening/badminton/scr.py over
docs/benchmarks/badminton-minicourt-20261008/study.py), so that its results are those of the screening record:

  the loop      high action level, x20; every 5 control steps the player observes and may act; an act is parsed,
                planned from the snapshot of its arrival step and lowered at once (core/local.py's realtime loop)
  perception    "camera": the reference unchanged (the 8 tiles of the two cameras, its own detection); "truth": the
                same player given the shuttle's true position at the tiles' times + 3 mm noise (no images drawn)

Returns {"won", "scores": [ours, theirs], "perception", "report": {"legal_returns": [returned, rally shots], "velocity_reflexes": [reflexes, rally shots]}}.
"""
from __future__ import annotations

import base64
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EVERY = 5
MAX_STEPS = 80000
NOISE = 0.003


def reference_match(format: str = "match-wallclock", level: int | None = 1, seed: int = 1,
                    perception: str = "truth") -> dict:
    if perception not in ("truth", "camera"):
        raise ValueError(f"perception must be truth or camera, not {perception!r}")
    if format != "match-wallclock":
        raise ValueError("the opponent calibration is for format match-wallclock (the scripted opponent)")
    for p in (HERE, os.path.join(HERE, "sim")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import bduel as BD
    import builtin_players as BP
    import plugin as PL
    from core.sport import FINISHED, UNIT_OVER, MatchConfig, Refused

    cfg = MatchConfig(sport="badminton", format="match-wallclock", seats=("A",), seed=int(seed),
                      level=1 if level is None else int(level), slowdown=20.0)
    m = PL.SPORT.build(cfg)
    layer = PL.SPORT.action_layer("high")
    spec = {"seat": "A", "action_level": "high", **PL.SPORT.spec(cfg, "A", m)}
    cur = {"obs": None}
    real_decode, real_detect = BP.decode, BP.detect_views

    def decode(b):
        return b if cur["obs"] is not None else real_decode(b)

    def detect_views(img, cams, times, max_res=0.12):
        if cur["obs"] is None:
            return real_detect(img, cams, times, max_res)
        ts = {round(float(t), 4) for t in times}
        return [(t, X) for t, X in cur["obs"] if round(float(t), 4) in ts]

    player = BP.Reference(spec, "A", int(seed))

    def perceive():
        job, meta = m.camera_job("A")
        if perception == "camera":
            png = PL.SPORT.worker_call(None, "render", job)["png"]
            return {**meta, "image_png_b64": base64.b64encode(png).decode()}, None
        obs = []
        for sn, t in zip(job["snaps"], meta["view_sim_times"]):
            X = BD.to_side("A", sn["sh"])
            if X[2] < -0.1:
                continue
            g = np.random.default_rng([int(seed), ord("A"), int(sn["k"])])
            obs.append((float(t), X + g.normal(0.0, NOISE, 3)))
        return {**meta, "image_png_b64": "eA=="}, obs

    BP.decode, BP.detect_views = decode, detect_views
    try:
        while m.phase().state != FINISHED and m.k < MAX_STEPS:
            if m.phase().state == UNIT_OVER:
                m.resume()
            if m.k % EVERY == 0:
                st = {"seat": "A", "phase": "running", "world": "running", "step": m.k, "t_sim": m.k * m.dt,
                      "done": False, **m.observe("A")}
                ob, cur["obs"] = perceive()
                try:
                    body = player.act({"state": st, "observation": ob})
                finally:
                    cur["obs"] = None
                if body is not None:
                    try:
                        cmd = layer.parse("A", body, m, {})
                        job = layer.snapshot("A", cmd, m, m.k)
                        prepared = layer.prepare(job) if job is not None else None
                        low, info = layer.lower("A", cmd, prepared, m)
                        m.apply("A", low)
                    except Refused:
                        pass
            m.step()
    finally:
        BP.decode, BP.detect_views = real_decode, real_detect
    g = m.g
    rally = [r for r in g.results if r["kind"] != "our_serve"]
    return {"won": g.winner == 0, "scores": [int(g.score[0]), int(g.score[1])],
            "perception": perception,      # a real truth variant (tools/check stage 5: not a camera stand-in)
            "report": {"legal_returns": [sum(bool(r.get("returned")) for r in rally), len(rally)],
                       "velocity_reflexes": [int(g.s.n_reflex), len(rally)]}}   # {name: [count, of]}: reflexes per rally shot
