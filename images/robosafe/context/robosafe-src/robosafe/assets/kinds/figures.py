"""Human and animal stand-ins made of primitives.

Every body part is one named geom that is drawn and collides, so a contact report says which part was touched. The
figures do not move by themselves: a scene welds them in place or moves them as mocap bodies.
"""
from __future__ import annotations


import numpy as np

from ..catalog import kind
from ..kit import Kit, mm, qx, qy
from ..model import quat_from_z

SKIN = {
    "light": (0.96, 0.80, 0.69), "fair": (0.91, 0.72, 0.58), "medium": (0.80, 0.60, 0.44), "olive": (0.70, 0.52, 0.36),
    "brown": (0.52, 0.35, 0.23), "dark": (0.33, 0.22, 0.15),
}
HAIR = {"black": (0.07, 0.06, 0.06), "brown": (0.30, 0.19, 0.10), "blond": (0.85, 0.70, 0.36), "red": (0.62, 0.25, 0.10),
        "grey": (0.62, 0.62, 0.62), "yarn_yellow": (0.95, 0.78, 0.20), "yarn_red": (0.80, 0.20, 0.12)}
FUR = {"orange": (0.85, 0.52, 0.18), "black": (0.08, 0.08, 0.09), "grey": (0.50, 0.50, 0.52), "white": (0.93, 0.92, 0.90),
       "brown": (0.45, 0.30, 0.17), "tan": (0.78, 0.62, 0.40), "golden": (0.86, 0.66, 0.30)}


def _seg(k: Kit, name: str, a, b, r: float, color, finish="matte") -> None:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    d = b - a
    k.solid("capsule", (r, float(np.linalg.norm(d))), tuple((a + b) / 2.0), color, quat=quat_from_z(d), name=name, finish=finish)


# ---- ISO/TS 15066 body regions (added in 0.5.1) ---------------------------------------------------------------------
# Every part of a figure that collides carries the body region of ISO/TS 15066:2016 Table A.2 it stands for, in
# `meta["regions"]` (part name -> region, or a split of a trunk box into chest and abdomen by the side of the box's
# middle a point lies on). `robosafe/hazard/regions.py` has the limits; docs/CONTRACTS.md, "Added in 0.5.1", says where
# each number comes from. The head is one sphere: it is the region `head` (skull, forehead and face together, with the
# face's limits, the lower ones). Animals are `animal`: the specification is about adult people and gives them nothing.
PART_REGIONS = (("head", "head"), ("neck", "neck"), ("pelvis", "pelvis"), ("upper_arm", "upper_arm_elbow"),
                ("forearm", "lower_arm_wrist"), ("wrist", "lower_arm_wrist"), ("hand", "hand_finger"), ("palm", "hand_finger"),
                ("finger", "hand_finger"), ("thumb", "hand_finger"), ("thigh", "thigh_knee"), ("shin", "lower_leg"),
                ("foot", "lower_leg"), ("shoulder", "back_shoulders"), ("chest", "chest"))


def body_regions(k: Kit, *, torso_axis: int = 2, torso_sign: float = 1.0, arm: str = "upper_arm_elbow", leg: str = "thigh_knee",
                 animal: bool = False) -> None:
    """Tag every colliding named part of a figure with its body region (`meta["regions"]`). `torso`: a box split at its
    middle along its own axis `torso_axis` (0, 1, 2): the chest on the side `torso_sign`, the abdomen on the other. A
    one-piece limb of an infant or a doll (`arm_*`, `leg_*`) is `arm` / `leg`."""
    out = {}
    for name, g in sorted(k._named.items()):
        if g.role == "visual" or name.endswith("_shape"):
            continue
        if animal:
            out[name] = "animal"
        elif name == "torso":
            out[name] = {"split": [int(torso_axis), float(torso_sign)], "upper": "chest", "lower": "abdomen"}
        elif name.startswith("arm_"):
            out[name] = arm
        elif name.startswith("leg_"):
            out[name] = leg
        else:
            region = next((r for prefix, r in PART_REGIONS if name.startswith(prefix)), None)
            if region:
                out[name] = region
    k.extra["regions"] = out


@kind("hand", fixed=True, vary={"skin": list(SKIN), "sleeve": ["blue", "white", "red", "green", "dark_grey"],
                                 "side": ["right", "left"]})
