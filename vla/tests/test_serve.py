"""Model server in a subprocess: RemoteClient matches LocalClient bitwise; errors do not stop the server."""
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import numpy as np
import pytest
from omegaconf import OmegaConf

from vla.config import load_yaml
from vla.gym.client import LocalClient, PolicyError, RemoteClient
from vla.models.dummy import HoldVLA
from vla.protocol import ActionChunk, Observation

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "vla/configs/models/panda_robotiq/hold_panda.yaml"


class ScalarVLA(HoldVLA):
    """Returns a NumPy scalar instead of an array, which the wire format cannot encode."""

    def infer(self, obs):
        return ActionChunk(np.float32(0.0))


def free_port():
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


def connect(address, deadline_s=60):
    start = time.monotonic()
    while True:
        try:
            return RemoteClient(address)
        except ConnectionRefusedError:
            if time.monotonic() - start > deadline_s:
                raise
            time.sleep(0.2)


@pytest.fixture(scope="module")
def address():
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "vla.models.serve", "--config", str(CONFIG), "--port", str(port)],
                              cwd=ROOT)
    yield f"localhost:{port}"
    server.terminate()
    server.wait(timeout=30)


def observation(step=0, joint=None):
    rng = np.random.default_rng(step)
    joint = rng.standard_normal(8).astype(np.float32) if joint is None else joint
    images = {name: rng.integers(0, 256, (480, 848, 3), dtype=np.uint8) for name in ("agentview", "wrist")}
    return Observation(images, {"joint": joint}, "go", "e", step)


def test_remote_chunks_equal_local_chunks_bitwise(address):
    local = LocalClient(HoldVLA(load_yaml(CONFIG)))
    remote = connect(address)
    assert remote.spec == local.spec
    remote.reset(0)
    for step in range(3):
        obs = observation(step)
        expected, actual = local.infer(obs).actions, remote.infer(obs).actions
        assert actual.dtype == expected.dtype and actual.tobytes() == expected.tobytes()
    remote.close()


def test_model_errors_are_answered_and_the_server_keeps_serving(address):
    remote = connect(address)
    with pytest.raises(PolicyError, match="KeyError"):
        remote.infer(Observation({}, {"ee": np.zeros(10, np.float32)}, "go", "e", 0))
    assert remote.infer(observation()).actions.shape == (10, 8)
    remote.close()


def test_server_accepts_the_next_client_after_a_disconnect(address):
    connect(address).close()
    remote = connect(address)
    assert remote.infer(observation()).actions.shape == (10, 8)
    remote.close()


def test_requests_after_close_raise_policy_error(address):
    remote = connect(address)
    remote.close()
    with pytest.raises(PolicyError):
        remote.reset(0)


def test_a_killed_server_raises_a_readable_policy_error_at_once():
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "vla.models.serve", "--config", str(CONFIG), "--port", str(port)],
                              cwd=ROOT)
    remote = connect(f"localhost:{port}")
    server.kill()
    server.wait(timeout=30)
    errors = []

    def infer():
        try:
            remote.infer(observation())
        except PolicyError as error:
            errors.append(str(error))

    thread = threading.Thread(target=infer, daemon=True)
    thread.start()
    thread.join(10)  # the client has no reply timeout, so a hang shows up here
    assert errors and errors[0].split(": ", 1)[1].split("(")[0] in {"EOFError", "BrokenPipeError",
                                                                    "ConnectionResetError"}


def test_unencodable_reply_is_answered_as_an_error(tmp_path):
    config = load_yaml(CONFIG)
    config.class_path = "vla.tests.test_serve.ScalarVLA"
    OmegaConf.save(config, tmp_path / "scalar.yaml")
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "vla.models.serve", "--config", str(tmp_path / "scalar.yaml"),
                               "--port", str(port)], cwd=ROOT)
    try:
        remote = connect(f"localhost:{port}")
        with pytest.raises(PolicyError, match="TypeError"):
            remote.infer(observation())
        remote.reset(0)  # the server is still answering
        remote.close()
    finally:
        server.terminate()
        server.wait(timeout=30)
