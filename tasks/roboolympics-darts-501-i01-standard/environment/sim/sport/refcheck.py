"""tools/check stage 5 (sport.toml [reference] match = "refcheck:reference_match", docs/screening/README.md "Reference
check"): one match of darts' reference against the scripted thrower of format 501, with truth or camera perception.
A module of its own because the reference player (builtin_players) imports no framework; screen/hooks.py uses
TruthFeed for its truth variants too.

  camera  the [players] reference unchanged: it finds its darts in the board close-up of each dart's reply (review,
          as over HTTP: core/client.py) and of the observation
  truth   the same player with the images replaced by its true landing points plus the image measurement error
          (N(0, 1 mm) per axis: the reference's location error in the board close-up was 1.0 / 0.9 mm rms, 36 darts,
          docs/screening/darts.md section 6), of every dart of its own that hit the board, before its next dart
"""
import os

import numpy as np

import builtin_players as bp

LOC_M = 0.001                   # 1 sigma per axis of the measured landing point (truth perception)
NOISE_STREAM = 31337            # the measurement noise: numpy default_rng([seed, NOISE_STREAM])


class TruthFeed:
    """Feeds a reference-like player (update(cmd, uv)) the measured landing points of its own darts: the true point
    plus N(0, loc) per axis, in the order of the darts, every dart that hit the board once."""

    def __init__(self, seed, stream=NOISE_STREAM, loc=LOC_M):
        self.rng = np.random.default_rng([int(seed), int(stream)])
        self.loc, self.done = float(loc), 0

    @staticmethod
    def own(m, seat):
        """The dart records of `seat` in the plugin match `m` (format 501: thrower 0; duel: the seat)."""
        return [r for r in m.d.log if (r.get("seat") == seat if "seat" in r else r["who"] == 0)]

    @staticmethod
    def wanted(r):
        """A dart the player measures: every one on the board (a dart that missed the board is not shown)."""
        return r["hit"] == "board"

    def feed(self, player, m, seat):
        recs = self.own(m, seat)
        for r in recs[self.done:]:
            if self.wanted(r):
                uv = (r["u"] + self.loc * self.rng.standard_normal(), r["v"] + self.loc * self.rng.standard_normal())
                player.update(tuple(r["cmd"]), uv)
        self.done = len(recs)


def reference_match(format="501", level=None, seed=1, perception="truth") -> dict:
    """One match of the reference against the scripted thrower of `level` (format 501), MatchConfig seed `seed`.
    Returns {"won", "scores": [our legs, its legs], "report": {"darts measured": [measured, own darts on the board],
    "darts on the board": [own darts on the board, own darts]}}."""
    import base64

    from core import local
    from core import spec as spec_mod
    from core.episode import load_plugin
    from core.observe import CameraWorker, players_scene, reply_job
    from core.sport import FINISHED, MatchConfig, Refused, parse_action
    if perception not in ("truth", "camera"):
        raise ValueError(f"perception must be truth or camera, not {perception!r}")
    plugin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.py")
    sport = load_plugin(plugin)
    cfg = MatchConfig(sport="darts", format=format, seats=("A",), seed=int(seed), first="A", action_level="low",
                      level=None if level is None else int(level))
    m = sport.build(cfg)
    layer = sport.action_layer("low")
    camera = perception == "camera"
    views = local.Views(sport, cfg, m, spec_mod.load(plugin), camera, plugin)
    player = bp.Reference(local.seat_spec(sport, cfg, "A", plugin=plugin), "A", int(seed))
    feed = None if camera else TruthFeed(seed)
    clock = {"A": local.DEFAULT_CLOCK_S}
    refused = 0
    while m.phase().state != FINISHED:
        if feed is not None:
            feed.feed(player, m, "A")
        views.render = camera
        v = views.view("A", {"phase": "play", "turn": "you", "your_turn": True, "done": False,
                             "clock_left_s": clock["A"]})
        try:
            cmd = parse_action(layer, "A", player.act(v), m, {"clock_left_s": dict(clock)})
        except Refused:
            refused += 1
            if refused > local.MAX_REFUSED:
                raise
            continue
        low, info = layer.lower("A", cmd, None, m)
        applied = m.apply("A", low) or {}
        if m.phase().state == FINISHED or not camera:
            continue
        job = reply_job(m, m.reply_views("A", low, applied), views.columns)     # the reply, as core/turn.py sends it
        if views.cam is None:
            views.cam = CameraWorker(players_scene(sport, plugin, cfg), cfg.renderer)
        img = views.cam.draw_job(job)
        views.render = False
        reply = {**layer.reply("A", cmd, {**applied, **info}, m),
                 "state": views.view("A", {"phase": "play", "turn": "review", "your_turn": True,
                                           "awaiting_review": True, "done": False})["state"],
                 "observation": {"of": "the result of this action", "tiles": img.get("tiles"),
                                 "image_png_b64": base64.b64encode(img["png"]).decode()}}
        player.review(reply)
    own = TruthFeed.own(m, "A")
    on_board = sum(1 for r in own if r["hit"] == "board")
    return {"won": bool(m.d.winner == 0), "scores": [int(m.d.legs[0]), int(m.d.legs[1])],
            "report": {"darts measured": [player.n, on_board], "darts on the board": [on_board, len(own)]}}