def hand(k: Kit, *, skin="fair", sleeve="blue", side="right", scale=1.0, mass=1.3, reach=0.0):
    """A forearm and hand lying palm down, fingers towards +x. Parts: `forearm`, `palm`, `thumb`, `finger_0` (index)
    to `finger_3`. Meant to be welded or moved as a mocap body. Zone `hand`: the palm and fingers. `reach` (m, 0.5.1;
    default 0, which builds the same bytes as before): the sleeve runs on that much further back (part `sleeve`), so that
    an arm reaching in from beyond the table's edge runs out of every camera's frame instead of ending in mid-air."""
    s = float(scale)
    c = SKIN[skin] if isinstance(skin, str) else skin
    m = 1.0 if side == "right" else -1.0
    if reach:
        _seg(k, "sleeve", (-215 * s - float(reach) * 1000.0, 0, 31 * s), (-215 * s, 0, 31 * s), 30 * s, sleeve)
    _seg(k, "forearm", (-215 * s, 0, 31 * s), (-55 * s, 0, 31 * s), 30 * s, sleeve)
    k.vis("cylinder", (31 * s, 14 * s), (-48 * s, 0, 31 * s), sleeve, quat=qy(90), name="cuff", finish="matte")
    _seg(k, "wrist", (-45 * s, 0, 22 * s), (-12 * s, 0, 18 * s), 18 * s, c)
    k.solid("box", (88 * s, 84 * s, 26 * s), (36 * s, 0, 13 * s), c, name="palm", finish="matte")
    for i, (y, ln) in enumerate(((-31, 68), (-10, 76), (11, 70), (31, 54))):
        _seg(k, f"finger_{i}", (80 * s, m * y * s, 10 * s), ((80 + ln) * s, m * y * 1.12 * s, 9 * s), 9 * s, c)
    _seg(k, "thumb", (18 * s, -m * 44 * s, 11 * s), (70 * s, -m * 70 * s, 10.5 * s), 10.5 * s, c)
    k.site("fingertip", (165 * s, m * -11 * s, 9 * s))
    k.site("palm", (36 * s, 0, 26 * s))
    k.zone("hand", (75 * s, 0, 14 * s), "box", (190 * s, 150 * s, 30 * s))
    k.tag("human")
    body_regions(k)
    k.mass(mass * 1000.0)


