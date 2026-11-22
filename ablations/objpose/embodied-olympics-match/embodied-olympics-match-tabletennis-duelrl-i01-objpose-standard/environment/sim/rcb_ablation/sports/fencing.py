"""Fencing (format bout, phrase by phrase against the scripted fencer): the state table, and the no-success-signal
edits.

The bout's phrases were measured in a MuJoCo world (two Unitree G1 with epees on the piste: sport fencing.py) and are
replayed from the phrase table (sport phrases.py). A phrase is fenced at once inside the act that completes it, so the
world has no state during one; between phrases both fencers stand on guard (the layout every phrase starts from). The
state table puts that layout into the fencing scene and reads it: each robot (pelvis pose, joints and their ranges,
the whole robot's extent), each epee (the hand body: grip, guard, blade), the piste and its lines. Your own frame
(spec: you at x < 0 facing +x). Left out under no success signal: the score (also after each phrase), each phrase's
result and the black card."""
from __future__ import annotations

from . import _mj

HIDE_KEYS = ("score_after", "how")
_SCENE: dict = {}

BODY = {"pos": "m (the pelvis)", "quat": "wxyz (the pelvis)", "joint_pos": "rad",
        "joint_range": "{joint: [lower, upper]} rad (null: not limited)", **_mj.BOX}
BLADE = {"pos": "m (the hand body: grip, guard, blade)", "quat": "wxyz", **_mj.BOX}
FEATURE = {"pos": "m", **_mj.BOX}
LINES = {"piste": "piste", "centre_line": "centre_line", "own_on_guard_line": "guard_A",
         "opponent_on_guard_line": "guard_B", "own_rear_limit": "rear_A", "opponent_rear_limit": "rear_B"}


def hide(obj):
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items() if not (k == "card" and str(v).startswith("P-black"))}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(obj)


def _scene():
    if not _SCENE:
        import mujoco as mj
        import fencing as F                              # sport/fencing.py: the scene the phrases were measured in
        model = mj.MjModel.from_xml_string(F.scene_xml())
        _SCENE.update(model=model, data=mj.MjData(model))
    return _SCENE["model"], _SCENE["data"]


def entities(m, seat):
    ents = {"robot": {"kind": "robot", "fields": dict(BODY), "note": "your G1, on guard"},
            "blade": {"kind": "robot_link", "fields": dict(BLADE), "note": "your epee"},
            "opponent": {"kind": "robot", "fields": dict(BODY), "note": "the opponent's G1, on guard"},
            "opponent_blade": {"kind": "object", "fields": dict(BLADE), "note": "the opponent's epee"}}
    for n in LINES:
        ents[n] = {"kind": "scene_feature", "fields": dict(FEATURE)}
    return {"frame": "your own frame (x along the piste towards the opponent, you at x < 0; y to your left; z up; "
                     "piste surface z = 0)", "quaternion_order": "wxyz", "entities": ents}


def read(m, seat, names):
    """The on-guard layout (sport phrases.py PhraseTable.guard_qpos), this seat's fencer at x < 0 (bodies A_)."""
    import mujoco as mj
    model, data = _scene()
    data.qpos[:] = m.table.guard_qpos()
    mj.mj_kinematics(model, data)
    out = {}
    for n in names:
        if n in ("robot", "opponent"):
            pre = "A" if n == "robot" else "B"
            b = _mj.body_id(model, f"{pre}_pelvis")
            js = _mj.joints(model, data, _mj.joint_names(model, rf"^{pre}_"))
            out[n] = {"pos": _mj.r(data.xpos[b]), "quat": _mj.r(data.xquat[b], 6),
                      **_mj.strip({"joint_pos": js["joint_pos"], "joint_range": js["joint_range"]}, prefix_len=2),
                      **_mj.body_box(model, data, b, subtree=True)}
        elif n in ("blade", "opponent_blade"):
            h = _mj.body_id(model, f"{'A' if n == 'blade' else 'B'}_hand")
            out[n] = {"pos": _mj.r(data.xpos[h]), "quat": _mj.r(data.xquat[h], 6), **_mj.body_box(model, data, h)}
        elif n in LINES:
            out[n] = _mj.geom_box(model, data, LINES[n])
    return out
