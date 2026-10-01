"""Provenance for sit_simple_actions.npy: the training-free search that produced it.

    # inside the base image, from the task dir: tests/ has the reward the image deletes (rcb_rewards.py)
    PYTHONPATH=tests python solution/cem_mpc.py h1-sit_simple-v0 --out sit_simple_actions.npy   # ~2.5 min, 32 cores

solve.sh does NOT run this -- it replays the recorded .npy, so the oracle costs one episode and is
deterministic. This file is here so the reference solution can be regenerated and audited -- it re-runs
the search, so it yields an equivalent passing trajectory, not this exact .npy.

Method: cross-entropy-method MPC. Every EXEC control steps it snapshots the simulator, samples N action
sequences (K spline knots interpolated over an H-step horizon) from a Gaussian, scores each by rolling it
out in a forked copy of the env, refits the Gaussian to the ELITE best, and executes the first EXEC
actions of the winner for real. No learning, no gradients, no pretrained anything -- just the simulator
used as its own model, which is why it needs no GPU and no training run.

Rollout scores add a small terminal shaping term (head height + torso uprightness) so the finite horizon
does not prefer falling over later; that term steers the *search* only and never enters the recorded
return, which the verifier recomputes from HumanoidBench's own reward.
"""
import argparse
import os
import time
from multiprocessing import Pool

import numpy as np

os.environ.setdefault("MUJOCO_GL", "osmesa")
import gymnasium as gym                      # noqa: E402
import humanoid_bench                        # noqa: E402,F401  (registers the env ids)
import mujoco                                # noqa: E402
from humanoid_bench.env import TASKS         # noqa: E402
from rcb_rewards import restore              # noqa: E402

restore()   # the image has no reward function; without it every rollout would score 0 (forked workers inherit this)

P = argparse.ArgumentParser()
P.add_argument("env_id")
P.add_argument("--out", default=None)
P.add_argument("--horizon", type=int, default=60, help="H: rollout length scored per candidate")
P.add_argument("--knots", type=int, default=7, help="K: spline knots parameterising a candidate")
P.add_argument("--samples", type=int, default=128, help="N: candidates per CEM iteration")
P.add_argument("--elite", type=int, default=16)
P.add_argument("--iters", type=int, default=2, help="CEM refits per replan")
P.add_argument("--exec-steps", type=int, default=3, help="actions executed for real per replan")
P.add_argument("--std0", type=float, default=0.25)
P.add_argument("--std-min", type=float, default=0.02)
P.add_argument("--seed", type=int, default=0)
P.add_argument("--workers", type=int, default=32)
A = P.parse_args()

TASK = A.env_id.split("-", 1)[1].rsplit("-v0", 1)[0]
ROBOT = A.env_id.split("-", 1)[0]

_worker_env = None


def _init_worker():
    global _worker_env
    _worker_env = gym.make(A.env_id, render_mode=None)
    _worker_env.reset(seed=A.seed)


def _knots_to_sequence(knots):
    """Linearly interpolate K knots into an H-step action sequence."""
    t = np.linspace(0, A.knots - 1, A.horizon)
    i = np.minimum(np.floor(t).astype(int), A.knots - 2)
    f = (t - i)[:, None]
    return knots[i] * (1 - f) + knots[i + 1] * f


def _snapshot(low):
    return (low.data.qpos.copy(), low.data.qvel.copy(), float(low.data.time), low.data.qacc_warmstart.copy())


def _restore(low, snap):
    qpos, qvel, t, warmstart = snap
    low.data.qpos[:] = qpos
    low.data.qvel[:] = qvel
    low.data.time = t
    low.data.qacc_warmstart[:] = warmstart
    mujoco.mj_forward(low.model, low.data)


def _score(arg):
    """Roll one candidate out from the snapshot and return its (shaped) value."""
    snap, knots = arg
    if _worker_env is None:
        _init_worker()
    low = _worker_env.unwrapped
    _restore(low, snap)
    seq = np.clip(_knots_to_sequence(knots), -1, 1)
    total = 0.0
    for h in range(A.horizon):
        _, r, terminated, _, _ = _worker_env.step(seq[h].astype(np.float32))
        total += r
        if terminated:
            return total - 1000.0            # falling over is never worth it
    try:                                     # terminal shaping: survive past the horizon
        return total + 20.0 * min(low.robot.head_height(), 1.65) / 1.65 \
                     + 20.0 * max(low.robot.torso_upright(), 0.0)
    except Exception:                        # noqa: BLE001  (tasks without a standing robot)
        return total


def main():
    env = gym.make(A.env_id, render_mode=None)
    low = env.unwrapped
    nu = low.model.nu
    bar = TASKS[TASK].success_bar
    max_steps = TASKS[TASK].max_episode_steps

    # Start the search from the task's own nominal pose, expressed as a normalised action.
    qpos0 = np.fromstring(TASKS[TASK].qpos0_robot[ROBOT], sep=" ")
    nominal = np.clip(2 * (qpos0[7:7 + nu] - low.action_low) / (low.action_high - low.action_low) - 1, -1, 1)
    nominal_knots = np.tile(nominal, (A.knots, 1))

    env.reset(seed=A.seed)
    mean = nominal_knots.copy()
    rng = np.random.default_rng(A.seed)
    actions, episode_return, t0 = [], 0.0, time.time()
    print(f"{A.env_id}  bar={bar}  H={A.horizon} K={A.knots} N={A.samples} elite={A.elite} "
          f"iters={A.iters} exec={A.exec_steps} std0={A.std0}", flush=True)

    with Pool(A.workers, initializer=_init_worker) as pool:
        for it in range(max_steps // A.exec_steps):
            snap = _snapshot(low)
            std = np.full((A.knots, nu), A.std0)
            for _ in range(A.iters):
                candidates = [mean, nominal_knots] + [
                    np.clip(mean + rng.normal(0, 1, (A.knots, nu)) * std, -1, 1)
                    for _ in range(A.samples - 2)
                ]
                values = np.array(pool.map(_score, [(snap, c) for c in candidates]))
                elite = np.array([candidates[i] for i in np.argsort(-values)[:A.elite]])
                mean, std = elite.mean(0), np.maximum(elite.std(0), A.std_min)

            seq = np.clip(_knots_to_sequence(mean), -1, 1)
            done = False
            for h in range(A.exec_steps):
                a = seq[h].astype(np.float32)
                actions.append(a.copy())
                _, r, terminated, truncated, _ = env.step(a)
                episode_return += r
                if terminated or truncated:
                    done = True
                    break
            if done:
                break
            mean = np.vstack([mean[1:], mean[-1:]])          # shift the plan one replan forward
            if it % 25 == 0:
                print(f"  {len(actions):4d} steps  return={episode_return:7.1f}  {time.time() - t0:.0f}s", flush=True)

    verdict = "PASS" if episode_return >= bar else "FAIL"
    print(f"\n{A.env_id}: {len(actions)} steps  return={episode_return:.1f}/{bar}  {verdict}  "
          f"({time.time() - t0:.0f}s)", flush=True)
    out = A.out or f"{TASK}_actions.npy"
    np.save(out, np.array(actions))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
