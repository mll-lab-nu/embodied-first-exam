#!/usr/bin/env python3
"""Assert, after install, that the image's physics fixes hold (the image build fails otherwise).

  engine     MuJoCo 3.3.7 with its native convex collision (upstream pins 3.1.6, whose general convex routine reported
             depths and normals unrelated to the geometry: feet on boxes, the hip's self-contact, the forearm);
  room       the reset no longer writes into the right hand: every robot joint starts inside its range, and no object
             starts below the floor (upstream-fixes.patch);
  powerlift  the dumbbell carries the plates' density="500": 53.7 kg (upstream, by accident: 104.0 kg).
"""
import gymnasium as gym
import mujoco
import numpy as np

import humanoid_bench  # noqa: F401

assert mujoco.__version__ == "3.3.7", mujoco.__version__
for env_id in ("h1-walk-v0", "h1-balance_hard-v0", "h1-door-v0", "h1hand-room-v0", "h1hand-powerlift-v0"):
    m = gym.make(env_id, render_mode=None).unwrapped.model
    assert not m.opt.disableflags & mujoco.mjtDisableBit.mjDSBL_NATIVECCD, f"{env_id}: native convex collision is off"

env = gym.make("h1hand-room-v0", render_mode=None)
for seed in range(5):
    np.random.seed(seed)          # room places its objects with the global np.random: the same check every build
    env.reset(seed=seed)
    m, d = env.unwrapped.model, env.unwrapped.data
    pel = m.body("pelvis").id
    for j in range(m.njnt):
        if m.body_rootid[m.jnt_bodyid[j]] == pel and m.jnt_limited[j] and m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            q, (lo, hi) = d.qpos[m.jnt_qposadr[j]], m.jnt_range[j]
            assert lo - 0.011 <= q <= hi + 0.011, f"room {seed}: {m.joint(j).name} = {q:.3f} outside [{lo}, {hi}]"
    floor = m.geom("floor").id
    other = [(c, m.geom_bodyid[c.geom1 ^ c.geom2 ^ floor]) for c in d.contact[:d.ncon] if floor in (c.geom1, c.geom2)]
    deep = [m.body(b).name for c, b in other if c.dist < -2e-3 and m.body_rootid[b] != pel]
    assert not deep, f"room seed {seed}: objects start inside the floor: {deep}"

m = gym.make("h1hand-powerlift-v0", render_mode=None).unwrapped.model
mass = float(m.body_subtreemass[m.body("dumbbell").id])
assert abs(mass - 53.7) < 0.1, f"powerlift dumbbell {mass:.2f} kg"
print(f"physics fixes verified: MuJoCo {mujoco.__version__} with native convex collision; room joints in range and "
      f"objects on the floor (5 seeds); powerlift dumbbell {mass:.1f} kg")
