"""Generate registered open-knot meshes and their geometric certificates."""
import argparse
from pathlib import Path

from .geometry import FAMILY_KNOTS, KnotLayout, generate_assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--handedness", choices=("left", "right"), default="right")
    parser.add_argument('--family', choices=tuple(FAMILY_KNOTS), default='overhand_trefoil')
    from .families import ROOT, ROUTE_PROFILES, template_config
    parser.add_argument('--route-profile', choices=tuple(ROUTE_PROFILES))
    args = parser.parse_args()
    from omegaconf import OmegaConf
    template = template_config(args.family, args.route_profile)
    geometry = OmegaConf.to_container(template.task.geometry, resolve=True)
    asset_name = (template.task.variant if args.route_profile else
                  'trefoil_v1' if args.family == 'overhand_trefoil' else f'{args.family}_v1')
    output = args.output or ROOT/'assets/tasks/knot_untying'/asset_name/'geometry'
    _, report = generate_assets(output, KnotLayout(**geometry, handedness=args.handedness))
    print(f"{args.family}: {report['rope_length_m']:.3f} m, "
          f"surface gap {report['minimum_nonlocal_surface_gap_m']*1000:.2f} mm; {output}")


if __name__ == "__main__":
    main()
