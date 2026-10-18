"""Stage only checksum-pinned public visual assets; no network or simulator imports."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.control_transfer.neuralfly_visual import COMMIT, FILES, PROFILE, load_assets


def stage(source, destination):
    data = load_assets(source)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in data.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (destination / "visual-provenance.json").write_text(
        json.dumps(
            {
                "profile": PROFILE,
                "source_commit": COMMIT,
                "license": "Apache-2.0",
                "sha256": FILES,
                "description": "Public appearance only; Neural Fly surrogate dynamics unchanged.",
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    return {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.source, args.out), sort_keys=True))