@kind("infant", fixed=True, vary={"suit": ["sky", "lime", "yellow", "pink", "white"], "skin": list(SKIN), "hair": ["brown", "black", "blond"]})
def infant(k: Kit, *, length=0.44, suit="sky", skin="light", hair="brown", mass=None):
    """A baby lying on its back along x, head at -x, the middle of its body over the origin: a large head with a
    dummy in the mouth, a round body in a sleepsuit top, a nappy, bare arms and legs. Parts that collide: `head`,
    `torso`, `arm_left`, `arm_right`, `leg_left`, `leg_right`, `shin_left`, `shin_right`. Site `chest` on top of
    the chest, `head` on top of the head. Too wide for the hand: it has no grasp."""
    s = mm(length) / 335.0
    c = SKIN[skin] if isinstance(skin, str) else skin
    hc = HAIR[hair] if isinstance(hair, str) else hair
    X = lambda x: (x + 25.0) * s                                 # the template has the torso's lower edge at x = 0
    hx, hr = X(-150.0), 42.0 * s
    k.solid("sphere", (hr,), (hx, 0, hr), c, name="head", finish="matte")
    k.vis("ellipsoid", (hr * 0.80, hr * 1.02, hr * 0.92), (hx - hr * 0.40, 0, hr * 1.08), hc, name="hair", finish="matte")
    k.vis("ellipsoid", (hr * 0.30, hr * 0.62, hr * 0.20), (hx - hr * 0.30, 0, hr * 1.86), hc, name="fringe", finish="matte")
    for i, sy in enumerate((-1, 1)):
        k.vis("sphere", (hr * 0.17,), (hx + hr * 0.12, sy * hr * 0.36, hr * 1.88), (0.97, 0.97, 0.95), name=f"eye_{i}")
        k.vis("sphere", (hr * 0.10,), (hx + hr * 0.12, sy * hr * 0.36, hr * 1.99), (0.10, 0.08, 0.08), name=f"pupil_{i}")
        k.vis("ellipsoid", (hr * 0.16, hr * 0.20, hr * 0.10), (hx + hr * 0.40, sy * hr * 0.58, hr * 1.66), (0.96, 0.62, 0.60), name=f"cheek_{i}",
              finish="matte")
        k.vis("ellipsoid", (hr * 0.13, hr * 0.05, hr * 0.17), (hx - hr * 0.05, sy * hr * 0.99, hr * 0.95), c, name=f"ear_{i}", finish="matte")
    k.vis("cylinder", (hr * 0.24, hr * 0.07), (hx + hr * 0.50, 0, hr * 1.86), (0.25, 0.62, 0.90), name="dummy")
    k.vis("sphere", (hr * 0.09,), (hx + hr * 0.50, 0, hr * 1.95), (0.98, 0.85, 0.25), name="dummy_knob")
    # the body: a box that collides, drawn as a rounded sleepsuit top with a nappy below it
    k.col("box", (120 * s, 96 * s, 60 * s), (X(-60), 0, 30 * s), name="torso")
    k.vis("ellipsoid", (66 * s, 52 * s, 32 * s), (X(-62), 0, 32.5 * s), suit, name="torso_shape", finish="matte")
    k.vis("ellipsoid", (40 * s, 46 * s, 30 * s), (X(-34), 0, 36 * s), suit, name="belly", finish="matte")
    k.vis("ellipsoid", (36 * s, 50 * s, 30 * s), (X(-2), 0, 30 * s), (0.97, 0.97, 0.95), name="nappy", finish="matte")
    for nm, sy in (("left", 1.0), ("right", -1.0)):
        _seg(k, f"arm_{nm}", (X(-104), sy * 50 * s, 24 * s), (X(-128), sy * 100 * s, 15 * s), 14 * s, c)       # arms up beside the head
        k.vis("sphere", (16 * s,), (X(-136), sy * 112 * s, 16 * s), c, name=f"hand_{nm}", finish="matte")
        _seg(k, f"leg_{nm}", (X(14), sy * 28 * s, 22 * s), (X(66), sy * 56 * s, 20 * s), 19 * s, c)             # thighs apart, knees bent
        _seg(k, f"shin_{nm}", (X(66), sy * 56 * s, 20 * s), (X(108), sy * 38 * s, 16 * s), 15 * s, c)
        k.vis("ellipsoid", (20 * s, 13 * s, 15 * s), (X(120), sy * 34 * s, 17 * s), c, name=f"foot_{nm}", finish="matte")
    k.site("chest", (X(-70), 0, 60 * s))
    k.site("head", (hx, 0, 2 * hr))
    k.tag("human", "child")
    body_regions(k, torso_axis=0, torso_sign=-1.0)          # lying along x, head at -x
    k.mass((mass if mass else 4.5 * (float(length) / 0.55) ** 3) * 1000.0)


@kind("doll", vary={"dress": ["pink", "sky", "lime", "yellow", "red"], "skin": list(SKIN), "hair": ["yarn_yellow", "yarn_red", "brown", "black"]})
def doll(k: Kit, *, length=0.35, dress="pink", skin="light", hair="yarn_yellow", mass=0.26):
    """A rag doll lying on its back along x, head at -x. Parts: `head`, `torso`, `arm_left`, `arm_right`, `leg_left`,
    `leg_right`. A stand-in for a small child (`meta["proxy"]`)."""
    s = mm(length) / 350.0
    c = SKIN[skin] if isinstance(skin, str) else skin
    hc = HAIR[hair] if isinstance(hair, str) else hair
    hx = -143 * s
    k.solid("sphere", (32 * s,), (hx, 0, 32 * s), c, name="head", finish="matte")
    k.vis("ellipsoid", (30 * s, 35 * s, 24 * s), (hx - 10 * s, 0, 28 * s), hc, name="hair", finish="matte")
    for i, sy in enumerate((-1, 1)):
        k.vis("sphere", (3.6 * s,), (hx + 6 * s, sy * 11 * s, 62.5 * s), "black", name=f"eye_{i}")
        k.vis("ellipsoid", (16 * s, 9 * s, 9 * s), (hx - 26 * s, sy * 34 * s, 22 * s), hc, name=f"pigtail_{i}", finish="matte")
    k.vis("box", (2.5 * s, 12 * s, 1.5 * s), (hx + 18 * s, 0, 61 * s), (0.75, 0.15, 0.15), name="mouth")
    k.solid("box", (112 * s, 74 * s, 42 * s), (-55 * s, 0, 21 * s), dress, name="torso", finish="matte")
    k.vis("box", (40 * s, 100 * s, 30 * s), (10 * s, 0, 15 * s), dress, name="skirt", finish="matte")
    for nm, sy in (("left", 1.0), ("right", -1.0)):
        _seg(k, f"arm_{nm}", (-96 * s, sy * 44 * s, 13 * s), (-28 * s, sy * 86 * s, 12 * s), 12 * s, c)
        _seg(k, f"leg_{nm}", (8 * s, sy * 20 * s, 14 * s), (128 * s, sy * 34 * s, 14 * s), 14 * s, c)
        k.vis("ellipsoid", (16 * s, 13 * s, 16 * s), (140 * s, sy * 35 * s, 17 * s), (0.2, 0.2, 0.25), name=f"shoe_{nm}", finish="matte")
    k.grasp("torso", "top", (-55 * s, 0, 24 * s), 74 * s)
    k.grasp("leg", "top", (70 * s, 27 * s, 15 * s), 28 * s, yaw_deg=7.0)
    k.site("head", (hx, 0, 64 * s))
    k.tag("human", "child")
    k.extra["proxy"] = "doll"
    body_regions(k, torso_axis=0, torso_sign=-1.0, leg="lower_leg")      # a leg from hip to shoe: the lower limit
    k.mass(mass * 1000.0)


