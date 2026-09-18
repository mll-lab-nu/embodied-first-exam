"""Generate the CLASSIC reconstruction without importing Genesis."""
import argparse
from .geometry import ASSET_ROOT, generate_assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ASSET_ROOT / "geometry"))
    parser.add_argument("--scale", type=float, default=1.)
    parser.add_argument("--finish", choices=("wood", "metal"), default="wood")
    args = parser.parse_args()
    _, report = generate_assets(args.output, args.scale, finish=args.finish)
    print(f"Prepared assets: {args.output}", flush=True)
    print(f"10 spikes; initial clearance {report['initial_pose']['minimum_conservative_clearance_m']*1000:.3f} mm; solution unverified", flush=True)


if __name__ == "__main__":
    main()
