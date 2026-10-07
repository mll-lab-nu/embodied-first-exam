"""Draw a candidate instance per seed with MuJoCo Playground's own code (@4057c14, JAX on the CPU).

  python make_instances.py Go1JoystickFlatTerrain --seeds 0-49 --out cand/
writes cand/<Env>/seed<k>.json with the episode's start (qpos0, qvel0) and, for the joystick tasks, the command schedule.
Needs `pip install -e <playground>` and `jax[cpu]` (not part of any task image). freeze.py then settles and hashes the
start in the task's own MuJoCo, and the selection rule (select.py) picks the instance.

Joystick: `env.reset(PRNGKey(seed))` gives the start and the first command; the schedule continues Playground's command
process exactly as `Joystick.step` draws it (each step: five obs-noise splits of info["rng"], then rng, key1, key2 =
split(rng, 3); when the timer runs out, sample_command(key1) and a new timer round(Exp(key2) * 5 s / dt)). The draws do
not depend on the physics as long as the episode does not terminate, which success requires.
Getup: reset's draws (drop with p = 0.6: random orientation and joints at z = 0.5 m, else home; base velocity U(-0.5,
0.5)) before its settle, which freeze.py runs in the task's MuJoCo."""
import argparse
import json
import os

import jax
import jax.numpy as jp
import numpy as np
from mujoco_playground import registry


def seeds(s: str) -> list[int]:
    a, _, b = s.partition("-")
    return list(range(int(a), int(b or a) + 1))


def joystick(env, seed: int, horizon: int) -> dict:
    st = jax.jit(env.reset)(jax.random.PRNGKey(seed))
    rng, cmd, timer = st.info["rng"], st.info["command"], int(st.info["steps_until_next_cmd"])
    segs = [{"start_step": 0, "vx": float(cmd[0]), "vy": float(cmd[1]), "wz": float(cmd[2])}]
    split = jax.jit(jax.random.split, static_argnums=1)
    sample = jax.jit(env.sample_command)
    for t in range(horizon - 1):                   # after step t, the command for step t + 1
        for _ in range(5):                           # _get_obs: gyro, gravity, joint_pos, joint_vel, linvel noise
            rng, _ = split(rng, 2)
        rng, key1, key2 = split(rng, 3)
        timer -= 1
        if timer <= 0:
            cmd = sample(key1, cmd)
            timer = int(jp.round(jax.random.exponential(key2) * 5.0 / env.dt))
            c = {"start_step": t + 1, "vx": float(cmd[0]), "vy": float(cmd[1]), "wz": float(cmd[2])}
            if any(c[k] != segs[-1][k] for k in ("vx", "vy", "wz")):   # a redraw can keep the command: one segment
                segs.append(c)
    return {"qpos0": np.asarray(st.data.qpos).tolist(), "qvel0": np.asarray(st.data.qvel).tolist(), "commands": segs}


def seg(t: int, cmd) -> dict:
    return {"start_step": t, "vx": float(cmd[0]), "vy": float(cmd[1]), "wz": float(cmd[2])}


def spot_joystick(env, seed: int, horizon: int, n_split: int) -> dict:
    """spot/joystick.py (n_split 4) and joystick_gait_tracking.py (3): each step splits info["rng"] into n_split keys,
    the first the next rng, the second the command key; after the step counter passes 200 the command is redrawn."""
    st = jax.jit(env.reset)(jax.random.PRNGKey(seed))
    rng, cmd, count = st.info["rng"], st.info["command"], 0
    segs = [seg(0, cmd)]
    split = jax.jit(jax.random.split, static_argnums=1)
    sample = jax.jit(env.sample_command)
    for t in range(horizon - 1):
        keys = split(rng, n_split)
        rng, cmd_rng = keys[0], keys[1]
        count += 1
        if count > 200:
            cmd, count = sample(cmd_rng), 0
            c = seg(t + 1, cmd)
            if any(c[k] != segs[-1][k] for k in ("vx", "vy", "wz")):
                segs.append(c)
    out = {"qpos0": np.asarray(st.data.qpos).tolist(), "qvel0": np.asarray(st.data.qvel).tolist(), "commands": segs}
    if "gait" in st.info:
        out["gait"] = {"type": int(st.info["gait"]), "name": ["trot", "walk", "pace", "bound", "pronk"][int(st.info["gait"])],
                       "frequency_hz": float(st.info["gait_freq"]), "foot_height_m": float(st.info["foot_height"]),
                       "phase0": np.asarray(st.info["phase"]).tolist(), "phase_dt": float(st.info["phase_dt"])}
    return out


