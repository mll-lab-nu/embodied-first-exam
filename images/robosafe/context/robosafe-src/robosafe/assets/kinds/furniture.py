"""Furniture and fixtures: drawers, cabinets, shelves, tables, a door, a machine hopper. All fixed by default."""
from __future__ import annotations


import numpy as np

from ..catalog import kind
from ..kit import Kit, mm, qx
from ..model import Joint


@kind("drawer_unit", priority=2, fixed=True, vary={"color": ["light_grey", "white", "wood"], "locked": [False, True]})
def drawer_unit(k: Kit, *, width=0.40, depth=0.45, height=0.22, color="light_grey", front_color=None, text="", pictograms=(),
                locked=False, mass=9.0):
    """A unit with one drawer on a slide (joint `drawer`, metres, driven by the actuator of the same name), a handle,
    an `open` button and a lock lamp (looks `locked`, `unlocked`). `locked` keeps the drawer shut. Zone `inside`
    moves with the drawer."""
    W, D, H = mm(width, depth, height)
    t = 14.0
    iw, idp, ih = k.case(W, D, H, t, color)
    travel = (D - 60.0)
    dw, dh, dd = iw - 8.0, ih - 26.0, D - t - 20.0
    drawer = k.part("drawer_box", (0, -D / 2, t + 4.0), mass_g=1800.0)
    drawer.joints.append(Joint("drawer", "slide", axis=(0, -1, 0), range=(0.0, 0.5 if locked else travel), damping=6.0,
                               frictionloss=1.0, armature=0.01, role="drawer"))
    k.box_vessel(dw, dd, dh, wall=8.0, floor=8.0, color="white", corner=0.5, center=(0, dd / 2 + 8.0), z0=0.0, body=drawer,
                 liquid=False, name="drawer_tray")
    fc = front_color or color
    k.solid("box", (W - 4.0, 16.0, H - 8.0), (0, -8.0 + 8.0, H / 2 - t - 4.0), fc, body=drawer, name="drawer_front")
    k.solid("box", (W * 0.4, 14.0, 12.0), (0, -18.0 + 8.0 - 6.0, H * 0.62 - t), "steel", body=drawer, name="handle", finish="metal")
    k.site("handle", (0, -24.0, H * 0.62 - t), body=drawer)
    if text or pictograms:
        k.label_flat([text] if text else [], pictograms, size=(W * 0.62, H * 0.30), pos=(0, 0.0, H * 0.28 - t), style="plain", body=drawer)
    k.vis("cylinder", (5.0, 2.0), (W / 2 - 26.0, -0.5, H * 0.78 - t - 4.0), (0.1, 0.5, 0.15), quat=qx(90), body=drawer, name="lock_lamp",
          finish="glow")
    k.look("locked", "lock_lamp", (1.0, 0.15, 0.1))
    k.look("unlocked", "lock_lamp", (0.15, 0.9, 0.25))
    k.button("open", (W / 2 - 30.0, -D / 2 + 40.0, H), axis=(0, 0, 1), size=(26.0, 18.0), color="blue")    # blue, as the door buttons of the appliances
    k.door("drawer", "drawer", open=0.0 if locked else travel * 1e-3 * 0.8, closed=0.0, kp=120.0, kv=25.0, force=20.0)
    k.doors["drawer"]["locked"] = bool(locked)
    k.set_look("locked" if locked else "unlocked")
    k.tag("storage")
    k.mass(mass * 1000.0)


