"""Offline metadata builder; generation reads its output with standard library only."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from ..components.anycarbench.tracks import get_route, track_ids


def build():
    folder = Path(__file__).parents[1] / 'components' / 'anycarbench'
    routes = {}
    for name in track_ids():
        route = get_route(name)
        horizon_steps = math.ceil((route.length / 0.85 + 2.5) / 0.02)
        routes[name] = dict(scaled_length_m=route.length, horizon_steps=horizon_steps,
                            horizon_s=horizon_steps * 0.02)
    return dict(schema='anycar-route-lengths/1',
                catalog_sha256=hashlib.sha256((folder / 'circuits.json').read_bytes()).hexdigest(),
                geometry='Existing curvature-feasible Route geometry, unchanged',
                routes=routes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(build(), indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
