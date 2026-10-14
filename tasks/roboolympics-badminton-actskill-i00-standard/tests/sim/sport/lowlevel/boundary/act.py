"""The simplest `act` skill from the provided tools (the core-skill boundary test, rule 5), in the deliverable's form:
the base to `base` (else the documented forehand stance for the requested contact) (the toolkit's base_plan), the toolkit's IK for
the requested head pose (pos, normal) at that base position, then the arm straight there at its speed limit and held.
It ignores t and vel (no swing: the racket meets the shuttle nearly still) and has no step()."""
import sys

import numpy as np

_S = {}


def act(t, pos, normal, vel, base=None, *, state, spec):
    if not _S:
        tk = spec["toolkit"]
        sys.path.insert(0, tk["ik_library"]["file"].rsplit("/", 1)[0])
        from bm_kinematics import RacketKinematics
        _S["K"] = RacketKinematics(tk["robot_model"], base_limits=spec["limits"]["base"])
        _S["vel"] = np.array(spec["limits"]["arm"]["velocity_rad_s"], float)
        _S["step"] = np.array(spec["joints"]["max_step"], float) * 0.999
    K = _S["K"]
    q_t = np.asarray(state["q_target"], float)
    v_t = np.asarray(state.get("qd_target") or np.zeros(9), float)
    r = max(0.30, 0.95 - 0.35 * abs(float(pos[2]) - 1.333))
    goal = np.clip(np.asarray(pos[:2], float) - 0.62 * r if base is None else np.asarray(base, float), K.base_lo,
                   K.base_hi)
    n = int(min(600, max(60, round(float(t) / 0.01) + 30)))
    brows, _ = K.base_plan(q_t[:2], v_t[:2], goal, n)
    qa, _ = K.solve_near(pos, normal=normal, q_ref=q_t[2:], base=goal, vel_limit=_S["vel"])
    rows, prev = [], q_t.copy()
    for b in brows:
        q = np.r_[b, prev[2:] + np.clip(qa - prev[2:], -_S["step"][2:], _S["step"][2:])]
        rows.append([round(float(x), 7) for x in q])
        prev = q
    return {"type": "traj", "q": rows}
