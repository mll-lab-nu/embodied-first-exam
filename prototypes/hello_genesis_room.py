import argparse
import os

import genesis as gs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal Genesis room prototype.")
    parser.add_argument(
        "--viewer",
        action="store_true",
        help="Open the Genesis viewer. Requires a graphical display.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=200,
        help="Number of scene.step() calls to run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    has_display = bool(os.environ.get("DISPLAY"))

    if args.viewer and not has_display:
        raise SystemExit(
            "No DISPLAY detected on this node. Re-run without --viewer, or use a node with GUI/X forwarding."
        )

    gs.init(backend=gs.cpu, logging_level="warning")
    scene = gs.Scene(show_viewer=args.viewer)
    scene.add_entity(gs.morphs.Plane())
    scene.add_entity(gs.morphs.Box(pos=(0.55, 0.0, 0.375), size=(0.80, 0.60, 0.75), fixed=True))
    scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml", pos=(0.15, 0.0, 0.75)))
    scene.build()
    for _ in range(args.steps):
        scene.step()

    mode = "viewer" if args.viewer else "headless"
    print(f"hello_genesis_room finished in {mode} mode after {args.steps} steps.")


if __name__ == "__main__":
    main()
