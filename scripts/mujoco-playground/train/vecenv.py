"""Multiprocess vector env over qenv.Env for rsl_rl (VecEnv interface), CPU only.

W worker processes, E envs each; actions, observations, rewards and done flags go through shared memory, one pipe
message per step per worker. Episodes auto-reset; reaching episode_length is a time-out (truncation)."""
from __future__ import annotations

import multiprocessing as mp
from multiprocessing import shared_memory

import numpy as np
import torch
from tensordict import TensorDict

import qenv


def _arr(shm, shape, dtype=np.float32):
    return np.ndarray(shape, dtype=dtype, buffer=shm.buf)


def _worker(name, seed, lo, hi, shm_names, shapes, conn, env_kwargs):
    import os
    os.environ["OMP_NUM_THREADS"] = "1"
    envs = [qenv.ENVS[name](seed=seed + i, **env_kwargs) for i in range(lo, hi)]
    shms = {k: shared_memory.SharedMemory(name=v) for k, v in shm_names.items()}
    A = _arr(shms["act"], shapes["act"]); O = _arr(shms["obs"], shapes["obs"]); P = _arr(shms["priv"], shapes["priv"])
    R = _arr(shms["rew"], shapes["rew"]); D = _arr(shms["done"], shapes["done"]); T = _arr(shms["trunc"], shapes["trunc"])
    t = np.zeros(hi - lo, int)
    while True:
        cmd = conn.recv()
        if cmd == "reset":
            for j, e in enumerate(envs):
                o, p = e.reset(); O[lo + j], P[lo + j] = o, p; t[j] = 0
        elif cmd == "step":
            for j, e in enumerate(envs):
                o, p, r, done = e.step(A[lo + j].astype(np.float64))
                t[j] += 1
                trunc = (not done) and t[j] >= e.episode_length
                if not np.all(np.isfinite(o)) or not np.isfinite(r):
                    done, r = True, 0.0
                R[lo + j] = r; D[lo + j] = float(done or trunc); T[lo + j] = float(trunc)
                if done or trunc:
                    o, p = e.reset(); t[j] = 0
                O[lo + j], P[lo + j] = o, p
        elif cmd == "close":
            break
        conn.send("ok")


class CpuVecEnv:
    def __init__(self, name: str, num_envs: int = 2048, workers: int = 16, seed: int = 0, env_kwargs=None):
        env_kwargs = env_kwargs or {}
        probe = qenv.ENVS[name](seed=0, **env_kwargs)
        self.num_envs, self.num_actions = num_envs, probe.m.nu
        self.max_episode_length = probe.episode_length
        self.device = "cpu"; self.cfg = {"env": name}
        o, p = probe.reset()
        shapes = {"act": (num_envs, self.num_actions), "obs": (num_envs, len(o)), "priv": (num_envs, len(p)),
                  "rew": (num_envs,), "done": (num_envs,), "trunc": (num_envs,)}
        self._shm = {k: shared_memory.SharedMemory(create=True, size=int(np.prod(s)) * 4) for k, s in shapes.items()}
        self.A, self.O, self.P = (_arr(self._shm[k], shapes[k]) for k in ("act", "obs", "priv"))
        self.R, self.D, self.T = (_arr(self._shm[k], shapes[k]) for k in ("rew", "done", "trunc"))
        ctx = mp.get_context("fork")
        bounds = np.linspace(0, num_envs, workers + 1).astype(int)
        self.conns, self.procs = [], []
        for w in range(workers):
            a, b = ctx.Pipe()
            pr = ctx.Process(target=_worker, args=(name, seed * 100003, bounds[w], bounds[w + 1],
                                                    {k: v.name for k, v in self._shm.items()}, shapes, b, env_kwargs),
                             daemon=True)
            pr.start(); self.conns.append(a); self.procs.append(pr)
        self._broadcast("reset")
        self.ep_ret = np.zeros(num_envs); self.ep_len = np.zeros(num_envs); self.done_rets = []; self.done_lens = []

    def _broadcast(self, cmd):
        for c in self.conns: c.send(cmd)
        for c in self.conns: c.recv()

    def _obs(self):
        return TensorDict({"state": torch.from_numpy(self.O.copy()), "privileged_state": torch.from_numpy(self.P.copy())},
                          batch_size=[self.num_envs])

    def get_observations(self):
        return self._obs()

    def step(self, actions: torch.Tensor):
        self.A[:] = torch.clip(actions, -1.0, 1.0).detach().cpu().numpy()
        self._broadcast("step")
        rew, done = self.R.copy(), self.D.copy()
        self.ep_ret += rew; self.ep_len += 1
        for i in np.nonzero(done)[0]:
            self.done_rets.append(self.ep_ret[i]); self.done_lens.append(self.ep_len[i]); self.ep_ret[i] = 0; self.ep_len[i] = 0
        self.done_rets = self.done_rets[-200:]; self.done_lens = self.done_lens[-200:]
        info = {"time_outs": torch.from_numpy(self.T.copy()), "log": {}}
        return self._obs(), torch.from_numpy(rew), torch.from_numpy(done), info

    def close(self):
        try:
            self._broadcast("close")
        except Exception:
            pass
        for s in self._shm.values():
            s.close(); s.unlink()
