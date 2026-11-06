#!/usr/bin/env python3
"""Write the court of the badminton scene (bm_scene.xml, next to this file) for the court scale of sim/bm.py.

Revision wallclock-8 / duel-10 (user decision 2026-10-08): every horizontal line of the BWF court is scaled by
COURT_SCALE (bm.COURT_SCALE; the net keeps its BWF height). This rewrites, in place, the floor's court geoms (lines,
the yellow 1 m marks along the outside of the singles side lines and behind the base lines), the net, the posts, the
gantry's joint ranges (bm.BASE_LO / BASE_HI + 5 cm) and the base motors' feed force (bm.BASE_FORCE); then run
mk_duel_scene.py for the duel's render scene. No import of bm (it needs MuJoCo): the numbers are repeated here and
tests/test_badminton.py checks that the scene and bm agree.

    python3 sports/badminton/sim/scene/mk_court.py && python3 sports/badminton/sim/scene/mk_duel_scene.py
"""
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENE = HERE / "bm_scene.xml"

COURT_SCALE = 0.4                       # = bm.COURT_SCALE
S = COURT_SCALE
CX, CY, DX, SSL = 2.59 * S, 6.70 * S, 3.05 * S, 1.98 * S      # singles side, back line, doubles side, short service
NET_TOP, POST_H = 1.524, 1.55
BASE_LO = (-(CX + 0.95), -(CY + 0.85))  # = bm.BASE_LO / BASE_HI
BASE_HI = (CX + 0.95, -0.5)
BASE_FORCE = 2500                       # = bm.BASE_FORCE (Festo EGC-185-TB-KF feed force, N)
W = 'rgba="0.97 0.97 0.97 1" contype="0" conaffinity="0"'
Y = 'rgba="1 0.85 0.1 1" contype="0" conaffinity="0"'


def f(x):
    return f"{round(x, 4):g}"


def court() -> list[str]:
    g = [f'<geom name="court" type="box" size="{f(DX + 0.3)} {f(CY + 0.6)} 0.001" pos="0 0 -0.001" '
         'rgba="0.13 0.45 0.30 1" contype="0" conaffinity="0"/>']
    for nm, x in (("side_sL", -CX), ("side_sR", CX), ("side_dL", -DX), ("side_dR", DX)):
        g.append(f'<geom name="{nm}" type="box" size="0.02 {f(CY)} 0.001" pos="{f(x)} 0 0.001" {W}/>')
    for sg in (-1, 1):
        g.append(f'<geom name="base_line{sg}" type="box" size="{f(DX)} 0.02 0.001" pos="0 {f(sg * CY)} 0.001" {W}/>')
        g.append(f'<geom name="short_service{sg}" type="box" size="{f(DX)} 0.02 0.001" pos="0 {f(sg * SSL)} 0.001" '
                 f'{W}/>')
        g.append(f'<geom name="centre_line{sg}" type="box" size="0.02 {f((CY - SSL) / 2)} 0.001" '
                 f'pos="0 {f(sg * (CY + SSL) / 2)} 0.001" {W}/>')
    i = 0
    xm = DX + 0.14                       # the marks: just outside the doubles side lines, every 1 m
    for y in range(-int(CY), int(CY) + 1):
        for x in (-xm, xm):
            g.append(f'<geom name="mk{i}" type="box" size="0.1 0.025 0.0015" pos="{f(x)} {y} 0.0015" {Y}/>')
            i += 1
    for x in range(-int(DX), int(DX) + 1):
        for y in (-(CY + 0.14), CY + 0.14):
            g.append(f'<geom name="mk{i}" type="box" size="0.025 0.1 0.0015" pos="{x} {f(y)} 0.0015" {Y}/>')
            i += 1
    return g


def net() -> list[str]:
    return [f'<!-- net: 0.76 m deep band whose top is {NET_TOP} m (BWF Law 1.10), posts ({POST_H} m) at the doubles side '
            'lines -->',
            f'<geom name="net" type="box" size="{f(DX)} 0.004 0.38" pos="0 0 {f(NET_TOP - 0.38)}" '
            'rgba="0.9 0.9 0.9 0.35" contype="0" conaffinity="0"/>',
            f'<geom name="net_tape" type="box" size="{f(DX)} 0.012 0.018" pos="0 0 {f(NET_TOP - 0.018)}" '
            'rgba="1 1 1 1" contype="0" conaffinity="0"/>',
            f'<geom name="post_L" type="cylinder" size="0.025 {f(POST_H / 2)}" pos="{f(-DX)} 0 {f(POST_H / 2)}" '
            'rgba="0.2 0.2 0.2 1" contype="0" conaffinity="0"/>',
            f'<geom name="post_R" type="cylinder" size="0.025 {f(POST_H / 2)}" pos="{f(DX)} 0 {f(POST_H / 2)}" '
            'rgba="0.2 0.2 0.2 1" contype="0" conaffinity="0"/>']


def main():
    xml = SCENE.read_text()
    ind = "    "
    a = xml.index('<geom name="court"')
    b = xml.index("\n", xml.index('<geom name="post_R"'))
    body = court() + [""] + net()
    xml = xml[:a] + ("\n" + ind).join(body) + xml[b:]
    xml = re.sub(r'(<joint name="base_x" type="slide" axis="1 0 0" range=")[^"]*(")',
                 rf"\g<1>{f(BASE_LO[0] - 0.05)} {f(BASE_HI[0] + 0.05)}\g<2>", xml)
    xml = re.sub(r'(<joint name="base_y" type="slide" axis="0 1 0" range=")[^"]*(")',
                 rf"\g<1>{f(BASE_LO[1] - 0.05)} {f(BASE_HI[1] + 0.05)}\g<2>", xml)
    xml = re.sub(r'(<motor name="motor_b[xy]" joint="base_[xy]" ctrlrange=")[^"]*(")',
                 rf"\g<1>-{BASE_FORCE} {BASE_FORCE}\g<2>", xml)
    xml = re.sub(r"Singles court \|x\| <= [0-9.]+, \|y\| <= [0-9.]+ \(doubles side lines drawn at [0-9.]+\)",
                 f"Singles court |x| <= {f(CX)}, |y| <= {f(CY)} (doubles side lines drawn at {f(DX)}; the BWF court "
                 f"x {COURT_SCALE:g})", xml)
    SCENE.write_text(xml)
    print("wrote", SCENE)


if __name__ == "__main__":
    main()
