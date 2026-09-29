"""Independent named RNG streams and first-use process seed control."""
import random
import numpy as np
import pytest
from topogym.utils.variant_rng import VariantRng, seed_process


def test_named_streams_are_independent_of_consumer_order():
    rng = VariantRng(17)
    before = rng.stream("visual/cloth").normal(size=20)
    rng.stream("task/layout").uniform(size=100)
    np.testing.assert_array_equal(before, rng.stream("visual/cloth").normal(size=20))
    assert not np.array_equal(before, VariantRng(18).stream("visual/cloth").normal(size=20))


def test_process_seed_restarts_host_and_tensor_streams():
    import torch
    seed_process(13)
    expected = (random.random(), np.random.uniform(), torch.rand(4).numpy())
    seed_process(14)
    seed_process(13)
    actual = (random.random(), np.random.uniform(), torch.rand(4).numpy())
    assert expected[:2] == actual[:2]
    np.testing.assert_array_equal(expected[2], actual[2])
