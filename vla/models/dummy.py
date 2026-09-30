"""HoldVLA: repeats the measured state as every action row, to test the pipeline without a model."""
import numpy as np

from vla.models.base import BaseVLA
from vla.protocol import ActionChunk


class HoldVLA(BaseVLA):
    def load(self):
        pass

    def infer(self, obs):
        state = obs.state["joint" if self.spec.action_space == "joint_abs" else "ee"]
        return ActionChunk(np.tile(state, (self.spec.chunk_size, 1)))
