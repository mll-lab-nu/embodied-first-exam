#!/usr/bin/env python3
"""Box feet for the scenes where the H1 stands on a box: a fix to upstream's contact physics, not to its task.

    python box_feet.py apply  [HB_ROOT]   rewrite the assets (in the clone layer, before install)
    python box_feet.py verify             assert the fix holds (after install: needs mujoco + humanoid_bench)

Why. Upstream collides each foot as the convex hull of its mesh (`left_ankle_link.stl`), and a mesh on a box goes
through MuJoCo's general convex routine: one contact point per foot. On 3.1.6, the version upstream pins, that point
jumped between toe and heel and every so often carried a depth and normal unrelated to the geometry (483 mm and
horizontal for a foot 23 mm into a stair tread): the robot with every joint locked slid off a stair tread in 9 of 10
placements, and 281 foot-box contacts in our logged stair / balance episodes were more than 5 mm off. 3.3.7's native
routine gets the depth right but still gives one point, so the robot never comes to rest (11-15 mm/s on a tread with
`multiccd`, more without). Against the floor plane a dedicated routine is used and nothing is wrong.

The fix. The hull is a sole slab (0.30 x 0.03 m, flat, 12 mm high) under a wedge that narrows to the ankle. It becomes
four boxes: the slab exactly, and the wedge as three 19-20 mm layers, each as long as the hull at its mid-height
(within 3 mm there, 13-31 mm off at a layer's top and bottom edges, where the hull's faces slope; the top 11 mm, the
tip under the ankle joint, has no box; total volume 98.4% of the hull's). Box-box and box-plane are MuJoCo's exact
colliders, up to 4 points per foot on a flat support. Collision geoms carry no mass (class "collision": mass 0), so
the model's inertia, nq, nv and every instance file are untouched. Only the h1 and h1hand env files of the three
families whose scene puts the feet on a box point at the box-foot robot; every other family keeps upstream's robot.
"""
import os
import re
import sys

ROBOTS = ("h1_pos", "h1hand_pos")
FAMILIES = ("stair", "balance_simple", "balance_hard")
FOOT_MESH = re.compile(r'<geom class="collision" mesh="(left|right)_ankle_link"/>')
SOLE_Z = -0.0700   # the sole, in the ankle body frame
# (centre, half-size) per box in the ankle body frame, bottom to top; checked against the compiled mesh by `verify`.
BOXES = (((0.05000, 0.0, -0.0640), (0.15000, 0.0150, 0.0060)),    # sole slab, 0-12 mm
         ((0.04785, 0.0, -0.0485), (0.13195, 0.0150, 0.0095)),    # 12-31 mm
         ((0.03370, 0.0, -0.0295), (0.09200, 0.0135, 0.0095)),    # 31-50 mm
         ((0.01695, 0.0, -0.0100), (0.04895, 0.0120, 0.0100)))    # 50-70 mm
BOX_GEOMS = "".join(f'<geom class="collision" type="box" pos="{p[0]} {p[1]} {p[2]}" size="{s[0]} {s[1]} {s[2]}"/>'
                    for p, s in BOXES)
BOXED = ("h1-stair-v0", "h1-balance_simple-v0", "h1-balance_hard-v0", "h1hand-balance_hard-v0")
MESH = ("h1-walk-v0", "h1hand-room-v0")


def apply(root: str) -> None:
    assets = os.path.join(root, "humanoid_bench", "assets")
    for robot in ROBOTS:
        src = open(os.path.join(assets, "robots", f"{robot}.xml")).read()
        out, n = FOOT_MESH.subn(BOX_GEOMS, src)
        assert n == 2, f"{robot}.xml: expected 2 foot colliders, found {n}"
        open(os.path.join(assets, "robots", f"{robot}_boxfeet.xml"), "w").write(out)
        for fam in FAMILIES:
            path = os.path.join(assets, "envs", f"{robot}_{fam}.xml")
            env = open(path).read()
            inc = f'<include file="../robots/{robot}.xml"/>'
            assert env.count(inc) == 1, f"{path}: robot include not found"
            open(path, "w").write(env.replace(inc, f'<include file="../robots/{robot}_boxfeet.xml"/>'))
    print(f"box feet: {len(ROBOTS)} robots x {len(FAMILIES)} families rewritten")


def _section_x(w, z):
    """The x-extent of the convex hull of points w where it crosses height z (from every segment that spans z)."""
    lo, hi = w[w[:, 2] <= z], w[w[:, 2] > z]
    t = (z - lo[:, None, 2]) / (hi[None, :, 2] - lo[:, None, 2])
    x = lo[:, None, 0] + t * (hi[None, :, 0] - lo[:, None, 0])
    return float(x.min()), float(x.max())


