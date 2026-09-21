"""Load a fixed compact toy instance and optionally render scene previews."""

import argparse
from pathlib import Path

from omegaconf import OmegaConf

from topogym.tasks.buzz_wire_3d.geometry import BuzzWireLayout, generate_assets
from topogym.tasks.buzz_wire_3d.physics import ROOT, save
from topogym.tasks.buzz_wire_3d.verification import verify_route


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--family", choices=["baseline", "F1", "F2", "F3"], default="baseline"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--style", choices=["wood-v1", "toy-v2"], default="wood-v1")
    args = parser.parse_args()
    if args.family == "F1" and args.style != "toy-v2":
        parser.error("F1 is available in toy-v2 style; use --style toy-v2")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    suffix = "compact_toy_s70_v2" if args.style == "toy-v2" else "compact_wood_s70_v1"
    instance = f"{args.family}_{suffix}"
    source = ROOT / "assets/tasks/buzz_wire_3d" / instance / "scene_config.yaml"
    cfg = OmegaConf.load(source)
    cfg.run.output = str(output)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    route, geometry = generate_assets(
        output / "assets",
        BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True)),
    )
    proof = verify_route(route)
    save(
        output / "report.json",
        dict(
            family=args.family,
            instance_id=instance,
            passed=proof["passed"],
            geometry=geometry,
            clearance=proof,
            source_config=str(source),
            robot_reachability_verified=False,
            physical_execution_verified=False,
        ),
    )
    if not proof["passed"]:
        raise RuntimeError("Compact geometry rejected; see report.json")
    if args.render:
        from topogym.tasks.buzz_wire_3d.compact_render import render

        render(output, output / "preview")
    print(output / "report.json")


if __name__ == "__main__":
    main()
