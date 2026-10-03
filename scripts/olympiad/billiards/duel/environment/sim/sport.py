"""8-ball for the turn-based duel service (server_duel.py): the sport-specific part (game state, action, views)."""
from __future__ import annotations

import base64
import math

import numpy as np

import duel_core as D
import eightball as E8
import render

NAME = "8-ball"
REVISION = D.REVISION
FIRST_MEANING = "FIRST_PLAYER breaks (cue ball in hand above the head string, y < L/4)"
_VIEWS: dict = {}


def warm() -> None:
    E8.simulate({"cue": (0.3, 0.3), "1": (0.3, 0.8)}, 90.0, 1.0, 0.0, 0.0)     # warm the JIT


def new(seed: int, first: str) -> D.Duel:
    return D.Duel(seed, first)


def validate(body: dict, g: D.Duel = None, seat: str = None) -> dict | str:
    if body.get("type", "shoot") != "shoot":
        return "the action is: shoot AIM_DEG SPEED [SPIN_X SPIN_Y] [cue=X,Y] [call=BALL:POCKET|safety]"
    try:
        phi = float(body["aim_deg"]); V = float(body["speed"])
        a = float(body.get("spin_x", 0.0)); b = float(body.get("spin_y", 0.0))
        cue = None
        if body.get("cue_x") is not None or body.get("cue_y") is not None:
            cue = [float(body["cue_x"]), float(body["cue_y"])]
        call = body.get("call")
        call = None if call in (None, "") else str(call)
    except Exception:  # noqa: BLE001
        return "shoot needs aim_deg, speed and optionally spin_x, spin_y, cue_x and cue_y (numbers), call (BALL:POCKET or safety)"
    if not all(math.isfinite(x) for x in (phi, V, a, b)):
        return "numbers must be finite"
    if not (E8.V_RANGE[0] <= V <= E8.V_RANGE[1]):
        return f"speed must be in [{E8.V_RANGE[0]}, {E8.V_RANGE[1]}] m/s"
    if math.hypot(a, b) > E8.SPIN_MAX:
        return f"tip offset too far from centre: sqrt(spin_x^2 + spin_y^2) must be <= {E8.SPIN_MAX} (a miscue)"
    dec = {"type": "shoot", "aim_deg": phi % 360.0, "speed": V, "spin_x": a, "spin_y": b}
    if cue is not None:
        dec["cue_xy"] = cue
    if call is not None:
        dec["call"] = call
    return (g.check(seat, dec) if g is not None else None) or dec


def play(g: D.Duel, seat: str, dec: dict) -> list[dict]:
    return [dict(g.play(seat, dec), player=seat)]


def _who(x, seat):
    return "you" if x == seat else "opponent"


def shot_text(s: dict, seat: str) -> dict:
    o = {"player": _who(s["player"], seat), "break": s["break"], "first_hit": s["first_hit"], "potted": s["potted"],
         "pockets": s["pockets"], "foul": s["foul"], "cue_ball_pocketed": s["cue_ball_pocketed"],
         "keeps_turn": s["keeps_turn"]}
    if s["call"]:
        o["call"], o["call_made"] = s["call"], s["call_made"]
    if s["cue_placed_at"]:
        o["cue_placed_at"] = s["cue_placed_at"]
    if s["eight_respotted"]:
        o["eight_respotted"] = "the 8 was potted on the break and spotted again on the foot spot"
    if s["group_assigned"]:
        g = s["group_assigned"]
        o["groups_assigned"] = {_who(s["player"], seat): g, _who(D.OTHER[s["player"]], seat): E8.OTHER_GROUP[g]}
    if s["game_over"]:
        o["game_over"] = s["result"]
    if s["player"] == seat:
        o["your_shot"] = s["requested"]
    return o


def scores(g: D.Duel) -> dict:
    """Balls left in each player's group (7 while the table is open)."""
    return {s: g.balls_left(s) for s in D.SIDES}


def score_view(g: D.Duel, seat: str) -> dict:
    p, q = D.SIDES.index(seat), 1 - D.SIDES.index(seat)
    o = {"your_group": g.g.group_name(p), "opponent_group": g.g.group_name(q),
         "your_balls_left": g.balls_left(seat), "opponent_balls_left": g.balls_left(D.OTHER[seat]),
         "your_shots": g.g.n_shots[p], "max_shots": E8.MAX_SHOTS}
    if not g.done and g.turn == seat:
        o.update(break_shot=not g.g.break_done,
                 ball_in_hand={None: None, "kitchen": "above the head string (y < L/4)",
                               "anywhere": "anywhere"}[g.g.ball_in_hand],
                 on_the_8=g.g.on_the_8(p), call_required=g.g.must_call(p))
    if g.done:
        o["result"] = g.g.result
    return o