def barkour_joystick(env, seed: int, horizon: int) -> dict:
    """barkour/joystick.py: each step splits info["rng"] into (rng, cmd, noise, pert); a push starts when the step
    counter is a nonzero multiple of kick_wait_steps (direction U(0, 2 pi) from the pert key) and lasts
    kick_duration_steps; the counter passes 500 -> a new command and the counter restarts."""
    st = jax.jit(env.reset)(jax.random.PRNGKey(seed))
    rng, cmd, count = st.info["rng"], st.info["command"], 0
    wait, dur = int(st.info["kick_wait_steps"][0]), int(st.info["kick_duration_steps"][0])
    vel = float(st.info["vel_kick"])
    segs, kicks = [seg(0, cmd)], []
    split = jax.jit(jax.random.split, static_argnums=1)
    sample = jax.jit(env.sample_command)
    for t in range(horizon):
        rng, cmd_rng, _noise, pert_rng = split(rng, 4)
        if count % wait == 0 and count != 0:
            ang = float(jax.random.uniform(pert_rng, minval=0.0, maxval=jp.pi * 2))
            kicks.append({"start_step": t, "duration_steps": dur, "velocity_mps": vel,
                          "direction_xy": [float(np.cos(ang)), float(np.sin(ang))]})
        count += 1
        if count > 500:
            cmd, count = sample(cmd_rng), 0
            if t + 1 < horizon:
                segs.append(seg(t + 1, cmd))
    return {"qpos0": np.asarray(st.data.qpos).tolist(), "qvel0": np.asarray(st.data.qvel).tolist(), "commands": segs,
            "kicks": kicks}


def reset_state(env, seed: int) -> dict:
    """Playground's reset as is (no settle, no command): handstand.py draws xy, yaw and the base velocity."""
    st = jax.jit(env.reset)(jax.random.PRNGKey(seed))
    return {"qpos0": np.asarray(st.data.qpos).tolist(), "qvel0": np.asarray(st.data.qvel).tolist()}


def spot_getup(env, seed: int) -> dict:
    rng = jax.random.PRNGKey(seed)
    rng, _noise, key1, key2 = jax.random.split(rng, 4)   # spot/getup.py reset, before its settle; base velocity zero
    drop = bool(jax.random.bernoulli(key1, env._config.drop_from_height_prob))
    qpos = env._get_random_qpos(key2) if drop else env._init_q
    return {"qpos0": np.asarray(qpos).tolist(), "qvel0": [0.0] * env.mjx_model.nv, "dropped": drop}


def getup(env, seed: int) -> dict:
    rng = jax.random.PRNGKey(seed)
    rng, key1, key2 = jax.random.split(rng, 3)     # getup.py reset, before mjx_env.step(..., settle_steps)
    drop = bool(jax.random.bernoulli(key1, env._config.drop_from_height_prob))
    qpos = env._get_random_qpos(key2) if drop else env._init_q
    rng, key = jax.random.split(rng)
    qvel = jp.zeros(env.mjx_model.nv).at[0:6].set(jax.random.uniform(key, (6,), minval=-0.5, maxval=0.5))
    return {"qpos0": np.asarray(qpos).tolist(), "qvel0": np.asarray(qvel).tolist(), "dropped": drop}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("env")
    ap.add_argument("--seeds", default="0-49")
    ap.add_argument("--out", default="cand")
    a = ap.parse_args()
    env = registry.load(a.env, config_overrides={"impl": "jax"})
    horizon = int(env._config.episode_length)
    os.makedirs(os.path.join(a.out, a.env), exist_ok=True)
    for k in seeds(a.seeds):
        rec = {"benchmark": "MuJoCo Playground", "env": a.env, "seed": k, "playground": "4057c14",
               "jax": jax.__version__}
        if a.env == "SpotFlatTerrainJoystick":
            rec.update(spot_joystick(env, k, horizon, 4))
        elif a.env == "SpotJoystickGaitTracking":
            rec.update(spot_joystick(env, k, horizon, 3))
        elif a.env == "BarkourJoystick":
            rec.update(barkour_joystick(env, k, horizon))
        elif "Joystick" in a.env:
            rec.update(joystick(env, k, horizon))
        elif a.env in ("Go1Handstand", "Go1Footstand"):
            rec.update(reset_state(env, k))
        else:
            rec.update(spot_getup(env, k) if a.env == "SpotGetup" else getup(env, k))
        json.dump(rec, open(os.path.join(a.out, a.env, f"seed{k}.json"), "w"), indent=1)
        print(a.env, k, len(rec.get("commands", [])), "segments" if "commands" in rec else f"dropped={rec.get('dropped')}")


if __name__ == "__main__":
    main()