def _cabinet(k: Kit, W, D, H, color, text, pictograms, style, shelves, mass, door_color=None, legs=0.0):
    t = 16.0
    if legs:
        for sx in (-1, 1):
            for sy in (-1, 1):
                k.solid("box", (30.0, 30.0, legs), (sx * (W / 2 - 25), sy * (D / 2 - 25), legs / 2), "dark_grey")
    iw, idp, ih = k.case(W, D, H, t, color, z0=legs)
    n = int(shelves)
    levels = [legs + t]
    for i in range(n):
        z = legs + t + ih * (i + 1) / (n + 1)
        k.solid("box", (iw, idp - 10.0, 12.0), (0, 5.0 - t / 2 + 0.0, z), color, name=f"shelf_board_{i}")
        levels.append(z + 6.0)
    for i, z in enumerate(levels):
        top = levels[i + 1] - 12.0 if i + 1 < len(levels) else legs + H - t
        k.zone(f"shelf_{i}", (0, -t / 2, (z + top) / 2), "box", (iw, idp - 10.0, top - z))
        k.site(f"level_{i}", (0, -t / 2 - 20.0, z))
    k.zone("inside", (0, -t / 2, legs + H / 2), "box", (iw, idp, ih))
    leaf = k.hinged_door("door", (-W / 2, -D / 2, legs + 2.0), W, H - 4.0, 18.0, door_color or color, mass_g=mass * 220.0)
    k.solid("box", (12.0, 22.0, 110.0), (W - 34.0, -18.0 - 11.0, (H - 4.0) * 0.5), "steel", body=leaf, name="handle", finish="metal")
    k.site("handle", (W - 34.0, -40.0, (H - 4.0) * 0.5), body=leaf)
    if text or pictograms:
        lines = (text.split(" ", 1) if len(text) > 9 else [text]) if isinstance(text, str) else list(text)
        k.label_flat([x for x in lines if x], pictograms, size=(W * 0.62, min(H * 0.34, W * 0.5)), pos=(W * 0.45, -18.0, (H - 4.0) * 0.70),
                     style=style, body=leaf)
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("cabinet", priority=2, fixed=True, vary={"text": ["CLEANING SUPPLIES", "MEDICINE", "FIRST AID", "TOOLS", "SNACKS"],
                                              "color": ["white", "light_grey", "wood"]})
def cabinet(k: Kit, *, width=0.50, depth=0.35, height=0.70, color="white", text="CLEANING SUPPLIES", pictograms=(),
            label_style="plain", shelves=1, mass=14.0):
    """A cabinet with one door (joint `door`, hinged on the left, driven by the actuator of the same name) that carries
    a printed label, and shelves inside (zones `shelf_0` ..., sites `level_0` ...)."""
    W, D, H = mm(width, depth, height)
    _cabinet(k, W, D, H, color, text, pictograms, label_style, shelves, mass)


@kind("shelf", priority=2, fixed=True, vary={"color": ["wood", "white", "light_grey"], "width": (0.5, 0.8)})
def shelf(k: Kit, *, width=0.60, depth=0.30, height=0.45, color="wood", levels=2, mass=6.0):
    """Open shelving with `levels` boards above the bottom one. Sites `level_0` (bottom) upwards, zones `shelf_k`."""
    W, D, H = mm(width, depth, height)
    t = 16.0
    n = int(levels)
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.solid("box", (t, D, H), (sgn * (W - t) / 2, 0, H / 2), color, name=f"side_{nm}", finish="matte")
    k.solid("box", (W - 2 * t, 6.0, H), (0, D / 2 - 3.0, H / 2), color, name="back", finish="matte")
    zs = [t / 2 + (H - t) * i / n for i in range(n + 1)]
    for i, z in enumerate(zs):
        k.solid("box", (W - 2 * t, D - 6.0, t), (0, -3.0, z), color, name=f"board_{i}", finish="matte")
        k.site(f"level_{i}", (0, -3.0, z + t / 2))
        clear = (zs[i + 1] - z - t) if i < n else 300.0
        k.zone(f"shelf_{i}", (0, -3.0, z + t / 2 + clear / 2), "box", (W - 2 * t, D - 6.0, clear))
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("low_table", priority=2, fixed=True, vary={"color": ["wood", "white", "dark_grey"]})
def low_table(k: Kit, *, width=0.60, depth=0.40, height=0.35, color="wood", mass=7.0):
    """A low table on four legs. Zone `surface`: the 30 cm above the top."""
    W, D, H = mm(width, depth, height)
    k.solid("box", (W, D, 24.0), (0, 0, H - 12.0), color, name="top_board", finish="matte")
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        k.solid("box", (36.0, 36.0, H - 24.0), (sx * (W / 2 - 30), sy * (D / 2 - 30), (H - 24.0) / 2), color, name=f"leg_{i}", finish="matte")
    k.site("surface_top", (0, 0, H))
    k.zone("surface", (0, 0, H + 150.0), "box", (W, D, 300.0))
    k.zone("below", (0, 0, (H - 24.0) / 2), "box", (W - 72.0, D - 72.0, H - 24.0), place=True)
    k.mass(mass * 1000.0)


