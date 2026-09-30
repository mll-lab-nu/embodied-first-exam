"""VLAAgent: one inference per ``execute_steps`` control steps; the rest of each chunk is discarded."""
from __future__ import annotations

from collections import deque
from uuid import uuid4

import numpy as np

from vla.gym.client import PolicyError


class VLAAgent:
    def __init__(self, client, adapter, execute_steps):
        if not 1 <= execute_steps <= client.spec.chunk_size:
            raise ValueError(f"execute_steps must be in [1, {client.spec.chunk_size}], got {execute_steps}")
        self.client, self.adapter, self.execute_steps = client, adapter, execute_steps
        self.queue = deque()
        self.instruction = self.episode_id = None
        self.step = self.inference_calls = 0

    def reset(self, seed, instruction):
        self.client.reset(seed)
        self.queue.clear()
        self.instruction, self.episode_id = instruction, uuid4().hex
        self.step = self.inference_calls = 0

    def act(self, rgb, robot):
        """Return the TopoGym action dict for this control step."""
        if not self.queue:
            obs = self.adapter.observation(rgb, robot, self.instruction, self.episode_id, self.step)
            actions = np.asarray(self.client.infer(obs).actions)
            self.inference_calls += 1
            expected = (self.client.spec.chunk_size, self.adapter.action_dim)
            if actions.shape != expected or not np.isfinite(actions).all():
                raise PolicyError(f"Expected a finite {expected} action chunk, got {actions.shape}")
            self.queue.extend(actions[:self.execute_steps])
        self.step += 1
        return self.adapter.action(self.queue.popleft())
