"""Reference solution for h1-sit_simple-v0. Runs inside Session.exec_code(): `session` is in scope.

The action sequence beside this file was produced by training-free CEM-MPC (cross-entropy-method
sampling over spline-parameterised action sequences, replanned every 3 steps against the simulator
itself), then recorded as an open-loop trajectory. HumanoidBench ships no reference solutions of its
own -- it is an RL benchmark, so upstream's "solutions" are training curves, not runnable code.
cem_mpc.py beside this file regenerates it.

Stepping the actions through the session is what records them, so this file is a replay, not a search:
the oracle is deterministic and costs one episode.
"""
import numpy as np

for action in np.load("/solution/sit_simple_actions.npy"):
    session.step(action)  # noqa: F821  (injected by Session.exec_code)