@kind("high_shelf", priority=2, fixed=True, vary={"height": (0.40, 0.60)})
def high_shelf(k: Kit, *, width=0.50, depth=0.25, height=0.50, color="white", mass=5.0):
    """A single board high above what it stands on, on two posts at the back with a foot plate. Zone `surface` on it,
    zone `below` under it."""
    W, D, H = mm(width, depth, height)
    k.solid("box", (W, D + 60.0, 12.0), (0, 30.0, 6.0), "dark_grey", name="foot", finish="matte")
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.solid("box", (24.0, 24.0, H - 12.0), (sgn * (W / 2 - 14), D / 2 + 46.0, (H + 12.0) / 2), "dark_grey", name=f"post_{nm}", finish="matte")
        k.solid("box", (10.0, D * 0.8, 10.0), (sgn * (W / 2 - 14), D / 2 + 34.0 - D * 0.4, H - 26.0), "dark_grey", name=f"bracket_{nm}")
    k.solid("box", (W, D, 18.0), (0, 0, H - 9.0), color, name="board", finish="matte")
    k.site("surface_top", (0, 0, H))
    k.zone("surface", (0, 0, H + 150.0), "box", (W, D, 300.0))
    k.zone("below", (0, 0, 12.0 + (H - 30.0) / 2), "box", (W, D, H - 30.0), place=True)
    k.tag("storage")
    k.mass(mass * 1000.0)


@kind("door", priority=2, fixed=True, vary={"text": ["STAFF ONLY", "LAB 2", "STORE ROOM", "FIRE EXIT"], "color": ["white", "wood", "light_grey"]})
def door(k: Kit, *, width=0.90, height=2.00, color="white", text="STAFF ONLY", pictograms=(), sign_style="info_sign", exit=False,
         mass=38.0):
    """A door in its frame (joint `door`, hinged on the left, opening towards -y, driven by the actuator of the same
    name) with a sign plate at eye height. `exit=True` puts a green emergency-exit sign above it and tags it a safety
    device. Zone `clearance`: the metre in front of it that has to stay free."""
    W, H = mm(width, height)
    fw, fd = 70.0, 120.0
    for sgn, nm in ((-1.0, "left"), (1.0, "right")):
        k.solid("box", (fw, fd, H + fw), (sgn * (W / 2 + fw / 2), 0, (H + fw) / 2), "light_grey" if color != "light_grey" else "white",
                name=f"jamb_{nm}", finish="matte")
    k.solid("box", (W + 2 * fw, fd, fw), (0, 0, H + fw / 2), "light_grey" if color != "light_grey" else "white", name="lintel", finish="matte")
    k.solid("box", (W + 2 * fw, 420.0, 14.0), (0, 0, 7.0), "dark_grey", name="threshold", finish="matte")
    leaf = k.hinged_door("door", (-W / 2, -fd / 2 + 44.0, 18.0), W - 6.0, H - 22.0, 40.0, color, mass_g=18000.0, kp=40.0, force=40.0,
                         open_angle=1.5, limit=1.75)
    k.solid("box", (120.0, 50.0, 22.0), (W - 6.0 - 90.0, -40.0 - 25.0, H * 0.50), "steel", body=leaf, name="handle", finish="metal")
    k.site("handle", (W - 6.0 - 110.0, -100.0, H * 0.50), body=leaf)
    if text or pictograms:
        k.label_flat([text] if text else [], pictograms, size=(320.0, 110.0), pos=((W - 6.0) / 2, -40.0, H * 0.78), style=sign_style,
                     body=leaf, name="sign")
    if exit:
        k.solid("box", (420.0, 30.0, 170.0), (0, -fd / 2 - 15.0, H + fw + 95.0), (0.0, 0.5, 0.3), name="exit_box")
        k.label_flat(["EXIT"], ("emergency_exit",), size=(400.0, 150.0), pos=(0, -fd / 2 - 30.0, H + fw + 95.0), style="exit_sign",
                     name="exit_sign", glow=0.6)
        k.tag("safety_device")
    k.zone("clearance", (0, -fd / 2 - 500.0, H / 2), "box", (W + 2 * fw, 1000.0, H))
    k.extra["exit"] = bool(exit)
    k.mass(mass * 1000.0)