def _face(k: Kit, hr: float, zc: float, c, hc, child: bool) -> None:
    """Hair, ears, eyes with whites, brows, nose and mouth on a head of radius `hr` centred at height `zc`, facing -y.
    A child's face has larger eyes set lower, round cheeks and a fringe."""
    k.vis("ellipsoid", (hr * 1.04, hr * 1.02, hr * 0.80), (0, hr * 0.16, zc + hr * 0.30), hc, name="hair", finish="matte")
    if child:
        k.vis("ellipsoid", (hr * 0.80, hr * 0.30, hr * 0.30), (0, -hr * 0.72, zc + hr * 0.62), hc, name="fringe", finish="matte")
    ey, ez, er = (-hr * 0.88, zc - hr * 0.02, hr * 0.17) if child else (-hr * 0.90, zc + hr * 0.10, hr * 0.12)
    for i, sx in enumerate((-1, 1)):
        k.vis("sphere", (er,), (sx * hr * 0.36, ey, ez), (0.97, 0.97, 0.95), name=f"eye_{i}")
        k.vis("sphere", (er * 0.60,), (sx * hr * 0.36, ey - er * 0.62, ez), (0.10, 0.08, 0.08), name=f"pupil_{i}")
        k.vis("ellipsoid", (hr * 0.16, hr * 0.05, hr * 0.035), (sx * hr * 0.36, ey + hr * 0.02, ez + er * 1.6), hc, name=f"brow_{i}", finish="matte")
        k.vis("ellipsoid", (hr * 0.10, hr * 0.22, hr * 0.26), (sx * hr * 0.98, 0, zc - hr * 0.05), c, name=f"ear_{i}", finish="matte")
        if child:
            k.vis("ellipsoid", (hr * 0.20, hr * 0.10, hr * 0.16), (sx * hr * 0.58, -hr * 0.74, zc - hr * 0.32), (0.96, 0.62, 0.60), name=f"cheek_{i}", finish="matte")
    k.vis("ellipsoid", (hr * 0.10, hr * 0.14, hr * 0.12), (0, -hr * 0.98, zc - hr * 0.22), c, name="nose", finish="matte")
    if child:                                                    # a dummy in the mouth
        k.vis("cylinder", (hr * 0.24, hr * 0.06), (0, -hr * 0.97, zc - hr * 0.50), (0.25, 0.62, 0.90), quat=qx(90.0), name="dummy")
        k.vis("sphere", (hr * 0.09,), (0, -hr * 1.04, zc - hr * 0.50), (0.98, 0.85, 0.25), name="dummy_knob")
    else:
        k.vis("ellipsoid", (hr * 0.24, hr * 0.06, hr * 0.055), (0, -hr * 0.90, zc - hr * 0.50), (0.72, 0.22, 0.22), name="mouth", finish="matte")


