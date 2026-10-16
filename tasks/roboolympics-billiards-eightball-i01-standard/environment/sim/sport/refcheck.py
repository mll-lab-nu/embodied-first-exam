"""tools/check stage 5 (sport.toml [reference] match = "refcheck:reference_match", docs/screening/README.md "Reference
check"): one match of billiards' reference against the scripted opponent, with truth or camera perception. A module of
its own because the reference player (builtin_players) imports no framework."""
import os

import builtin_players as bp


def reference_match(format="eightball", level=None, seed=1, perception="truth") -> dict:
    """tools/check stage 5 (sport.toml [reference] match): one match of the reference (platform skill only: the shot)
    against the scripted opponent of `level`, MatchConfig seed `seed` (its coin toss decides who breaks). perception
    "camera": the [players] reference unchanged, through core.local.play with the images; "truth": the same planner
    on the true positions. Returns {"won", "scores": [ours, theirs], "report"}: scores are the rack's progress of
    each side (its group's balls down, plus 1 for the winner; the numerator of ball_share), NOT Match.scores() (balls
    left, lower is better); report: legal shots and calls made of the reference."""
    from core import local
    from core.episode import load_plugin
    from core.sport import FINISHED, MatchConfig, Refused, parse_action
    plugin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.py")
    sport = load_plugin(plugin)
    cfg = MatchConfig(sport="billiards", format=format, seats=("A",), seed=int(seed), first="A", action_level="low",
                      level=None if level is None else int(level))
    if perception == "camera":
        res = local.play(sport, cfg, local.make_players(sport, cfg, {"A": "reference"}, plugin=plugin), render=True,
                         plugin=plugin)
        f = res["final_fields"]
        shots, won = f["shots"], res["winner"] == "A"
        left = (f["your_balls_left"], f["opponent_balls_left"])
    elif perception == "truth":
        m = sport.build(cfg)
        layer = sport.action_layer("low")
        from core import spec as spec_mod
        views = local.Views(sport, cfg, m, spec_mod.load(plugin), False, plugin)
        player = bp.TRUTH_PLAYERS["reference_truth"](local.seat_spec(sport, cfg, "A", plugin=plugin), "A", int(seed))
        refused = 0
        while m.phase().state != FINISHED:
            v = views.view("A", {"phase": "play", "turn": "you", "your_turn": True, "done": False})
            v["truth"] = dict(m.g.pos)
            try:
                cmd = parse_action(layer, "A", player.act(v), m, {"clock_left_s": {"A": 3600.0}})
            except Refused:
                refused += 1
                if refused > local.MAX_REFUSED:
                    raise
                continue
            m.apply("A", layer.lower("A", cmd, None, m)[0])
        shots, won = m.g.shots, m.g.winner == 0
        left = (m.balls_left(0), m.balls_left(1))
    else:
        raise ValueError(f"perception must be truth or camera, not {perception!r}")
    ours = [s for s in shots if s["player"] == 0 and not s["break"]]
    calls = [s for s in ours if s["call"] not in (None, "safety")]
    return {"won": bool(won), "scores": [7 - left[0] + int(won), 7 - left[1] + int(not won)],
            "report": {"legal shots": [sum(1 for s in ours if not s["foul"]), len(ours)],
                       "calls made": [sum(1 for s in calls if s["call_made"]), len(calls)]}}