def observation(g: D.Duel, seat: str, query: dict) -> dict:
    aim = query.get("aim")
    pos = g.g.pos
    phi = render.default_sight_phi(pos) if aim is None else float(aim) % 360.0
    key = (g.g.k, round(phi, 3))
    if key not in _VIEWS:
        if len(_VIEWS) > 16:
            _VIEWS.clear()
        v = render.views(pos, phi)
        _VIEWS[key] = {"images_png_b64": {"top": base64.b64encode(v["top"]).decode(),
                                          "sight": base64.b64encode(v["sight"]).decode()},
                       "sight_aim_deg": round(phi, 3), "cameras": v["cameras"]}
    return {"shot_number": g.g.k + 1, "balls_on_table": g.g.objects_left(), "cue_ball_on_table": "cue" in pos,
            **_VIEWS[key]}


def parse_query(body: dict) -> dict:
    """The observe body: {"aim": DEG} (optional)."""
    out = {}
    if body.get("aim") is not None:
        aim = float(body["aim"])
        if not math.isfinite(aim):
            raise ValueError("aim must be a finite number (degrees)")
        out["aim"] = aim
    return out


def spec(seat: str, first: str) -> dict:
    return {
        "simulator": "pooltool 0.6.0 (event-based billiards physics)",
        "rules": "WPA Rules of Play, effective 2025-09-15, 8-Ball (with the deviations listed in the instructions)",
        "match": {"type": "8-ball, one rack", "first_player": first, "you_break": seat == first,
                 "solids": list(E8.SOLIDS), "stripes": list(E8.STRIPES), "max_shots_each": E8.MAX_SHOTS},
        "action": {"shoot": {"aim_deg": "cue direction in the table plane, degrees counter-clockwise from +x",
                             "speed": f"cue stick speed at impact, m/s, in [{E8.V_RANGE[0]}, {E8.V_RANGE[1]}]",
                             "spin_x, spin_y": f"tip offset in ball radii, sqrt(x^2+y^2) <= {E8.SPIN_MAX}",
                             "cue_x, cue_y": "ball in hand only: where to place the cue ball first (optional)",
                             "call": (f"every shot after the break (not the break): BALL:POCKET with a ball you may hit first and a pocket "
                                      f"of {list(E8.POCKET_IDS)}, e.g. 3:rc or 8:lt; or safety")},
                   "execution_scatter_sigma": E8.EXEC_SIGMA},
        "table": {"playing_surface": {"x": [0.0, round(E8.W, 4)], "y": [0.0, round(E8.L, 4)]}, "ball_radius": E8.R,
                  "cloth_z": 0.0, "ball_centre_z": E8.R,
                  "pockets": {k: {"centre_xy": [round(float(c[0]), 4), round(float(c[1]), 4)],
                                  "radius": float(E8.TABLE.pockets[k].radius), "where": E8.POCKET_NAMES[k]}
                              for k, c in E8.POCKETS.items()},
                  "head_spot": [round(E8.HEAD_SPOT[0], 4), round(E8.HEAD_SPOT[1], 4)],
                  "foot_spot": [round(E8.FOOT_SPOT[0], 4), round(E8.FOOT_SPOT[1], 4)],
                  "head_string_y": round(E8.HEAD_STRING_Y, 4)},
        "cameras": {"top": render.camera_info(render.top_camera(), "top"),
                    "sight": {"eye": "0.75 m behind the cue ball centre along -aim, 0.32 m above the cloth",
                              "looks_at": "the cloth 1.0 m ahead of the cue ball along the aim",
                              "image_px": list(render.SIGHT["size"]), "fx": render.SIGHT["f"], "fy": render.SIGHT["f"],
                              "note": "its exact pose for each image is in the observation's `cameras`"}},
    }


def actions_array(decisions: list[dict]) -> dict:
    """trajectory.npz content: per shot the seat (0 = A, 1 = B) and aim_deg, speed, spin_x, spin_y, cue_x, cue_y (NaN:
    no placement), the call: ball (-1: none, 0: safety) and pocket (index into POCKET_IDS, -1: none)."""
    return {"seat": np.array([D.SIDES.index(d["seat"]) for d in decisions], dtype=np.int64),
            "actions": np.array([[d["aim_deg"], d["speed"], d["spin_x"], d["spin_y"],
                                  *(d["cue_xy"] if d.get("cue_xy") is not None else (np.nan, np.nan)),
                                  *_call_cols(d.get("call"))] for d in decisions],
                                dtype=np.float64).reshape(-1, 8)}


def _call_cols(call):
    c = None if call is None else E8.parse_call(call)
    if c is None:
        return (-1.0, -1.0)
    if c == "safety":
        return (0.0, -1.0)
    return (float(c[0]), float(E8.POCKET_IDS.index(c[1])))