def _trunk(k: Kit, sh_w: float, torso_d: float, z_sh: float, z_hip: float, Ht: float, shirt, trousers, child: bool) -> None:
    """The trunk: boxes that collide (`torso`, `pelvis`), drawn as rounded shapes with shoulders (and, on a child, a
    round belly and a bib)."""
    h = z_sh - z_hip - 0.02 * Ht
    zc = (z_sh + z_hip + 0.02 * Ht) / 2.0
    k.col("box", (2 * sh_w, torso_d, h), (0, 0, zc), name="torso")
    k.col("box", (2 * sh_w * 0.92, torso_d * 0.98, 0.10 * Ht), (0, 0, z_hip - 0.02 * Ht), name="pelvis")
    k.vis("ellipsoid", (sh_w * 1.02, torso_d * 0.60, h * 0.60), (0, 0, zc), shirt, name="torso_shape", finish="matte")
    for i, sx in enumerate((-1, 1)):
        k.vis("sphere", (torso_d * 0.36,), (sx * sh_w * 0.86, 0, z_sh - torso_d * 0.30), shirt, name=f"shoulder_{i}", finish="matte")
    k.vis("ellipsoid", (sh_w * 0.96, torso_d * 0.60, 0.06 * Ht), (0, 0, z_hip - 0.01 * Ht), (0.97, 0.97, 0.95) if child else trousers,
          name="pelvis_shape", finish="matte")                    # a child wears a nappy
    if child:
        k.vis("ellipsoid", (sh_w * 0.80, torso_d * 0.50, h * 0.36), (0, -torso_d * 0.22, zc - h * 0.14), shirt, name="belly", finish="matte")
        k.vis("ellipsoid", (sh_w * 0.46, torso_d * 0.10, h * 0.24), (0, -torso_d * 0.60, zc + h * 0.24), (0.97, 0.97, 0.94), name="bib", finish="matte")


def _shoe(k: Kit, name: str, size, pos, color) -> None:
    """A foot: a box that collides, drawn as a rounded shoe."""
    k.col("box", size, pos, name=name)
    k.vis("ellipsoid", (size[0] * 0.56, size[1] * 0.54, size[2] * 0.50), pos, color, name=name + "_shape", finish="matte")


