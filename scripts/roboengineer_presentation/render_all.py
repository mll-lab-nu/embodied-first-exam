"""Render/encode eight operator-only videos sequentially on one selected GPU."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ORDER = [
    "go2-attitude",
    "go2-forward-jump",
    "go2-yaw-jump",
    "go2-weave",
    "g1",
    "neural-landing",
    "neural-fly",
    "anycar",
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--blender", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument(
        "--gpu",
        required=True,
        help="Physical CUDA device visible to this render process only",
    )
    p.add_argument("--only", choices=ORDER + ["anycar-jump", "anycar-drift-v3"])
    a = p.parse_args()
    a.root = a.root.resolve()
    tools = Path(__file__).resolve().parent
    (a.root / "renders").mkdir(exist_ok=True)
    (a.root / "logs").mkdir(exist_ok=True)
    state = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gpu": a.gpu,
        "completed": [],
        "sources": {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in tools.glob("*.py")
        },
    }
    for name in [a.only] if a.only else ORDER:
        state["active"] = name
        (a.root / "render-progress.json").write_text(json.dumps(state, indent=2) + "\n")
        with (a.root / "logs" / (name + ".log")).open("a") as log:
            subprocess.run(
                [
                    str(a.blender),
                    "-b",
                    "--factory-startup",
                    "--python",
                    str(tools / "render_blender.py"),
                    "--",
                    "--capture",
                    str(a.root / "captures" / name),
                    "--output",
                    str(a.root / "renders" / name),
                    "--width",
                    "1920",
                    "--samples",
                    "32",
                ],
                env={**os.environ, "CUDA_VISIBLE_DEVICES": a.gpu},
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(tools / "deliver.py"),
                    "--root",
                    str(a.root),
                    "--only",
                    name,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        state["completed"].append(name)
        print("COMPLETE", name, flush=True)
    if not a.only:
        subprocess.run(
            [
                sys.executable,
                str(tools / "deliver.py"),
                "--root",
                str(a.root),
                "--collection-only",
            ],
            check=True,
        )
    state["active"] = None
    state["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (a.root / "render-progress.json").write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    main()
