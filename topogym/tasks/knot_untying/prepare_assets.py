"""Generate the open trefoil reference mesh and its geometric certificate."""
import argparse
from pathlib import Path

from .geometry import KnotLayout, generate_assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("assets/tasks/knot_untying/trefoil_v1/geometry"))
    parser.add_argument("--handedness", choices=("left", "right"), default="right")
    args = parser.parse_args()
    _, report = generate_assets(args.output, KnotLayout(handedness=args.handedness))
    print(f"Open trefoil: {report['rope_length_m']:.3f} m, "
          f"surface gap {report['minimum_nonlocal_surface_gap_m']*1000:.2f} mm; {args.output}")


if __name__ == "__main__":
    main()
