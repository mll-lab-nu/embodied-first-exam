"""Contacts between robots (construction step 2, physical consistency: "机器人之间有接触"). The library's robots never
touch each other or a second robot: their collision geoms are contype 4 / conaffinity 0 (bodies/selfcollision.py; each
robot's own parts touch through its explicit self-collision pairs), and a hand's contact geoms (contype 1 /
conaffinity 1) touch the world, a ball and each other. A sport whose robots meet (fencing, basketball, soccer) turns
their contacts on here, on the compiled model:

    from bodies import contacts
    m = mujoco.MjModel.from_xml_string(scene)
    info = contacts.between(m, ["A_", "B_"])        # robot prefixes (as mounted); after compiling, before stepping

Robot k gets two bits above the sports' own (BASE and up, two per robot): its body bit on every collision geom of
its body and hand (the library's contype 4 geoms and the hand's), its tool bit on its hand's contact geoms (the blade,
the racket's strings, ...). Each robot's geoms then touch every other robot's body and tools; a robot never touches
itself through these bits (its self-collision stays with its pairs); everything the geoms touched before they still
touch (the bits are added, none removed). Geoms with contype 0 and conaffinity 0 (drawings) are left alone, and so
are geoms whose names match `skip` (sensing volumes such as the G1's kick strike boxes, contype 8).

MuJoCo's broad phase filters body pairs by body_contype / body_conaffinity, which the compiler sets from the bodies'
geoms (the OR of their bits): changing a geom's bits after compiling is not enough, so the bodies' bits are recomputed
here (without it the robots' bodies are still filtered out and they still pass through each other; found in the
fencing and basketball screenings, 2026-10-11).
"""
from __future__ import annotations

import re

BASE = 16                       # the first bit used here; bits 0-15 stay the sports' and the library's (1, 4, 8, ...)
MAX_ROBOTS = (31 - BASE) // 2   # contype is a signed 32-bit int


def bits(k: int) -> tuple[int, int]:
    """(body bit, tool bit) of the k-th robot."""
    if not 0 <= k < MAX_ROBOTS:
        raise ValueError(f"at most {MAX_ROBOTS} robots")
    return 1 << (BASE + 2 * k), 1 << (BASE + 2 * k + 1)


def _robot_geoms(m, prefix: str) -> list[int]:
    import mujoco as mj
    out = []
    for g in range(m.ngeom):
        b = mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[g])) or ""
        if b.startswith(prefix) and (m.geom_contype[g] or m.geom_conaffinity[g]):
            out.append(g)
    return out


def between(m, prefixes, skip: str = r"_strike$") -> dict:
    """Turn on the contacts between the robots mounted with these prefixes (and between each robot and the others'
    tools) on the compiled model m. Returns {prefix: {body_bit, tool_bit, geoms, tools}}."""
    import mujoco as mj
    import numpy as np
    prefixes = list(prefixes)
    if len(set(prefixes)) != len(prefixes):
        raise ValueError("duplicate prefixes")
    skip_re = re.compile(skip) if skip else None
    info, sets = {}, {}
    for k, p in enumerate(prefixes):
        body_bit, tool_bit = bits(k)
        gs = []
        for g in _robot_geoms(m, p):
            name = mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, g) or ""
            if skip_re is not None and skip_re.search(name):
                continue
            gs.append(g)
        tools = [g for g in gs if (mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, g) or "").startswith(p + "hand_")
                 and int(m.geom_contype[g]) & 1]   # the hand's contact geoms (body.py: "contact" in hands.toml)
        sets[p] = (gs, tools)
        info[p] = dict(body_bit=body_bit, tool_bit=tool_bit, geoms=len(gs), tools=len(tools))
    every_body = sum(bits(k)[0] for k in range(len(prefixes)))
    every_tool = sum(bits(k)[1] for k in range(len(prefixes)))
    touched = set()
    for k, p in enumerate(prefixes):
        body_bit, tool_bit = bits(k)
        gs, tools = sets[p]
        for g in gs:
            m.geom_contype[g] |= body_bit
            m.geom_conaffinity[g] |= (every_body & ~body_bit) | (every_tool & ~tool_bit)
            touched.add(int(m.geom_bodyid[g]))
        for g in tools:
            m.geom_contype[g] |= tool_bit
    for b in touched:                     # the broad phase's body filter (see the module docstring)
        sel = m.geom_bodyid == b
        m.body_contype[b] = int(np.bitwise_or.reduce(m.geom_contype[sel]))
        m.body_conaffinity[b] = int(np.bitwise_or.reduce(m.geom_conaffinity[sel]))
    return info


def contacts_between(m, d, prefix_a: str, prefix_b: str) -> list[tuple[str, str]]:
    """The active contacts between two robots' geoms (names), for checks and records."""
    import mujoco as mj
    out = []
    for c in d.contact[:d.ncon]:
        n1 = mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, int(c.geom1)) or ""
        n2 = mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, int(c.geom2)) or ""
        b1 = mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[c.geom1])) or ""
        b2 = mj.mj_id2name(m, mj.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[c.geom2])) or ""
        if (b1.startswith(prefix_a) and b2.startswith(prefix_b)) or (b1.startswith(prefix_b) and b2.startswith(prefix_a)):
            out.append((n1, n2))
    return out
