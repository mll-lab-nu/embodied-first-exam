"""VLAAgent: one inference per ``execute_steps`` executed targets; the rest of each chunk is discarded.

With ``spec.reach_tolerance_m`` > 0 (ee_abs) each target is held until every TCP is that close, for at most
MAX_HOLD_STEPS extra control steps, as RoboTwin's evaluation executes each target to completion.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from vla.gym.client import PolicyError

MAX_HOLD_STEPS = 10


class VLAAgent:
    def __init__(self, client, adapter, execute_steps):
        if not 1 <= execute_steps <= client.spec.chunk_size:
            raise ValueError(f"execute_steps must be in [1, {client.spec.chunk_size}], got {execute_steps}")
        self.client, self.adapter, self.execute_steps = client, adapter, execute_steps
        self.queue = deque()
        self.instruction = self.episode_id = self.row = None
        self.step = self.inference_calls = self.holds = self.skipped = 0

    def reset(self, seed, instruction, episode_id):
        """Start an episode; ``episode_id`` is the Env's (obs["state"]["episode_id"])."""
        self.client.reset(seed)
        self.queue.clear()
        self.instruction, self.episode_id, self.row = instruction, episode_id, None
        self.step = self.inference_calls = self.holds = self.skipped = 0

    def act(self, rgb, robot):
        """Return the TopoGym action dict for this control step."""
        tolerance = self.client.spec.reach_tolerance_m
        if (self.row is not None and tolerance > 0 and self.holds < MAX_HOLD_STEPS
                and not self.adapter.reached(self.row, robot, tolerance)):
            self.holds += 1
        else:
            if not self.queue:
                obs = self.adapter.observation(rgb, robot, self.instruction, self.episode_id, self.step)
                actions = np.asarray(self.client.infer(obs).actions)
                self.inference_calls += 1
                expected = (self.client.spec.chunk_size, self.adapter.action_dim)
                if actions.shape != expected or not np.isfinite(actions).all():
                    raise PolicyError(f"Expected a finite {expected} action chunk, got {actions.shape}")
                self.queue.extend(actions[:self.execute_steps])
            self.row, self.holds = self.queue.popleft(), 0
        self.step += 1
        return self.adapter.action(self.row)

    def skip(self, robot):
        """The Env rejected the current ee target (beyond its IK tolerance): drop the target and return an action
        that holds the arms at their measured poses with its gripper openings, as RoboTwin's evaluation skips a
        target it cannot plan."""
        action = self.adapter.hold(self.row, robot)
        self.row, self.skipped = None, self.skipped + 1
        self.step += 1
        return action
