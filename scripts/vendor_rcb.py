#!/usr/bin/env python3
"""Copy the robot_coding_bench files listed in ci_checks/rcb_vendor.json at its pinned commit.

    scripts/vendor_rcb.py [--repo ../robot_coding_bench]

`verbatim` files are (over)written byte for byte; `adapted` files are only created when missing (they carry TopoGym
edits). The reference blob id of every source is recorded under "blobs"; ci_checks/check-rcb-vendor.sh compares the
verbatim copies against them without needing the reference repository."""
import argparse, json, pathlib, subprocess

root = pathlib.Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--repo", default=str(root.parent / "robot_coding_bench"))
a = ap.parse_args()
manifest_path = root / "ci_checks/rcb_vendor.json"
m = json.loads(manifest_path.read_text())


def git(*args, text=True):
    return subprocess.run(["git", "-C", a.repo, *args], check=True, capture_output=True, text=text).stdout


blobs = {}
for kind in ("verbatim", "adapted"):
    for dest, src in m[kind].items():
        mode, _, blob = git("ls-tree", m["commit"], "--", src).split()[:3]
        data = git("show", f"{m['commit']}:{src}", text=False)
        out = root / dest
        if kind == "verbatim" or not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            out.chmod(0o755 if mode == "100755" else 0o644)
        blobs[dest] = blob
m["blobs"] = blobs
manifest_path.write_text(json.dumps(m, indent=1) + "\n")
print(f"{len(m['verbatim'])} verbatim, {len(m['adapted'])} adapted files from {m['commit'][:8]}")
