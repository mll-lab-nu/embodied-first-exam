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
        self.instruction = self.episode_id = self.row = self.action = None
        self.step = self.inference_calls = self.holds = self.skipped = 0

    def reset(self, seed, instruction, episode_id):
        """Start an episode; ``episode_id`` is the Env's (obs["state"]["episode_id"])."""
        self.client.reset(seed)
        self.queue.clear()
        self.instruction, self.episode_id, self.row, self.action = instruction, episode_id, None, None
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
            self.row = self.queue.popleft()
            self.action, self.holds = self.adapter.action(self.row), 0
        self.step += 1
        return self.action

    def skip(self, robot, step):
        """The Env rejected this step's ee action (a target beyond its IK tolerance). As RoboTwin skips only the arm
        it cannot plan, the targets of one arm at a time, then of all arms, are replaced by the measured poses (the
        gripper commands stay) until ``step`` accepts the action, which then stays the current target. Returns the
        accepted action and ``step``'s result."""
        self.skipped += 1
        clipped = self.adapter.clipped  # candidates change only ee poses, which are never clipped
        arms = list(self.adapter.arms)
        for held in [[arm] for arm in arms] + ([arms] if len(arms) > 1 else []):
            row = self.adapter.hold(self.row, robot, held)
            action = self.adapter.action(row)
            try:
                result = step(action)
            except ValueError as error:
                rejected = error
                continue
            self.adapter.clipped = clipped
            self.row, self.action, self.holds = row, action, 0
            return action, result
        raise rejected
