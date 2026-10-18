"""Operator visualization rejects mismatched truth and cannot replace feedback video."""

import hashlib
import json
from pathlib import Path
import tempfile
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.neuralfly_wind_demo import load_episode, render


class WindDemoTests(unittest.TestCase):
    def test_trace_identity_timing_and_calibration_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            state = np.zeros((10, 18), dtype="<f8")
            state[:, 0] = 0.02 * (1 + np.arange(10))
            state[:, 4] = 1
            record = {
                "revision": "neuralfly-cpu/4",
                "dynamics": {"dynamics_revision": "vector-wind/1"},
                "state_sha256": hashlib.sha256(state.tobytes()).hexdigest(),
            }
            np.savez(folder / "trajectory.npz", state=state)
            (folder / "record.json").write_text(json.dumps(record))
            wind = np.tile([1.0, -2.0, 0.0], (len(state), 1))
            np.savez(folder / "wind.npz", time=state[:, 0], velocity_world=wind)
            np.testing.assert_array_equal(load_episode(folder)[2], wind)
            np.savez(folder / "wind.npz", time=state[:, 0] - 0.02, velocity_world=wind)
            with self.assertRaises(ValueError):
                load_episode(folder)
            np.savez(folder / "wind.npz", time=state[:, 0], velocity_world=wind)
            state[0, 1] = 2
            np.savez(folder / "trajectory.npz", state=state)
            with self.assertRaises(ValueError):
                load_episode(folder)
            record["revision"] = "neuralfly-cpu/3"
            (folder / "record.json").write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                load_episode(folder)

    def test_never_overwrites_existing_artifact_or_agent_video(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            existing = folder / "operator-demo.mp4"
            existing.write_bytes(b"preserve")
            for out in (folder / "video.mp4", existing):
                with self.assertRaises(ValueError):
                    render(folder, out, folder)
            self.assertEqual(existing.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
