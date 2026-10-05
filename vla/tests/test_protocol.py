"""Wire format: bitwise array round trips and protocol version checks."""
from dataclasses import asdict

import numpy as np
import pytest

from vla.protocol import PROTOCOL_VERSION, PolicySpec, decode, encode

SPEC = dict(name="hold", embodiment="aloha", cameras=["cam_high", "cam_left_wrist"], action_space="joint_abs",
            control_hz=50, chunk_size=10, execute_steps=5)


def assert_bitwise_equal(a, b):
    assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def test_nested_arrays_round_trip_bitwise():
    rng = np.random.default_rng(0)
    image = rng.integers(0, 256, (480, 848, 3), dtype=np.uint8)
    joint = rng.standard_normal(8).astype(np.float32)
    table = rng.standard_normal((2, 3))
    msg = dict(type="infer", images={"agentview": image}, state={"joint": joint, "nested": [table, {"x": 1}]},
               instruction="pick", step=3)
    out = decode(encode(msg))
    assert_bitwise_equal(out["images"]["agentview"], image)
    assert_bitwise_equal(out["state"]["joint"], joint)
    assert_bitwise_equal(out["state"]["nested"][0], table)
    assert out["state"]["nested"][1] == {"x": 1}
    assert (out["type"], out["instruction"], out["step"]) == ("infer", "pick", 3)


def test_non_contiguous_array_round_trips():
    view = np.arange(24, dtype=np.float64).reshape(4, 6)[:, ::2].T
    assert_bitwise_equal(decode(encode({"a": view}))["a"], np.ascontiguousarray(view))


def test_decode_rejects_truncated_message():
    data = encode({"a": np.zeros(4, np.float32)})
    with pytest.raises(ValueError, match="size"):
        decode(data[:-1])


def test_spec_survives_the_wire():
    spec = PolicySpec(**SPEC)
    assert spec.cameras == ("cam_high", "cam_left_wrist") and spec.protocol_version == PROTOCOL_VERSION
    assert PolicySpec(**decode(encode(asdict(spec)))) == spec


def test_spec_rejects_a_reach_tolerance_for_joint_targets():
    with pytest.raises(ValueError, match="ee_abs"):
        PolicySpec(**dict(SPEC, reach_tolerance_m=0.005))
