#!/usr/bin/env python3
"""Compare the local v15 Orbits scene with the source's detached v8 candidate (no physics).

Both scenes are built in disposable Envs at their birth state with the same Nyx cameras, plus a
same-scale engineering drawing; the result is a single review image. Nothing is written back to
the Task. Example (inside the topogym CUDA image, repository mounted at /work):

  python scripts/preview_orbits_geometry.py --variation easy --output runs/oracle_dev/orbits_bigring_preview
"""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Source geometry is an explicit development preview only, never an installed task default.
BASE_LENGTH = {"easy": .581, "medium": .727, "hard": .874}
CORD_LENGTH = {"easy": 2.20, "medium": 3.00, "hard": 3.60}


def candidate(variation, cord_length=None):
    return dict(geometry=dict(ring_radius_m=.1353, post_spacing_m=.1465, ring_step_m=.1059,
                              lowest_ring_z_m=.1613, base_width_m=.329,
                              base_length_m=BASE_LENGTH[variation], handle_x_m=.53 if variation == 'hard' else .49),
                cord_profile=dict(handle_x_m=.47 if variation == 'hard' else .44,
                                  cord_length_m=CORD_LENGTH[variation] if cord_length is None else cord_length))


def memory_watchdog(limit=.90):
    """Stop only this process when system memory reaches the limit."""
    def watch():
        while True:
            with open("/proc/meminfo") as f:
                info = {line.split(":")[0]: int(line.split()[1]) for line in f}
            if 1-info["MemAvailable"]/info["MemTotal"] >= limit:
                print(f"memory >= {limit:.0%}; stopping this preview", flush=True)
                os._exit(3)
            time.sleep(2)
    threading.Thread(target=watch, daemon=True).start()


def stitch(rows, output):
    from PIL import Image, ImageDraw
    tiles = [[Image.open(path) for path in row] for _, row in rows]
    width = max(sum(t.width for t in row) for row in tiles)
    height = sum(max(t.height for t in row)+36 for row in tiles)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    y = 0
    for (label, _), row in zip(rows, tiles):
        draw.text((10, y+10), label, fill=(0, 0, 0))
        x = 0
        for tile in row:
            sheet.paste(tile, (x, y+36))
            x += tile.width
        y += max(t.height for t in row)+36
    sheet.save(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variation", choices=sorted(BASE_LENGTH), default="easy")
    parser.add_argument("--cord-length", type=float, default=None, help="detached candidate only; defaults to the source v8 profile")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    memory_watchdog()
    from topogym.planning.calibration_tools.adapters import orbits
    from topogym.tasks.orbits.orbits_easy import OrbitsEasyTask
    from topogym.tasks.orbits.orbits_medium import OrbitsMediumTask
    from topogym.tasks.orbits.orbits_hard import OrbitsHardTask
    task_class = dict(easy=OrbitsEasyTask, medium=OrbitsMediumTask, hard=OrbitsHardTask)[args.variation]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    parameters = candidate(args.variation, args.cord_length)
    (output / "candidate.json").write_text(json.dumps(parameters, indent=1))
    drawing = orbits.plot_layout_comparison(task_class(), parameters, output / "layout_comparison.png")
    config = dict(variation_id=args.variation, seed=args.seed, compute_backend="cuda")
    current = orbits.render_preview(config, None, output / "current")
    enlarged = orbits.render_preview(config, parameters, output / "candidate")
    rows = [(f"current orbits_{args.variation} (birth state, Nyx)",
             [current["frames"][c]["raw"] for c in ("cam_high", "cam_low")]),
            (f"source v8 candidate, cord {parameters['cord_profile']['cord_length_m']:.2f} m (birth state, Nyx)",
             [enlarged["frames"][c]["raw"] for c in ("cam_high", "cam_low")]),
            ("same-scale layout drawing (grey current, red candidate)", [drawing["path"]])]
    stitch(rows, output / "review.png")
    (output / "review.json").write_text(json.dumps(dict(
        variation=args.variation, candidate=parameters, drawing=drawing,
        current_layout=current["layout"], candidate_layout=enlarged["layout"],
        declaration=enlarged["declaration"], review_image=str(output / "review.png"),
        scope="birth-state modeling preview; no physics advanced, no qualification"), indent=1, default=str))
    print(output / "review.png")


if __name__ == "__main__":
    main()
