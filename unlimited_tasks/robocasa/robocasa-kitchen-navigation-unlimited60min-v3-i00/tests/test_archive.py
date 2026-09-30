"""Exercise untrusted NPY headers before any simulator allocation."""
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from casa_traj import load_actions


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "trajectory.npz"

    def test_valid(self):
        a = np.zeros((4, 3))
        np.savez_compressed(self.path, actions=a)
        np.testing.assert_array_equal(load_actions(self.path), a)

    def test_invalid(self):
        for a in [np.zeros((0, 3)), np.zeros((1201, 3)), np.zeros((2, 7)),
                  np.full((2, 3), np.nan), np.full((2, 3), 1.01),
                  np.zeros((2, 3), dtype=object), np.full((2, 3), np.iinfo(np.int64).min)]:
            with self.subTest(shape=a.shape, dtype=a.dtype):
                np.savez(self.path, actions=a)
                with self.assertRaises(ValueError):
                    load_actions(self.path)

    def test_forged_huge_array(self):
        stream = io.BytesIO()
        np.lib.format.write_array_header_1_0(stream, dict(descr="<f8", fortran_order=False, shape=(10**12, 3)))
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("actions.npy", stream.getvalue())
        with self.assertRaises(ValueError):
            load_actions(self.path)

    def test_duplicate_member(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("actions.npy", b"")
            archive.writestr("extra.npy", b"")
        with self.assertRaises(ValueError):
            load_actions(self.path)


if __name__ == "__main__":
    unittest.main()
