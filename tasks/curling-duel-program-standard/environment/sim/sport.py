"""Curling for the turn-based duel service (server_duel.py): the sport-specific part (game state, action, views)."""
from __future__ import annotations

import base64
import math

import numpy as np

import curling as C
import duel_core as D
import render

NAME = "curling"
REVISION = D.REVISION
FIRST_MEANING = ("FIRST_PLAYER throws the first stone of end 1, so the other player has the hammer (the last stone) "
                 "in end 1; afterwards the team that scored throws first in the next end, a blank end keeps the hammer")
COLOUR = {"A": "yellow", "B": "red"}
_VIEW = {"key": None, "rd": None, "png": None}


def warm() -> None:
    C.master("ccw"); C.master("cw")


def new(seed: int, first: str) -> D.Duel:
    return D.Duel(seed, first)


def validate(body: dict, g=None, seat=None) -> dict | str:
    if body.get("type", "throw") != "throw":
        return "the action is: throw SPEED ANGLE SPIN"
    try:
        v = float(body["speed"]); a = float(body["angle"]); sp = str(body["spin"]).lower()
    except Exception:  # noqa: BLE001
        return "throw needs speed (m/s), angle (deg) and spin (cw | ccw)"
    if sp not in ("cw", "ccw"):
        return "spin must be cw or ccw"
    if not (math.isfinite(v) and math.isfinite(a)):
        return "numbers must be finite"
    if not (C.V_MIN <= v <= C.V_MAX):
        return f"speed must be in [{C.V_MIN}, {C.V_MAX}] m/s"
    if not abs(a) <= C.ANGLE_MAX_DEG:
        return f"angle must be in [-{C.ANGLE_MAX_DEG}, {C.ANGLE_MAX_DEG}] deg"
    return {"type": "throw", "v": v, "angle": a, "spin": sp}


def play(g: D.Duel, seat: str, dec: dict) -> list[dict]:
    return [g.play(seat, dec)]


def _who_team(team: int, seat: str) -> str:
    return "you" if D.SIDES[team] == seat else "opponent"


def shot_text(r: dict, seat: str) -> dict:
    rem = {"you": 0, "opponent": 0}
    why = []
    for sid, reason in r["removed"]:
        t = 0 if sid < C.N_STONES else 1
        rem[_who_team(t, seat)] += 1
        why.append(f"{'your' if D.SIDES[t] == seat else 'an opponent'} stone"
                   f"{' (the thrown one)' if sid == r.get('sid') else ''}: {reason}")
    h = {"end": r["end"] + 1, "throw": r["k"] + 1, "by": _who_team(r["team"], seat), "spin": r["spin"],
         "collisions_heard": r["collisions"], "stones_removed": rem, "removed_why": why}
    if r.get("fgz_violation"):
        h["free_guard_zone_violation"] = "the thrown stone moved an opposition guard out of play: it was removed and the stones were put back"
    if D.SIDES[r["team"]] == seat:
        h["your_release"] = {"speed": r["v"], "angle_deg": r["angle"], "spin": r["spin"]}
    e = r.get("end_finished")
    if e:
        mine = D.TEAM[seat]
        h["end_finished"] = {"end": e["end"] + 1, "scored_by": "blank" if e["team"] < 0 else _who_team(e["team"], seat),
                             "points": e["points"], "score_after": {"you": e["score"][mine], "opponent": e["score"][1 - mine]}}
    return h


def score_view(g: D.Duel, seat: str) -> dict:
    t = D.TEAM[seat]
    o = {"score": {"you": g.score[t], "opponent": g.score[1 - t]}, "your_colour": COLOUR[seat]}
    if not g.done:
        o.update(end=g.end + 1, throw_in_end=g.k + 1, hammer="you" if g.hammer == t else "opponent",
                 stones_left_to_throw={"you": g.stones_left(t), "opponent": g.stones_left(1 - t)})
    return o


