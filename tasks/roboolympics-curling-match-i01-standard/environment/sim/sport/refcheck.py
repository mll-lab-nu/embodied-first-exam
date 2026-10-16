"""tools/check stage 5, the reference check (docs/screening/README.md "Reference check"): one match of the built-in
reference player (builtin_players.Reference) against the scripted team, in process, as the live turn service plays it:
the observation's camera images for its act(), and after every throw that does not end the match its review() gets
the reply with the reply image of its own stone at rest (Match.reply_views, drawn by the task's renderer).

  perception "camera"  the player unchanged (camera images only)
  perception "truth"   the same player with its perception replaced by the true state: the stones of the sheet when
                       it acts, and the stones at rest right after its throw (what the reply image shows) when it
                       reviews; no image is drawn

sport.toml [reference] match = "refcheck:reference_match". Runs in the sport's image with the simulator directory.
"""
from __future__ import annotations

import os

from core import local
from core.episode import load_plugin
from core.observe import CameraWorker, players_scene, reply_job
from core.outcome import decide
from core.sport import FINISHED, MatchConfig, parse_action

import builtin_players as B

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.py")
CLOCK_S = 3600.0
N_STONES = 5


class Truth(B.Reference):
    """The reference with true perception: an observation carrying `_stones` is read as those stones."""

    def see(self, obs):
        return list(obs["_stones"]) if "_stones" in obs else super().see(obs)


def _stones(state):
    """[(x, y, colour)] of a render state (CurlingMatch.render_state: stone id < 5 is the yellow team's, unused slots
    wait off the sheet at y = -20)."""
    return [(p[0], p[1], "yellow" if i < N_STONES else "red") for i, p in enumerate(state["mocap_pos"]) if p[1] > 0.0]


def reference_match(format="match", level=None, seed=1, perception="camera"):
    sport = load_plugin(PLUGIN)
    from core import spec as spec_mod
    decl = spec_mod.load(PLUGIN)
    cfg = MatchConfig(sport="curling", format=format, seats=("A",), seed=int(seed), first="A", action_level="low",
                      **({"level": int(level)} if level is not None else {}))
    truth = perception == "truth"
    m = sport.build(cfg)
    layer = sport.action_layer("low")
    views = local.Views(sport, cfg, m, decl, not truth, PLUGIN)
    p = (Truth if truth else B.Reference)(local.seat_spec(sport, cfg, "A", plugin=PLUGIN), "A", int(seed))
    cam = None
    rep = {"throws": 0, "fgz": 0, "fits": 0}
    while m.phase().state != FINISHED:
        v = views.view("A", {"phase": "play", "turn": "you", "your_turn": True, "awaiting_review": False,
                             "done": False, "clock_left_s": CLOCK_S})
        if truth:
            v["observation"] = {"_stones": _stones(m.render_state())}
        cmd = parse_action(layer, "A", p.act(v), m, {"clock_left_s": {"A": CLOCK_S}})
        low, info = layer.lower("A", cmd, None, m)
        applied = m.apply("A", low) or {}
        rep["throws"] += 1
        rep["fgz"] += bool(applied["rec"].get("fgz_violation"))
        if m.phase().state == FINISHED:
            break
        reply = layer.reply("A", cmd, {**applied, **info}, m)
        if truth:
            reply["observation"] = {"image_png_b64": "-", "tiles": [{"camera": "house"}],
                                    "_stones": _stones(applied["after"])}
        else:
            job = reply_job(m, m.reply_views("A", low, applied), views.columns)
            if cam is None:
                cam = CameraWorker(players_scene(sport, PLUGIN, cfg), cfg.renderer)
            img = cam.draw_job(job)
            reply["observation"] = {"image_png_b64": __import__("base64").b64encode(img["png"]).decode(),
                                    "tiles": img["tiles"]}
        p.review(reply)
    oc = decide(m, None, None, cfg.side_list(), cfg.side_of)
    sc = m.scores()
    kd = m.g.kd
    return {"won": oc.winner == "A", "scores": [sc["A"], sc["opponent"]],
            "report": {"throws without a free guard zone violation": [rep["throws"] - rep["fgz"], rep["throws"]],
                       "ice estimate within 0.01 of kd": [int(abs(p.ice.kd - kd) <= 0.01), 1],
                       "throws used to learn the ice": [len(p.ice.fits), rep["throws"]]}}
