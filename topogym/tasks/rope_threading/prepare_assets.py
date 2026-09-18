"""Generate standalone metric OBJ/GLB assets without building a simulation."""
import argparse
from pathlib import Path

from .geometry import generate_assets
from .reference import REFERENCE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REFERENCE.parent/"model")
    args = parser.parse_args()
    report = generate_assets(args.output)
    print(f'{args.output}/assembly.glb: {report["rope_length_m"]:.3f} m rope, three 138 mm apertures')


if __name__ == "__main__":
    main()