def observation(g: D.Duel, seat: str, query: dict) -> dict:
    if _VIEW["key"] != g.n_throws:
        if _VIEW["rd"] is None:
            _VIEW["rd"] = render.Renderer()
        rd = _VIEW["rd"]
        rd.set_stones([(s["id"], s["team"], s["x"], s["y"], s["a"]) for s in g.sheet.stones])
        _VIEW.update(key=g.n_throws, png={c: base64.b64encode(rd.png(c)).decode() for c in ("house", "hack")})
    t = D.TEAM[seat]
    ends = [{"end": e["end"] + 1, "scored_by": "blank" if e["team"] < 0 else _who_team(e["team"], seat),
             "points": e["points"], "score_after": {"you": e["score"][t], "opponent": e["score"][1 - t]}} for e in g.ends]
    return {"end": g.end + 1, "throw_in_end": g.k + 1, "extra_end": g.end >= C.N_ENDS, "your_colour": COLOUR[seat],
            "stones_in_play": {"you": sum(1 for s in g.sheet.stones if s["team"] == t),
                               "opponent": sum(1 for s in g.sheet.stones if s["team"] != t)},
            "ends_so_far": ends, "images_png_b64": dict(_VIEW["png"])}


def parse_query(body: dict) -> dict:
    return {}


def spec(seat: str, first: str) -> dict:
    return {
        "simulator": "curling ice model with impulse collisions; MuJoCo renders the cameras",
        "rules": "World Curling, The Rules of Curling, July 2025 (with the deviations listed in the instructions)",
        "match": {"ends": C.N_ENDS, "max_extra_ends": C.MAX_EXTRA_ENDS, "tie_after_extra_ends": "the player with more chess-clock time left wins",
                  "free_guard_zone_stones": C.FGZ_STONES,
                  "stones_per_team_per_end": C.N_STONES, "first_player": first, "you_throw_first_in_end_1": seat == first,
                  "your_colour": COLOUR[seat], "opponent_colour": COLOUR[D.OTHER[seat]]},
        "action": {"throw": "{'type':'throw','speed':m/s,'angle':deg,'spin':'cw'|'ccw'}",
                   "limits": {"speed_m_s": [C.V_MIN, C.V_MAX], "angle_deg": [-C.ANGLE_MAX_DEG, C.ANGLE_MAX_DEG]},
                   "execution_noise_sigma": {"speed_m_s": C.PLAYER_NOISE["speed"], "angle_deg": C.PLAYER_NOISE["angle_deg"]}},
        "cameras": [{k: v for k, v in c.items() if not k.startswith("_")} for c in render.CAMERAS],
        "camera_model": "pinhole; pixel (u, v) from the image's top-left; u right, v down; a world point p maps to "
                        "u = cx + f * (p - pos).image_right / depth, v = cy - f * (p - pos).image_up / depth, "
                        "depth = (p - pos).optical_axis_forward",
        "world": {"origin": "release point at the hack", "+y": "down the sheet towards the far house", "+x": "right",
                  "tee": [0.0, C.TEE_Y], "far_hog_line_y": C.HOG_Y, "back_line_y": C.BACK_Y, "house_radius": C.HOUSE_R,
                  "sheet_half_width": C.HALF_W, "stone_radius": C.R, "stone_top_z": 0.112, "handle_top_z": 0.146},
    }


def actions_array(decisions: list[dict]) -> dict:
    """trajectory.npz content: per throw the seat (0 = A, 1 = B) and speed, angle_deg, spin (+1 ccw, -1 cw)."""
    return {"seat": np.array([D.SIDES.index(d["seat"]) for d in decisions], dtype=np.int64),
            "actions": np.array([[d["v"], d["angle"], 1.0 if d["spin"] == "ccw" else -1.0] for d in decisions],
                                dtype=np.float64).reshape(-1, 3)}


def scores(g: D.Duel) -> dict:
    return {"A": g.score[0], "B": g.score[1]}
