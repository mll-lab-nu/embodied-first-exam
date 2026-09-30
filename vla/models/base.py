"""Model wrapper interface: standard Observation in, standard ActionChunk out."""
from __future__ import annotations

from abc import ABC, abstractmethod
import importlib

from vla.protocol import ActionChunk, Observation, PolicySpec


class BaseVLA(ABC):
    """One subclass per model. It converts the standard messages to the official inference code's inputs
    and its outputs back to absolute targets (relative/absolute, gripper direction, frames)."""

    def __init__(self, config):
        self.config = config  # the model config: class_path, checkpoint, port, spec, model
        self.spec = PolicySpec(**config["spec"])

    @abstractmethod
    def load(self) -> None:
        """Load the checkpoint onto the GPU."""

    @abstractmethod
    def infer(self, obs: Observation) -> ActionChunk:
        ...

    def reset(self, seed: int) -> None:
        """Start an episode: clear history frames and seed sampling."""


def load_model(config) -> BaseVLA:
    """Instantiate ``config["class_path"]`` (no registry) and load its checkpoint."""
    module, name = config["class_path"].rsplit(".", 1)
    model = getattr(importlib.import_module(module), name)(config)
    model.load()
    return model
