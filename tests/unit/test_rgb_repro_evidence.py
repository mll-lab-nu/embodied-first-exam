"""Check evidence arithmetic and lossless output without a renderer/GPU."""

import json

import numpy as np
import pytest
from PIL import Image

from rgb_repro_evidence import save_rgb_comparison


def test_difference_distribution_and_lossless_roundtrip(tmp_path):
    a = np.zeros((2, 3, 3), dtype=np.uint8)
    a[0, 1, 0] = 255
    b = a.copy()
    b[0, 1, 0] = 0
    b[1, 2, 2] = 2
    folder = tmp_path / "comparison"
    result = save_rgb_comparison(folder, {"camera": a}, {"camera": b})
    row = result["cameras"]["camera"]
    assert not row["bitwise_equal"]
    assert row["changed_pixel_count"] == 2
    assert row["changed_pixel_fraction"] == pytest.approx(2 / 6)
    assert row["mean_absolute_channel_error"] == pytest.approx(257 / 18)
    assert row["max_absolute_channel_error"] == 255
    assert row["changed_bbox_xyxy"] == [1, 0, 3, 2]
    assert row["pixel_fraction_above"] == {"1": 2 / 6, "2": 1 / 6, "5": 1 / 6, "10": 1 / 6}
    for label, expected in (("A", a), ("A_again", b)):
        with Image.open(folder / row["files"][label]["path"]) as saved:
            np.testing.assert_array_equal(np.asarray(saved), expected)
    with Image.open(folder / "camera/max_error_x16.png") as heatmap:
        assert np.asarray(heatmap)[0, 1] == 255
        assert np.asarray(heatmap)[1, 2] == 32
    assert json.loads((folder / "comparison.json").read_text()) == result


def test_equal_camera_is_retained_alongside_failed_camera(tmp_path):
    a = np.zeros((2, 2, 3), dtype=np.uint8)
    result = save_rgb_comparison(tmp_path / "comparison", {"equal": a, "different": a},
                                 {"equal": a.copy(), "different": a + 1})
    row = result["cameras"]["equal"]
    assert row["bitwise_equal"] and row["changed_bbox_xyxy"] is None
    assert row["changed_pixel_count"] == row["max_absolute_channel_error"] == 0
    assert not result["cameras"]["different"]["bitwise_equal"]


def test_camera_mismatch_is_not_silently_ignored(tmp_path):
    a = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="camera sets"):
        save_rgb_comparison(tmp_path / "comparison", {"camera": a}, {"other": a})