@kind("belt_conveyor", priority=2, fixed=True, vary={"color": ["grey", "blue", "green", "orange"]})
def belt_conveyor(k: Kit, *, length=0.62, belt_width=0.13, height=0.075, roller=0.022, period=0.03, color="grey", mass=6.0):
    """A short tabletop belt conveyor that carries things along +x, from the tail roller to the head roller, where a
    fence across the end (`fence`) stops them. The belt is one flat plate on a slide joint (`belt`, metres): a scripted
    mover drives it at a steady speed, its position wrapping every `period` (`movers`: the joint leg's `wrap`), so the
    plate is as long as the run between the rollers plus one period and never sticks out by more than one period;
    the cleats drawn across it every `period` hide the wrap. Its collision surface is flat and uniform; the cleats are
    drawn only. At the head end the belt runs onto the head roller under the fence: the in-running nip (zone `nip`,
    from the belt's top up to 6 cm above it, from 6 cm before the head roller's axis to the fence). On the front side
    near the tail a small control box carries a green START and a red STOP button (controls `start`, `stop`, pressed
    from above), a green lamp on its front and its top and a beacon 4 cm across on a post (looks `running`: glowing
    green; `idle`: dull grey-green). Bright stripes across the belt (drawn only) show its travel. Zone `belt`: where a thing put on the belt rests."""
    L, BW, H, R, P = mm(length, belt_width, height, roller, period)
    T = 4.0                                                    # the belt's thickness
    xt, xh = -L / 2 + R + 6.0, L / 2 - R - 6.0                 # the rollers' axes
    zr = H - T - R                                             # their height
    rail_h = 10.0                                              # the side guides stand this far above the belt
    yr = BW / 2 + 5.0
    frame = {"grey": (0.55, 0.57, 0.60), "blue": (0.15, 0.32, 0.62), "green": (0.12, 0.45, 0.30), "orange": (0.85, 0.45, 0.12)}.get(color, color)
    # the frame: a bed under the belt between the rollers, two side plates with the guides, feet
    k.solid("box", (xh - xt, BW - 4.0, zr - 4.0), ((xt + xh) / 2, 0, (zr - 4.0) / 2), "dark_grey", name="bed", finish="matte")
    for sgn, nm in ((-1.0, "front"), (1.0, "back")):
        k.solid("box", (L, 6.0, H + rail_h), (0, sgn * (yr + 3.0), (H + rail_h) / 2), frame, name=f"side_{nm}", finish="satin")
    for i, x in enumerate((xt, xh)):
        k.vis("cylinder", (R, BW), (x, 0, zr), "steel", quat=qx(90.0), name=f"roller_{i}", finish="metal")
        k.col("cylinder", (R, BW), (x, 0, zr), quat=qx(90.0), name=f"roller_{i}_col")
    # the fence across the head end, a finger's width above the belt (things carried there stop against it)
    fx = xh + R * 0.4
    k.solid("box", (6.0, BW + 12.0, 46.0), (fx + 3.0, 0, H + 2.5 + 23.0), frame, name="fence", finish="satin")
    # the belt: a plate on a slide joint, wrapping every period (its left end at xt - P when the joint is at 0)
    from ..model import Joint
    Lb = (xh - xt) + P
    belt = k.part("belt_plate", (xt - P + Lb / 2, 0, H - T / 2), mass_g=300.0)
    belt.joints.append(Joint("belt", "slide", axis=(1.0, 0.0, 0.0), armature=0.5, role="belt"))
    # the drive: a velocity servo on the belt's joint (the geared motor: it keeps the belt at its target speed under
    # the load of what it carries, and holds it still at a target of 0); the family sets the target, the mover the
    # belt's position as it runs
    k.asset.actuators.append({"name": "belt", "joint": "belt", "kind": "velocity", "kv": 3000.0, "ctrlrange": (-0.5, 0.5),
                              "forcerange": (-300.0, 300.0)})
    k.solid("box", (Lb, BW, T), (0, 0, 0), (0.10, 0.10, 0.11), body=belt, name="belt", finish="matte")
    n = int(Lb // P)
    for i in range(n + 1):
        x = -Lb / 2 + i * P
        if x > Lb / 2 - 1.0:
            break
        # high-contrast stripes (drawn only): the belt's travel shows between frames a fraction of a period apart
        k.vis("box", (P * 0.4, BW - 6.0, 0.6), (x + P * 0.2, 0, T / 2 + 0.3), (0.95, 0.95, 0.93), body=belt, name=f"cleat_{i}", finish="matte")
    # the control box at the front, near the tail: START and STOP on top, the lamp facing the front
    bx, by = -L / 2 + 70.0, -(yr + 6.0) - 30.0
    k.solid("box", (90.0, 56.0, H + 10.0), (bx, by, (H + 10.0) / 2), "light_grey", name="control_box", finish="satin")
    k.button("start", (bx - 20.0, by + 6.0, H + 10.0), axis=(0, 0, 1), size=(26.0, 22.0), color="green")
    k.button("stop", (bx + 20.0, by + 6.0, H + 10.0), axis=(0, 0, 1), size=(26.0, 22.0), color="red")
    k.lamp("lamp", (bx, by - 28.5, H - 10.0), on=(0.2, 1.0, 0.3), off=(0.05, 0.22, 0.08), looks=("running", "idle"), radius=7.0)
    k.lamp("lamp_top", (bx + 30.0, by - 16.0, H + 11.0), axis=(0, 0, 1), on=(0.2, 1.0, 0.3), off=(0.05, 0.22, 0.08), looks=("running", "idle"),
           radius=9.0)                                         # the same lamp seen from above
    # a beacon on a post beside the control box, 4 cm across and 5 cm tall: glowing green while the belt runs, dull
    # grey-green when it stands (the small lamps alone were a few pixels in the fixed cameras' images)
    px, ph = bx - 45.0 - 30.0, H + 50.0
    k.solid("box", (40.0, 40.0, 6.0), (px, by, 3.0), "dark_grey", name="beacon_foot", finish="satin")
    k.solid("cylinder", (6.0, ph), (px, by, ph / 2.0), "dark_grey", name="beacon_post", finish="satin")
    k.vis("cylinder", (20.0, 50.0), (px, by, ph + 25.0), (0.25, 0.30, 0.26), name="beacon", finish="glow")
    k.look("running", "beacon", (0.15, 1.0, 0.25))
    k.look("idle", "beacon", (0.25, 0.30, 0.26))
    k.set_look("idle")
    k.zone("belt", (0, 0, H + 40.0), "box", (xh - xt - 40.0, BW - 10.0, 80.0))
    k.zone("nip", ((xh - 60.0 + fx) / 2, 0, H + 30.0), "box", (fx - (xh - 60.0), BW, 60.0), place=False)
    k.site("head", (xh, 0, H))
    k.site("tail", (xt, 0, H))
    k.extra["belt"] = {"joint": "belt", "period": round(P * 1e-3, 6), "top": round(H * 1e-3, 6), "head_x": round(xh * 1e-3, 6),
                       "tail_x": round(xt * 1e-3, 6), "fence_x": round(fx * 1e-3, 6)}
    k.tag("electrical")
    k.mass(mass * 1000.0)


@kind("machine_hopper", priority=2,fixed=True, vary={"color": ["blue", "green", "dark_grey", "orange"]})
def machine_hopper(k: Kit, *, width=0.30, depth=0.30, height=0.46, color="blue", mass=9.0):
    """A feed bin on a machine base: open at the top (zone `inside`), with a sliding gate at the front (joint `gate`,
    metres, driven by the actuator of the same name) that uncovers the outlet (zone `outlet`). Looks `running`, `idle`."""
    W, D, H = mm(width, depth, height)
    hb = 200.0
    k.solid("box", (W, D, hb), (0, 0, hb / 2), "dark_grey", name="base", finish="matte")
    k.vis("box", (W * 0.5, 1.0, 90.0), (0, -D / 2 - 0.3, 70.0), (0.03, 0.03, 0.03), name="outlet_mouth")
    k.zone("outlet", (0, -D / 2 - 40.0, 70.0), "box", (W * 0.5, 80.0, 90.0))
    k.box_vessel(W, D, H - hb, wall=6.0, floor=6.0, color=color, corner=4.0, z0=hb, liquid=False)
    gate = k.part("gate_plate", (0, -D / 2 - 5.0, 70.0), mass_g=600.0)
    gate.joints.append(Joint("gate", "slide", axis=(0, 0, 1), range=(0.0, 110.0), damping=8.0, frictionloss=2.0, armature=0.01, role="door"))
    k.solid("box", (W * 0.56, 8.0, 100.0), (0, 0, 0), "steel", body=gate, name="gate_panel", finish="metal")
    k.solid("box", (60.0, 16.0, 12.0), (0, -10.0, 30.0), "black", body=gate, name="gate_handle")
    k.door("gate", "gate", open=0.10, closed=0.0, kp=2000.0, kv=150.0, force=40.0)
    k.label_flat([("DANGER", 1.0), ("KEEP HANDS CLEAR", 0.8)], ("do_not_touch",), size=(W * 0.86, 76.0), pos=(0, -D / 2, hb + (H - hb) * 0.5),
                 style="danger_sign")
    k.button("start", (W / 2 - 40.0, -D / 2, hb - 30.0), size=(34.0, 22.0), color="green")
    k.button("stop", (W / 2 - 40.0, -D / 2, hb - 62.0), size=(34.0, 22.0), color="red")
    k.lamp("lamp", (-W / 2 + 30.0, -D / 2 - 0.5, hb - 30.0), on=(0.2, 1.0, 0.3), off=(0.05, 0.22, 0.08), looks=("running", "idle"), radius=7.0)
    k.set_look("idle")
    k.tag("electrical")
    k.mass(mass * 1000.0)


# The scripted second arm of `d_arm_shares_table` (0.5.1, docs/movers.md): its link lengths, read by the family's
# kinematics. Metres.
WORK_ARM = {"shoulder_z": 0.22, "upper": 0.25, "fore": 0.34}     # (0.5.1 review: low enough to stay inside the bench cameras)


@kind("work_arm", priority=2, fixed=True, vary={"color": ["yellow", "blue", "white"]})
def work_arm(k: Kit, *, color="yellow", mass=14.0):
    """A small industrial arm on a pedestal that works beside the robot: a turret on the pedestal (joint `base`, about
    z), an upper arm (joint `shoulder`, about the turret's y: 0 points straight up, positive leans towards +x) and a
    forearm with a two-finger tool at its end (joint `elbow`, the same axis). Each joint has a stiff position servo of
    its own name; the links are gravity-compensated, so the arm stands where its servos hold it. An amber beacon on the
    pedestal's front corner, lit while it runs (looks `running`, `idle`). Made to be driven by a script (`robosafe.sim.movers`), not by the agent."""
    z_sh, up, fore = (WORK_ARM[x] * 1000.0 for x in ("shoulder_z", "upper", "fore"))
    k.solid("box", (180.0, 180.0, 120.0), (0, 0, 60.0), "dark_grey", name="pedestal", finish="matte")
    # an amber beacon on the pedestal's front corner (a 4.8 cm dome on a short collar, clear of the turret): lit while the arm runs its cycle,
    # dull while it is parked (looks `running`, `idle`)
    k.vis("cylinder", (26.0, 16.0), (76.0, -76.0, 128.0), "dark_grey", name="beacon_collar")
    for geom, typ, size, z in (("beacon", "cylinder", (24.0, 36.0), 154.0), ("beacon_top", "sphere", (24.0,), 172.0)):
        k.vis(typ, size, (76.0, -76.0, z), (0.16, 0.12, 0.07), name=geom, finish="glow")
        k.look("running", geom, (1.0, 0.42, 0.0))
        k.look("idle", geom, (0.16, 0.12, 0.07))
    turret = k.part("turret", (0, 0, 120.0), mass_g=2500.0)
    turret.gravcomp = 1.0
    # the base turns more than once round (as many arms' first axis does): a swing that keeps over the outside of the
    # table may go past half a turn either way
    turret.joints.append(Joint("base", "hinge", axis=(0, 0, 1), range=(-6.4, 6.4), damping=20.0, armature=0.05, role="axis"))
    k.solid("cylinder", (75.0, 80.0), (0, 0, 40.0), color, body=turret, name="turret_body")
    k.solid("box", (110.0, 100.0, 40.0), (0, 0, z_sh - 120.0 - 20.0), "dark_grey", body=turret, name="shoulder_block")
    upper = k.part("upper", (0, 0, z_sh - 120.0), mass_g=2200.0, parent="turret")
    upper.gravcomp = 1.0
    upper.joints.append(Joint("shoulder", "hinge", axis=(0, 1, 0), range=(-2.0, 2.0), damping=20.0, armature=0.05, role="axis"))
    k.solid("capsule", (42.0, up - 60.0), (0, 0, up / 2.0), color, body=upper, name="upper_link")
    k.solid("cylinder", (48.0, 96.0), (0, 0, 0), "dark_grey", quat=qx(90), body=upper, name="shoulder_hub")
    fore_b = k.part("fore", (0, 0, up), mass_g=1600.0, parent="upper")
    fore_b.gravcomp = 1.0
    fore_b.joints.append(Joint("elbow", "hinge", axis=(0, 1, 0), range=(-2.8, 2.8), damping=15.0, armature=0.05, role="axis"))
    k.solid("cylinder", (40.0, 86.0), (0, 0, 0), "dark_grey", quat=qx(90), body=fore_b, name="elbow_hub")
    k.solid("capsule", (34.0, fore - 190.0), (0, 0, (fore - 130.0) / 2.0), color, body=fore_b, name="fore_link")
    k.solid("box", (70.0, 70.0, 60.0), (0, 0, fore - 105.0), "dark_grey", body=fore_b, name="wrist")
    for i, sx in enumerate((-1, 1)):
        k.solid("box", (14.0, 36.0, 60.0), (sx * 22.0, 0, fore - 45.0), "steel", body=fore_b, name=f"finger_{i}", finish="metal")
    k.site("tool", (0, 0, fore), body=fore_b)
    for j in ("base", "shoulder", "elbow"):
        k.asset.actuators.append({"name": j, "joint": j, "kind": "position", "kp": 4000.0, "kv": 200.0,
                                  "ctrlrange": (-6.4, 6.4), "forcerange": (-400.0, 400.0)})
    k.set_look("idle")
    k.tag("electrical")
    k.mass(mass * 1000.0)
