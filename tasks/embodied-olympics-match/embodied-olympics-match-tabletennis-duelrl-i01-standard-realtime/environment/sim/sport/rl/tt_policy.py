"""The RL opponent's shot policy (version 1, high level): a small deterministic policy over the shot choices of the
reference's stroke pipeline, trained by evolution strategies against the scripted opponent and in self-play
(training code and report outside the repository).

Inputs (per incoming ball, the ball's true state): the predicted contact point and the ball's velocity there, where
the opponent stands (the ball's first frames after its hit). Outputs: the aim on the opponent's half (|x|, y), the
side (away from the opponent or not), the outgoing speed tried first, the blade-speed cap, and how much later than the
reference's contact point the ball is taken (along its predicted flight). The service: a score per repertoire serve
(the two best alternate). Every stroke is still planned and executed by the platform (the high level's act: the
limits-aware planner, the real limits, the execution scatter). numpy only; the weights are tt_es_v1/weights.json
(builtin_players.RLOpponent loads this file by path; the screening variant `rl` is the same class).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
N_FEAT = 8
OUT = (  # name, low, high, the reference's value (the initial policy)
    ("aim_x", 0.0, 0.70, 0.45),
    ("aim_y", 0.35, 1.25, 0.85),
    ("vy", 2.8, 6.0, 5.0),
    ("vp_cap", 0.9, 2.4, 1.4),
    ("side", -1.0, 1.0, 0.0),        # > 0: away from the opponent (the reference's rule), < 0: towards it
    ("late", 0.0, 0.10, 0.004),      # s after the reference's contact point
)
N_OUT = len(OUT)
SERVE_NAMES = ("mid_wide_fh_top", "short_centre_top", "mid_wide_bh", "mid_centre_back", "short_bh_top",
               "mid_wide_bh_top")
N_PARAMS = N_OUT * N_FEAT + len(SERVE_NAMES)


def _logit(y):
    y = min(max(y, 1e-3), 1 - 1e-3)
    return math.log(y / (1 - y))


def initial() -> np.ndarray:
    """The reference's choices as a policy (zero weights, biases at its values; side: away from the opponent)."""
    W = np.zeros((N_OUT, N_FEAT))
    for i, (name, lo, hi, ref) in enumerate(OUT):
        if name == "side":
            W[i, 6] = -3.0               # opp_x > 0 -> negative -> ... handled in decode (sign relative to the opponent)
            W[i, 7] = 2.0
        else:
            W[i, 7] = _logit((ref - lo) / (hi - lo))
    return np.concatenate([W.ravel(), np.zeros(len(SERVE_NAMES))])


def features(p_hit, v_in, opp_x) -> np.ndarray:
    return np.array([p_hit[0] / 0.7, (p_hit[1] + 1.4) / 0.3, (p_hit[2] - 0.25) / 0.15, v_in[0] / 2.0,
                     (v_in[1] + 4.0) / 2.0, v_in[2] / 2.0, opp_x / 0.5, 1.0])


def decode(theta, p_hit, v_in, opp_x) -> dict:
    W = np.asarray(theta[:N_OUT * N_FEAT], float).reshape(N_OUT, N_FEAT)
    z = W @ features(p_hit, v_in, opp_x)
    out = {}
    for i, (name, lo, hi, _) in enumerate(OUT):
        if name == "side":
            out[name] = float(z[i])
        else:
            out[name] = lo + (hi - lo) / (1.0 + math.exp(-float(np.clip(z[i], -30, 30))))
    return out


def serve_order(theta) -> tuple:
    s = np.asarray(theta[N_OUT * N_FEAT:], float)
    idx = sorted(range(len(SERVE_NAMES)), key=lambda i: (-s[i], i))
    return SERVE_NAMES[idx[0]], SERVE_NAMES[idx[1]]


def load(path=None) -> np.ndarray:
    path = Path(path) if path else HERE / "tt_es_v1" / "weights.json"
    if not path.exists():
        return initial()
    d = json.loads(path.read_text())
    th = np.asarray(d["theta"], float)
    assert th.shape == (N_PARAMS,), th.shape
    return th


# ------------------------------------------------------------------------------------------------ version 2: the swing
# The RL opponent v2 (builtin_players.RLOpponentV2) adds two outputs, on the same features, that go to its own swing
# (fast_swing.py, the act's `swing`): the rail's share of the horizontal blade velocity and a factor on the blade speed
# asked for. theta v2 = theta v1 (N_PARAMS) + N_SWING * N_FEAT.
SWING_OUT = (("base_share", 0.0, 1.0, 0.5), ("overdrive", 0.8, 1.5, 1.0))
N_SWING = len(SWING_OUT)
N_PARAMS_V2 = N_PARAMS + N_SWING * N_FEAT


def initial_v2(theta_v1=None) -> np.ndarray:
    W = np.zeros((N_SWING, N_FEAT))
    for i, (name, lo, hi, ref) in enumerate(SWING_OUT):
        W[i, 7] = _logit((ref - lo) / (hi - lo))
    base = initial() if theta_v1 is None else np.asarray(theta_v1, float)
    return np.concatenate([base[:N_PARAMS], W.ravel()])


def decode_swing(theta, p_hit, v_in, opp_x) -> dict:
    W = np.asarray(theta[N_PARAMS:N_PARAMS_V2], float).reshape(N_SWING, N_FEAT)
    z = W @ features(p_hit, v_in, opp_x)
    return {name: lo + (hi - lo) / (1.0 + math.exp(-float(np.clip(z[i], -30, 30))))
            for i, (name, lo, hi, _) in enumerate(SWING_OUT)}


def load_v2(path=None) -> np.ndarray:
    path = Path(path) if path else HERE / "tt_es_v2" / "weights.json"
    if not path.exists():
        return initial_v2(load())
    th = np.asarray(json.loads(path.read_text())["theta"], float)
    if th.shape == (N_PARAMS,):
        return initial_v2(th)
    assert th.shape == (N_PARAMS_V2,), th.shape
    return th
