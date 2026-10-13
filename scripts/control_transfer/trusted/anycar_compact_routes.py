"""Offline builder for explicitly simplified, 30-second F1-inspired layouts."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from ..components.anycarbench.tracks import Route, get_route, track_ids


def build():
    rows = {}
    for name in track_ids():
        source = get_route(name).points
        for sigma in (2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512):
            frequency = np.fft.fftfreq(len(source))
            kernel = np.exp(-2 * np.pi**2 * sigma**2 * frequency**2)
            points = np.fft.ifft(np.fft.fft(source, axis=0) * kernel[:, None], axis=0).real
            points -= points.mean(axis=0)
            eigenvalues, axes = np.linalg.eigh(np.cov(points.T))
            widening = max(1.0, float(np.sqrt(eigenvalues[1] / eigenvalues[0])) / 2.0)
            projected = points @ axes
            projected[:, 0] *= widening
            points = projected @ axes.T
            arc = np.r_[0, np.cumsum(np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1))]
            closed = np.vstack((points, points[0]))
            distance = np.linspace(0, arc[-1], 512, endpoint=False)
            points = np.column_stack([np.interp(distance, arc, closed[:, j]) for j in range(2)])
            points *= 45.0 / np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1).sum()
            points = np.round(points, 9)
            probe = object.__new__(Route)
            probe.points = points
            probe.delta = np.roll(points, -1, axis=0) - points
            probe.segment_lengths = np.linalg.norm(probe.delta, axis=1)
            probe.arc = np.r_[0, np.cumsum(probe.segment_lengths)]
            probe.length = float(probe.arc[-1])
            curvature = float(np.max(np.abs(probe.at(np.linspace(0, probe.length, 8192, endpoint=False))[:, 3])))
            if curvature <= .8:
                rows[name] = dict(points=points.tolist(), length_m=probe.length,
                                  smoothing_sigma_samples=sigma, source_samples=len(source),
                                  minor_axis_widening=widening, max_curvature_per_m=curvature,
                                  target_lap_time_s=28.0, horizon_s=30.0)
                break
        else:
            raise ValueError(f"No feasible compact layout: {name}")
    source = Path(__file__).parents[1] / 'components/anycarbench/circuits.json'
    return dict(schema='anycar-compact-routes/1', revision='compact-30s/1',
                source_catalog_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                geometry='F1-inspired: periodic smoothing and minor-axis widening, then 45m normalization. Not exact scaled circuit outlines; tight corners/crossovers may be removed.',
                routes=rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(build(), sort_keys=True, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
