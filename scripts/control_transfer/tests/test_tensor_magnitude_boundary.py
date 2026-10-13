"""Numeric policy admission must bound signed tensors without integer overflow."""

import io
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from control_public.weights import arrays


SHAPES = {"mean": (3,), "std": (3,), "w0": (3,)}


def archive(dtype, values):
    tensors = {
        "mean": np.zeros(3, dtype=dtype),
        "std": np.ones(3, dtype=dtype),
        "w0": np.asarray(values, dtype=dtype),
    }
    stream = io.BytesIO()
    np.savez_compressed(stream, **tensors)
    return stream.getvalue(), tensors


class TensorMagnitudeBoundary(unittest.TestCase):
    def test_signed_minimum_rejected_in_mixed_tensor(self):
        for dtype in (np.int32, np.int64):
            with self.subTest(dtype=dtype):
                raw, _ = archive(dtype, [0, np.iinfo(dtype).min, 1])
                with self.assertRaisesRegex(ValueError, "Invalid tensor w0"):
                    arrays(raw, SHAPES)

    def test_signed_extrema_and_outside_bounds_rejected(self):
        for dtype in (np.int32, np.int64, np.float32, np.float64):
            values = [-10001, 10001]
            if np.issubdtype(dtype, np.integer):
                values.append(np.iinfo(dtype).max)
            for value in values:
                with self.subTest(dtype=dtype, value=value):
                    raw, _ = archive(dtype, [0, value, 1])
                    with self.assertRaisesRegex(ValueError, "Invalid tensor w0"):
                        arrays(raw, SHAPES)

    def test_supported_dtypes_and_inclusive_bounds_preserved(self):
        for dtype in (np.int32, np.int64, np.float32, np.float64):
            with self.subTest(dtype=dtype):
                raw, expected = archive(dtype, [-10000, 0, 10000])
                actual = arrays(raw, SHAPES)
                for name in SHAPES:
                    self.assertEqual(actual[name].dtype, expected[name].dtype)
                    np.testing.assert_array_equal(actual[name], expected[name])

    def test_nonfinite_values_still_rejected(self):
        for dtype in (np.float32, np.float64):
            for value in (np.nan, np.inf, -np.inf):
                with self.subTest(dtype=dtype, value=value):
                    raw, _ = archive(dtype, [0, value, 1])
                    with self.assertRaisesRegex(ValueError, "Invalid tensor w0"):
                        arrays(raw, SHAPES)


if __name__ == "__main__":
    unittest.main()