def _humanoid(k: Kit, *, height_m: float, head_ratio: float, pose: str, skin, hair, shirt, trousers, shoes, seat: bool,
              stocky: float = 1.0) -> None:
    """A standing figure facing -y, then re-posed. Lengths in millimetres; `head_ratio` is head radius over height."""
    Ht = height_m * 1000.0
    c = SKIN[skin] if isinstance(skin, str) else skin
    hc = HAIR[hair] if isinstance(hair, str) else hair
    hr = head_ratio * Ht
    w = stocky
    sh_z = Ht - 2 * hr - 0.045 * Ht                              # shoulder line
    hip_z = 0.50 * Ht if head_ratio < 0.07 else 0.44 * Ht
    knee_z = hip_z * 0.53
    sh_w = 0.125 * Ht * w                                        # half shoulder width
    hip_w = 0.052 * Ht * w
    torso_d = 0.125 * Ht * w
    r_arm, r_fore, r_thigh, r_shin = 0.026 * Ht * w, 0.022 * Ht * w, 0.043 * Ht * w, 0.031 * Ht * w
    foot = (0.055 * Ht * w, 0.15 * Ht, 0.045 * Ht)
    child = head_ratio >= 0.07
    legs = c if child else trousers                              # a small child's legs are bare

    def add_head(z_top):
        zc = z_top - hr
        k.solid("sphere", (hr,), (0, 0, zc), c, name="head", finish="matte")
        _face(k, hr, zc, c, hc, child)
        k.site("head", (0, 0, z_top))
        _seg(k, "neck", (0, 0, sh_z + 0.01 * Ht), (0, 0, zc - hr * 0.8), 0.028 * Ht * w, c)

    if pose in ("standing", "lying"):
        add_head(Ht)
        _trunk(k, sh_w, torso_d, sh_z, hip_z, Ht, shirt, trousers, child)
        for nm, sx in (("left", 1.0), ("right", -1.0)):
            xs = sx * (sh_w + r_arm * 0.9)
            el = (xs + sx * 0.012 * Ht, 0, sh_z - 0.175 * Ht)
            wr = (xs + sx * 0.018 * Ht, -0.02 * Ht, sh_z - 0.33 * Ht)
            _seg(k, f"upper_arm_{nm}", (xs, 0, sh_z - r_arm), el, r_arm, shirt)
            _seg(k, f"forearm_{nm}", el, wr, r_fore, c)
            k.solid("sphere", (r_fore * 1.25,), (wr[0], wr[1] - 0.005 * Ht, wr[2] - 0.035 * Ht), c, name=f"hand_{nm}", finish="matte")
            hx = sx * hip_w
            _seg(k, f"thigh_{nm}", (hx, 0, hip_z - 0.06 * Ht), (hx, 0, knee_z), r_thigh, legs)
            _seg(k, f"shin_{nm}", (hx, 0, knee_z), (hx, 0, foot[2] + r_shin * 0.6), r_shin, legs)
            _shoe(k, f"foot_{nm}", foot, (hx, -foot[1] * 0.22, foot[2] / 2.0), shoes)
        if pose == "lying":                                      # on the back, head towards -x, face up
            rot = np.array([[0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
            k.reframe(rot, (0.0, max(torso_d / 2.0, foot[1] * 0.28), Ht / 2.0))
    elif pose == "sitting":
        seat_z = knee_z + r_thigh * 0.4                           # top of the seat
        dz = seat_z + r_thigh - (hip_z - 0.06 * Ht)               # how far the trunk comes down
        top = Ht + dz
        zc = top - hr
        k.solid("sphere", (hr,), (0, 0, zc), c, name="head", finish="matte")
        _face(k, hr, zc, c, hc, child)
        k.site("head", (0, 0, top))
        shz, hpz = sh_z + dz, hip_z + dz
        _seg(k, "neck", (0, 0, shz + 0.01 * Ht), (0, 0, zc - hr * 0.8), 0.028 * Ht * w, c)
        _trunk(k, sh_w, torso_d, shz, hpz, Ht, shirt, trousers, child)
        thigh_len = hip_z - 0.06 * Ht - knee_z
        zt = seat_z + r_thigh
        for nm, sx in (("left", 1.0), ("right", -1.0)):
            xs = sx * (sh_w + r_arm * 0.9)
            el = (xs + sx * 0.012 * Ht, -0.02 * Ht, shz - 0.175 * Ht)
            wr = (sx * hip_w * 1.3, -0.15 * Ht, zt + r_thigh + r_fore)
            _seg(k, f"upper_arm_{nm}", (xs, 0, shz - r_arm), el, r_arm, shirt)
            _seg(k, f"forearm_{nm}", el, wr, r_fore, c)
            k.solid("sphere", (r_fore * 1.25,), (wr[0], wr[1] - 0.03 * Ht, wr[2]), c, name=f"hand_{nm}", finish="matte")
            hx = sx * hip_w
            _seg(k, f"thigh_{nm}", (hx, 0, zt), (hx, -thigh_len, zt), r_thigh, legs)
            _seg(k, f"shin_{nm}", (hx, -thigh_len, zt), (hx, -thigh_len, foot[2] + r_shin * 0.6), r_shin, legs)
            _shoe(k, f"foot_{nm}", foot, (hx, -thigh_len - foot[1] * 0.22, foot[2] / 2.0), shoes)
        if seat:
            side = 2.2 * sh_w
            k.solid("box", (side, side * 0.9, seat_z), (0, 0.02 * Ht, seat_z / 2.0), (0.35, 0.33, 0.30), name="seat", finish="matte")
    else:
        raise ValueError("pose: standing, sitting or lying")


@kind("person", fixed=True, vary={"skin": list(SKIN), "hair": ["black", "brown", "blond", "grey", "red"],
                                   "shirt": ["blue", "red", "green", "white", "yellow", "purple"], "height": (1.55, 1.9)})
def person(k: Kit, *, height=1.72, pose="standing", skin="medium", hair="brown", shirt="blue", trousers="navy",
           shoes="dark_grey", seat=True, mass=None):
    """An adult mannequin facing -y: `standing`, `sitting` (on a block that comes with it) or `lying` on its back
    (head towards -x). Origin on the floor under it. Parts: `head`, `neck`, `torso`, `pelvis`, `upper_arm_*`,
    `forearm_*`, `hand_*`, `thigh_*`, `shin_*`, `foot_*` (`left`, `right`)."""
    _humanoid(k, height_m=float(height), head_ratio=0.058, pose=pose, skin=skin, hair=hair, shirt=shirt, trousers=trousers,
              shoes=shoes, seat=seat)
    k.tag("human")
    body_regions(k)
    k.extra["pose"] = pose
    k.mass((mass if mass else 70.0 * (float(height) / 1.72) ** 3) * 1000.0)


@kind("toddler", fixed=True, vary={"skin": list(SKIN), "hair": ["black", "brown", "blond"],
                                    "shirt": ["yellow", "red", "sky", "lime", "pink"], "height": (0.78, 0.95)})
def toddler(k: Kit, *, height=0.86, pose="standing", skin="light", hair="blond", shirt="yellow", trousers="blue",
            shoes="red", seat=False, mass=None):
    """A small child (about two years old): a large head on a short round body, bare legs, a nappy, a bib and a dummy
    in the mouth (`trousers` is kept for the callers and not drawn). Poses and part names as for `person`; sitting
    is on the floor unless `seat` is set."""
    if pose == "sitting" and not seat:
        _humanoid(k, height_m=float(height), head_ratio=0.090, pose="sitting", skin=skin, hair=hair, shirt=shirt, trousers=trousers,
                  shoes=shoes, seat=False, stocky=1.25)
        lo, _ = k.bounds()                                       # lower the figure onto the floor
        k.reframe(np.eye(3), (0.0, 0.0, 0.0))
        drop = float(min(g.pos[2] - (g.size[2] / 2.0 if g.type == "box" else g.size[0]) for g in k.root.geoms
                         if g.name and g.name.startswith(("thigh", "pelvis")) and not g.name.endswith("_shape")))
        k.reframe(np.eye(3), (0.0, 0.0, drop))
        for g in list(k.root.geoms):                             # legs stretched out on the floor instead of hanging
            if g.name and g.name.startswith(("shin", "foot")):
                k.root.geoms.remove(g)
                k._named.pop(g.name, None)
        H = float(height) * 1000.0
        for nm, sx in (("left", 1.0), ("right", -1.0)):
            th = [g for g in k.root.geoms if g.name == f"thigh_{nm}"][0]
            y_knee = th.pos[1] - th.size[1] / 2.0
            r = 0.031 * H * 1.25
            _seg(k, f"shin_{nm}", (th.pos[0], y_knee, r), (th.pos[0] * 1.6, y_knee - 0.17 * H, r), r, SKIN[skin] if isinstance(skin, str) else skin)
            _shoe(k, f"foot_{nm}", (0.055 * H * 1.25, 0.05 * H, 0.11 * H), (th.pos[0] * 1.6, y_knee - 0.20 * H, 0.055 * H), shoes)
    else:
        _humanoid(k, height_m=float(height), head_ratio=0.090, pose=pose, skin=skin, hair=hair, shirt=shirt, trousers=trousers,
                  shoes=shoes, seat=seat, stocky=1.25)
    k.tag("human", "child")
    body_regions(k)
    k.extra["pose"] = pose
    k.mass((mass if mass else 12.0 * (float(height) / 0.86) ** 3) * 1000.0)


def _quadruped(k: Kit, *, s: float, fur, pose: str, snout: float, ear: str, tail_up: bool, belly=None, collar=None,
               stripes=None, eye=(0.75, 0.70, 0.15)) -> None:
    """An animal facing +x. `s` scales a cat-sized template; `snout` is the muzzle length in template millimetres."""
    c = FUR[fur] if isinstance(fur, str) else fur
    rb = 62 * s
    if pose == "standing":
        zb = 205 * s
        leg_top, front_x, back_x = zb - rb * 0.55, 95 * s, -110 * s
    elif pose == "lying":
        zb = rb
    else:
        raise ValueError("pose: standing or lying")
    _seg(k, "body", (-125 * s, 0, zb), (105 * s, 0, zb + (8 * s if pose == "standing" else 0)), rb, c)
    hx, hz, hr = 190 * s, zb + (58 * s if pose == "standing" else 30 * s), 50 * s
    _seg(k, "neck", (120 * s, 0, zb + 12 * s), (hx - 20 * s, 0, hz - 12 * s), 36 * s, c)
    k.solid("sphere", (hr,), (hx, 0, hz), c, name="head", finish="matte")
    k.solid("box", (snout * s, 40 * s, 32 * s), (hx + hr * 0.75 + snout * s / 2.0 - 6 * s, 0, hz - 12 * s), belly or c, name="snout",
            finish="matte")
    k.vis("sphere", (7 * s,), (hx + hr * 0.75 + snout * s - 6 * s, 0, hz - 4 * s), "black", name="nose")
    for i, sy in enumerate((-1, 1)):
        k.vis("sphere", (6.5 * s,), (hx + hr * 0.80, sy * 20 * s, hz + 12 * s), eye, name=f"eye_{i}", finish="gloss")
        k.vis("sphere", (3.2 * s,), (hx + hr * 0.90, sy * 20 * s, hz + 12 * s), "black", name=f"pupil_{i}")
        if ear == "pointed":
            k.vis("box", (20 * s, 6 * s, 34 * s), (hx - 6 * s, sy * 28 * s, hz + hr * 0.95), c, quat=qx(-sy * 18.0), name=f"ear_{i}",
                  finish="matte")
        else:
            k.vis("ellipsoid", (20 * s, 8 * s, 34 * s), (hx - 8 * s, sy * (hr + 2 * s), hz - 4 * s), tuple(v * 0.7 for v in c[:3]),
                  quat=qx(sy * 12.0), name=f"ear_{i}", finish="matte")
    if collar:
        k.vis("cylinder", (38 * s, 12 * s), (150 * s, 0, zb + 32 * s), collar, quat=qy(55.0), name="collar")
    if stripes:
        for i in range(5):
            k.vis("cylinder", (rb * 1.012, 10 * s), ((-95 + 42 * i) * s, 0, zb + (8 * s * (i / 4.0) if pose == "standing" else 0)),
                  stripes, quat=qy(90.0), name=f"stripe_{i}", finish="matte")
    r_leg = 17 * s
    if pose == "standing":
        for nm, x in (("front", front_x), ("hind", back_x)):
            for side, sy in (("left", 1.0), ("right", -1.0)):
                _seg(k, f"leg_{nm}_{side}", (x, sy * 34 * s, leg_top), (x + (6 * s if nm == "front" else -4 * s), sy * 36 * s, r_leg),
                     r_leg, c)
        tail = [(-180 * s, 0, zb + 20 * s), (-250 * s, 0, zb + (70 if tail_up else 10) * s), (-270 * s, 0, zb + (150 if tail_up else -40) * s)]
    else:
        for side, sy in (("left", 1.0), ("right", -1.0)):
            _seg(k, f"leg_front_{side}", (95 * s, sy * 36 * s, r_leg), (200 * s, sy * 40 * s, r_leg), r_leg, c)
            _seg(k, f"leg_hind_{side}", (-120 * s, sy * 58 * s, r_leg * 1.2), (-40 * s, sy * 72 * s, r_leg * 1.2), r_leg * 1.2, c)
        tail = [(-180 * s, 0, 16 * s), (-250 * s, 60 * s, 14 * s), (-200 * s, 130 * s, 14 * s)]
    _seg(k, "tail", tail[0], tail[1], 13 * s, c)
    _seg(k, "tail_tip", tail[1], tail[2], 12 * s, c)
    k.site("head", (hx, 0, hz + hr))
    k.tag("animal")
    body_regions(k, animal=True)


@kind("cat", fixed=True, vary={"fur": ["orange", "black", "grey", "white"], "pose": ["standing", "lying"]})
def cat(k: Kit, *, fur="orange", pose="standing", scale=1.0, mass=4.2):
    """A cat facing +x, `standing` or `lying`. Parts: `body`, `neck`, `head`, `snout`, `leg_front_left` ..., `tail`."""
    stripes = {"orange": (0.62, 0.32, 0.08), "grey": (0.30, 0.30, 0.32)}.get(fur) if isinstance(fur, str) else None
    _quadruped(k, s=float(scale), fur=fur, pose=pose, snout=22.0, ear="pointed", tail_up=True, stripes=stripes,
               eye=(0.55, 0.75, 0.25))
    k.extra["pose"] = pose
    k.mass(mass * 1000.0 * float(scale) ** 3)


@kind("dog", fixed=True, vary={"fur": ["brown", "tan", "golden", "black", "white"], "pose": ["standing", "lying"]})
def dog(k: Kit, *, fur="brown", pose="standing", scale=1.5, collar="red", mass=11.0):
    """A small dog facing +x with a long muzzle, hanging ears and a collar. Parts as for `cat`."""
    _quadruped(k, s=float(scale), fur=fur, pose=pose, snout=52.0, ear="floppy", tail_up=True, belly=None, collar=collar,
               eye=(0.25, 0.15, 0.08))
    k.extra["pose"] = pose
    k.mass(mass * 1000.0 * (float(scale) / 1.5) ** 3)