def _hull_in_ankle_frame(m, side):
    import mujoco
    import numpy as np
    b = m.body(f"{side}_ankle_link").id
    g = next(g for g in range(m.ngeom) if m.geom_bodyid[g] == b and m.geom_contype[g])
    assert m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH, "walk must keep upstream's mesh feet"
    mid = m.geom_dataid[g]
    v = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
    rot = np.zeros(9)
    mujoco.mju_quat2Mat(rot, m.geom_quat[g])
    return v @ rot.reshape(3, 3).T + m.geom_pos[g]


def _stands_still(m, d, x, z):
    """Every joint locked, feet flat at (x, keyframe height + z): after 20 s, still where it was, upright and still?"""
    import mujoco
    import numpy as np
    pel = m.body("pelvis").id
    saved = [a.copy() for a in (m.jnt_range, m.jnt_limited, m.actuator_gainprm, m.actuator_biasprm)]
    mujoco.mj_resetDataKeyframe(m, d, 0)
    d.qpos[0] = x
    d.qpos[2] += z
    for j in range(m.njnt):
        if m.body_rootid[m.jnt_bodyid[j]] == pel and m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            q = d.qpos[m.jnt_qposadr[j]]
            m.jnt_range[j] = [q - 1e-4, q + 1e-4]
            m.jnt_limited[j] = 1
    m.actuator_gainprm[:, 0] = 0
    m.actuator_biasprm[:, :3] = 0
    mujoco.mj_forward(m, d)
    x0 = d.qpos[:2].copy()
    mujoco.mj_step(m, d, nstep=10000)
    for a, b in zip((m.jnt_range, m.jnt_limited, m.actuator_gainprm, m.actuator_biasprm), saved):
        a[:] = b
    slid, speed = float(np.linalg.norm(d.qpos[:2] - x0)), float(np.linalg.norm(d.qvel[:3]))
    return slid < 0.02 and speed < 1e-3 and d.xmat[m.body("torso_link").id, 8] > 0.99, (slid, speed)


def verify() -> None:
    import gymnasium as gym
    import mujoco
    import humanoid_bench

    root = os.path.dirname(humanoid_bench.__file__)
    # 1. The boxes follow the hull, read off the compiled upstream mesh: the slab's footprint and sole within 0.5 mm,
    #    each layer as long as the hull at its mid-height within 3 mm, and nothing wider than the hull.
    m = mujoco.MjModel.from_xml_path(os.path.join(root, "assets", "envs", "h1_pos_walk.xml"))
    for side in ("left", "right"):
        w = _hull_in_ankle_frame(m, side)
        lo, hi = w.min(0), w.max(0)
        p, s = BOXES[0]
        assert abs(lo[2] - SOLE_Z) < 5e-4 and abs(p[2] - s[2] - SOLE_Z) < 1e-9, (lo, SOLE_Z)
        assert abs(p[0] - s[0] - lo[0]) < 5e-4 and abs(p[0] + s[0] - hi[0]) < 5e-4, (lo, hi)
        assert abs(s[1] - hi[1]) < 5e-4, (s, hi)
        for p, s in BOXES[1:]:
            x0, x1 = _section_x(w, p[2])
            assert abs(p[0] - s[0] - x0) < 3e-3 and abs(p[0] + s[0] - x1) < 3e-3, (p, s, x0, x1)
            assert s[1] <= hi[1] + 1e-9
    # 2. Exactly the three families got box feet; the rest kept the mesh.
    for env_id in BOXED + MESH:
        mm = gym.make(env_id, render_mode=None).unwrapped.model
        feet = {mm.geom_type[g] for g in range(mm.ngeom)
                if "ankle" in mm.body(mm.geom_bodyid[g]).name and mm.geom_contype[g]}
        want = mujoco.mjtGeom.mjGEOM_BOX if env_id in BOXED else mujoco.mjtGeom.mjGEOM_MESH
        assert feet == {want}, f"{env_id}: foot collider {feet}, expected {want}"
    # 3. The behaviour the fix is for: every joint locked, feet flat on a stair tread -> it stands still.
    env = gym.make("h1-stair-v0", render_mode=None)
    m, d = env.unwrapped.model, env.unwrapped.data
    for k in range(3):                     # tread k: x in [0.5 + 0.6k, 1.1 + 0.6k], top z = 0.18(k + 1)
        for frac in (0.15, 0.5, 0.85):     # heel near the front edge, centred, toe near the riser
            ok, (slid, speed) = _stands_still(m, d, 0.5 + 0.6 * k + 0.061 + frac * 0.30, 0.18 * (k + 1))
            assert ok, f"tread {k + 1} at {frac}: slid {slid:.3f} m, speed {speed:.4f} m/s"
    print("box feet verified: boxes follow the hull, 3 families boxed / others mesh, "
          "locked robot stands still on 9 tread placements")


if __name__ == "__main__":
    if sys.argv[1:2] == ["apply"]:
        apply(sys.argv[2] if len(sys.argv) > 2 else "/opt/humanoid-bench")
    elif sys.argv[1:2] == ["verify"]:
        verify()
    else:
        sys.exit(__doc__)
