#!/usr/bin/env python3
"""Lossless optional array reuse in the shared committed-tick evidence writer."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.simulator.rollout_simulation.evidence import EvidenceError, SegmentEvidence
from topogym.planning.interlocked_claws.evidence import decode_record


class ArrayReuse(unittest.TestCase):
    def writer(self, root, **kwargs):
        env = SimpleNamespace(config={}, _asset_build=SimpleNamespace(sha256={}),
                              episode_metadata={}, timing_spec={})
        return SegmentEvidence(Path(root), env, **kwargs)

    def rows(self, root):
        private = Path(root)/'private'
        encoded = [json.loads(line) for line in (private/'physics_states.jsonl').read_text().splitlines()]
        return encoded, [decode_record(row, private) for row in encoded]

    def test_default_still_writes_an_independent_chunk_for_every_tick(self):
        with tempfile.TemporaryDirectory() as root:
            w = self.writer(root)
            for tick in range(3):
                w.tick(dict(tick=tick, values=np.zeros(128)), segment_id=1)
            w.close()
            self.assertEqual(w.array_chunks, 3)
            self.assertEqual([r['tick'] for r in self.rows(root)[1]], [0, 1, 2])

    def test_dynamic_measurements_and_unchanged_topology_roundtrip_for_every_tick(self):
        with tempfile.TemporaryDirectory() as root:
            w = self.writer(root, deduplicate_arrays=True)
            topology = np.arange(512, dtype=np.int64).reshape(128, 4)
            positions = np.zeros((128, 3))
            for tick in range(4):
                positions[0, 0] = tick
                w.tick(dict(tick=tick, world=dict(elements=topology, position=positions)), segment_id=1)
            w.close()
            encoded, decoded = self.rows(root)
            self.assertEqual(len(decoded), 4)
            self.assertEqual(w.array_references_reused, 3)
            self.assertEqual(len({r['world']['elements']['array_file'] for r in encoded}), 1)
            for tick, r in enumerate(decoded):
                self.assertEqual(r['world']['position'][0, 0], tick)
                np.testing.assert_array_equal(r['world']['elements'], topology)
            # Mutating the caller's arrays after writes cannot alter any archived tick.
            topology[:] = -1; positions[:] = -1
            self.assertGreaterEqual(self.rows(root)[1][0]['world']['elements'].min(), 0)

    def test_signed_zero_dtype_shape_and_noncontiguous_values_preserve_exact_bits(self):
        with tempfile.TemporaryDirectory() as root:
            w = self.writer(root, deduplicate_arrays=True)
            positive = np.zeros(128)
            negative = positive.copy(); negative[0] = -0.
            values = [positive, negative, negative.astype('>f8'), negative.reshape(32, 4),
                      np.arange(256, dtype=float).reshape(16, 16).T]
            for tick, value in enumerate(values):
                w.tick(dict(tick=tick, data=value), segment_id=1)
            w.close()
            self.assertEqual(w.array_chunks, len(values))
            for expected, actual in zip(values, self.rows(root)[1], strict=True):
                self.assertEqual(actual['data'].dtype, expected.dtype)
                self.assertEqual(actual['data'].shape, expected.shape)
                self.assertEqual(actual['data'].tobytes(), expected.tobytes())

    def test_all_reused_arrays_keep_ticks_without_creating_empty_chunks(self):
        with tempfile.TemporaryDirectory() as root:
            w = self.writer(root, deduplicate_arrays=True)
            for tick in range(5):
                w.tick(dict(tick=tick, values=np.ones(128)), segment_id=1)
            w.close()
            self.assertEqual(w.ticks, 5)
            self.assertEqual(w.array_chunks, 1)
            self.assertEqual([r['tick'] for r in self.rows(root)[1]], list(range(5)))
            chunk = next((Path(root)/'private/arrays').glob('*.npz'))
            chunk.unlink()
            with self.assertRaises(FileNotFoundError):
                self.rows(root)

    def test_failed_write_cannot_publish_references_to_uncommitted_data(self):
        with tempfile.TemporaryDirectory() as root:
            w = self.writer(root, deduplicate_arrays=True)
            w.tick(dict(tick=0, values=np.ones(128)), segment_id=1)
            with patch.object(w, 'write', side_effect=OSError('injected disk failure')):
                with self.assertRaises(EvidenceError):
                    w.tick(dict(tick=1, values=np.zeros(128)), segment_id=1)
            w.tick(dict(tick=2, values=np.zeros(128)), segment_id=1)
            w.close()
            encoded, decoded = self.rows(root)
            self.assertEqual([r['tick'] for r in decoded], [0, 2])
            # The failed chunk remains unreferenced; the later successful tick owns its own chunk.
            self.assertEqual(encoded[-1]['values']['chunk_id'], 2)
            np.testing.assert_array_equal(decoded[-1]['values'], np.zeros(128))


if __name__ == '__main__':
    unittest.main()
