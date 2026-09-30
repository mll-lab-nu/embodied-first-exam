"""HoldVLA: repeats the measured state as every action row, to test the pipeline without a model."""
import numpy as np

from vla.models.base import BaseVLA
from vla.protocol import STATE_KEY, ActionChunk


class HoldVLA(BaseVLA):
    def load(self):
        pass

    def infer(self, obs):
        state = obs.state[STATE_KEY[self.spec.action_space]]
        return ActionChunk(np.tile(state, (self.spec.chunk_size, 1)))
