"""Command line of the asset generator.

    python -m robosafebench.assets list [--priority N] [--json]
    python -m robosafebench.assets describe KIND
    python -m robosafebench.assets build (--all | KIND ...) --out DIR [--seed N]
    python -m robosafebench.assets preview --out DIR [KIND ...]
    python -m robosafebench.assets preview --room --out DIR [KIND ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def table() -> str:
    """One row per kind: what a default build is and has."""
    from . import catalog

    rows = ["| Kind | P | Size (cm) | Mass (kg) | Tags | Grasps | Zones | Controls | Looks | Doors | `seed` varies |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]

    def cell(items, limit=6):
        items = list(items)
        text = ", ".join(f"`{i}`" for i in items[:limit])
        return text + (f" +{len(items) - limit}" if len(items) > limit else "")

    for n in catalog.kinds():
        d = catalog.describe(n)
        size = " x ".join(f"{v * 100:.3g}" for v in d["size"])
        name = f"`{n}`" + (" (fixed)" if d["fixed"] else "")
        rows.append(f"| {name} | {d['priority']} | {size} | {d['mass']:.3g} | {cell(d['tags'])} | {cell(d['grasps'], 4)} | "
                    f"{cell(d['zones'], 4)} | {cell(d['controls'])} | {cell(d['looks'])} | {cell(d['doors'])} | {cell(d['vary'])} |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m robosafebench.assets", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="the kinds of the catalogue")
    p.add_argument("--priority", type=int)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("describe", help="parameters, tags, zones, controls and looks of a kind")
    p.add_argument("kind")
    p = sub.add_parser("build", help="write MJCF, meshes, textures and meta.json")
    p.add_argument("kinds", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, help="draw the varying parameters from this seed")
    p.add_argument("--params", help="JSON object of parameters (one kind only)")
    p.add_argument("--profile", choices=("native", "realism_v3"), help="visual set; defaults to realism_v3 or ROBOSAFEBENCH_ASSET_PROFILE")
    sub.add_parser("table", help="the catalogue as a Markdown table (docs/ASSETS.md)")
    p = sub.add_parser("preview", help="contact sheets as PNG")
    p.add_argument("kinds", nargs="*")
    p.add_argument("--out", required=True)
    p.add_argument("--room", action="store_true", help="room-scale sheets: each thing from a room camera and from 1 m")
    args = ap.parse_args(argv)

    from . import catalog

    if args.cmd == "list":
        names = catalog.kinds(args.priority)
        if args.json:
            print(json.dumps(names))
        else:
            for n in names:
                s = catalog.spec(n)
                first = s.doc.split(". ")[0].split("\n")[0].strip()
                print(f"{n:18s} P{s.priority}  {first}")
            print(f"{len(names)} kinds")
        return 0
    if args.cmd == "describe":
        print(json.dumps(catalog.describe(args.kind), indent=1, default=str))
        return 0
    if args.cmd == "build":
        names = catalog.kinds() if args.all else args.kinds
        if not names:
            ap.error("give kinds or --all")
        params = json.loads(args.params) if args.params else {}
        if args.seed is not None:
            params["seed"] = args.seed
        index = {}
        for n in names:
            path, meta = catalog.write(n, params or None, Path(args.out) / n, profile=args.profile)
            index[n] = {"path": str(path.relative_to(args.out)), "size": meta["size"], "mass": meta["mass"], "tags": meta["tags"]}
            print(f"{n:18s} {path}")
        (Path(args.out) / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
        return 0
    if args.cmd == "table":
        print(table())
        return 0
    if args.cmd == "preview":
        from . import preview

        for f in (preview.room_sheets if args.room else preview.all_sheets)(args.out, args.kinds or None):
            print(f)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
