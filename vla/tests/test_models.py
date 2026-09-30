"""BaseVLA loading by class path, HoldVLA and the in-process LocalClient."""
import numpy as np
import pytest

from vla.gym.client import LocalClient, PolicyError
from vla.models.base import BaseVLA, load_model
from vla.models.dummy import HoldVLA
from vla.protocol import ActionChunk, Observation


def config(action_space="joint_abs", chunk_size=4, class_path="vla.models.dummy.HoldVLA"):
    return dict(class_path=class_path, spec=dict(
        name="hold", embodiment="panda_robotiq", cameras=["agentview"], state_keys=["joint", "ee"],
        action_space=action_space, control_hz=15, chunk_size=chunk_size, execute_steps=2))


def observation():
    state = {"joint": np.arange(8, dtype=np.float32), "ee": np.arange(10, 20, dtype=np.float32)}
    return Observation({"agentview": np.zeros((480, 848, 3), np.uint8)}, state, "go", "e", 0)


class Broken(BaseVLA):
    def load(self):
        pass

    def infer(self, obs):
        raise KeyError("missing camera")


@pytest.mark.parametrize("action_space, key", [("joint_abs", "joint"), ("ee_abs", "ee")])
def test_hold_repeats_the_matching_state(action_space, key):
    obs = observation()
    chunk = HoldVLA(config(action_space)).infer(obs)
    assert isinstance(chunk, ActionChunk) and chunk.actions.dtype == np.float32
    np.testing.assert_array_equal(chunk.actions, np.tile(obs.state[key], (4, 1)))


def test_camera_images_follow_the_slot_order_and_resize_as_configured():
    images = {"agentview": np.full((480, 848, 3), 1, np.uint8), "wrist": np.full((480, 848, 3), 2, np.uint8)}
    obs = Observation(images, {}, "go", "e", 0)
    cfg = config()
    cfg["spec"]["cameras"] = ["wrist", "agentview"]
    native = HoldVLA(cfg).camera_images(obs)
    assert [image.shape for image in native] == [(480, 848, 3)] * 2 and [image[0, 0, 0] for image in native] == [2, 1]
    cfg["model"] = dict(image_hw=[180, 320], image_interpolation="area")
    resized = HoldVLA(cfg).camera_images(obs)
    assert [image.shape for image in resized] == [(180, 320, 3)] * 2 and [image[0, 0, 0] for image in resized] == [2, 1]


def test_load_model_instantiates_class_path_and_spec():
    model = load_model(config(chunk_size=6))
    assert isinstance(model, HoldVLA) and model.spec.chunk_size == 6 and model.spec.cameras == ("agentview",)


def test_local_client_forwards_to_the_model():
    client = LocalClient(HoldVLA(config()))
    client.reset(3)
    assert client.spec.name == "hold" and client.infer(observation()).actions.shape == (4, 8)
    client.close()


def test_local_client_reports_model_errors_as_policy_errors():
    client = LocalClient(Broken(config()))
    with pytest.raises(PolicyError, match="missing camera"):
        client.infer(observation())
