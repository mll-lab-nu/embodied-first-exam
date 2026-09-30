"""Model wrapper interface: standard Observation in, standard ActionChunk out."""
from __future__ import annotations

from abc import ABC, abstractmethod
import importlib

import cv2
import numpy as np

from vla.protocol import ActionChunk, Observation, PolicySpec

INTERPOLATIONS = {"area": cv2.INTER_AREA, "linear": cv2.INTER_LINEAR}


class BaseVLA(ABC):
    """One subclass per model. It converts the standard messages to the official inference code's inputs
    and its outputs back to absolute targets (relative/absolute, gripper direction, frames)."""

    def __init__(self, config):
        self.config = config  # the model config: class_path, checkpoint, spec, model
        self.spec = PolicySpec(**config["spec"])

    @abstractmethod
    def load(self) -> None:
        """Load the checkpoint onto the GPU."""

    @abstractmethod
    def infer(self, obs: Observation) -> ActionChunk:
        ...

    def reset(self, seed: int) -> None:
        """Start an episode, e.g. seed the sampling noise."""

    def camera_images(self, obs: Observation) -> list:
        """The frames of ``spec.cameras`` in the order of the model's image slots. With ``model.image_aspect``
        [width, height] set they keep only their center at the aspect ratio of the training frames; with
        ``model.image_hw`` set they are then resized to it, with ``model.image_interpolation``, as the model's official
        client does."""
        images = [obs.images[camera] for camera in self.spec.cameras]
        options = self.config.get("model") or {}
        if "image_aspect" in options:
            images = [center_crop(image, *options["image_aspect"]) for image in images]
        if "image_hw" not in options:
            return images
        height, width = options["image_hw"]
        flag = INTERPOLATIONS[options["image_interpolation"]]
        return [cv2.resize(image, (width, height), interpolation=flag) for image in images]


def center_crop(image, width, height):
    """The largest centered part of ``image`` with the aspect ratio width:height."""
    rows, cols = image.shape[:2]
    keep_rows, keep_cols = min(rows, round(cols * height / width)), min(cols, round(rows * width / height))
    top, left = (rows - keep_rows) // 2, (cols - keep_cols) // 2
    return np.ascontiguousarray(image[top:top + keep_rows, left:left + keep_cols])


def load_model(config) -> BaseVLA:
    """Instantiate ``config["class_path"]`` (no registry) and load its checkpoint."""
    module, name = config["class_path"].rsplit(".", 1)
    model = getattr(importlib.import_module(module), name)(config)
    model.load()
    return model
