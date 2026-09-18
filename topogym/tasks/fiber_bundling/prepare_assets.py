"""Generate the reproducible reference assets without importing Genesis."""
import argparse
from pathlib import Path
from .geometry import FiberLayout, generate_assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("assets/tasks/fiber_bundling/anchored_v2/geometry"))
    parser.add_argument("--legacy-free", action="store_true", help="Rebuild the historical detached-cable model")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fiber-count", type=int, default=8)
    args = parser.parse_args()
    from .anchored_geometry import generate_anchored_assets
    generate = generate_assets if args.legacy_free else generate_anchored_assets
    _, report = generate(args.output, FiberLayout(seed=args.seed, fiber_count=args.fiber_count))
    print(f"Assets: {args.output}; trunk radial clearance: {report['trunk_radial_clearance_m']*1000:.3f} mm")


if __name__ == "__main__":
    main()
