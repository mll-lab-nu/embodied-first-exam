#!/usr/bin/env python3
"""Authoring tool: freeze the accepted T13 sweeping episode into this family's offline assets.

Input (read-only, workspace evidence):
  artifacts/everyday-dexterity-2026-10-13/sweeping/strong-index-cleanup/native-trial/{model.xml,trajectory.npz,report.json}

Output (this family folder):
  assets/sweep_sharpa.xml        the accepted model, byte-identical except that absolute mesh paths become
                                 ${DEXHAND_ASSET_DIR}/... and ${TIANJI_ASSET_DIR}/... tokens and four fixed world
                                 cameras are added (cameras do not touch dynamics; verified by the native hashes)
  assets/reset.npz               the accepted initial qpos, the first control row (the pre-held hold targets) and the
                                 joint/actuator layout used to transfer the reset to the Wuji composition by name
  assets/external_assets.json    every mesh the model loads from the image, with sha256 and size
  assets/manifest.json           sha256 of the three files above (provenance stays in provenance.json)
  solution/trajectory.json + trajectory.partNN.npz
                                 the accepted 132,521 x 58 float64 controls followed by 16,000 copies of their last row
                                 (an 8 s hold after the end of the accepted run), hand "sharpa", stored as parts below
                                 2 MB each (scripts/dexhand/shared/solution/solution_parts.py)

Never run inside a task. Re-running reproduces the same bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile

import numpy as np

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
REPO = FAMILY.parents[3]
WORKSPACE = REPO.parent
SOURCE = WORKSPACE / "artifacts/everyday-dexterity-2026-10-13/sweeping/strong-index-cleanup/native-trial"
HOLD_ROWS = 16000  # 8 s: lets rolling pieces settle in noisy replays (tools/perturbation_study.py)
TOKENS = {
    str(REPO / "images/dexhand/assets/hand"): "${DEXHAND_ASSET_DIR}",
    str(REPO / "images/everyday_dexterity/assets/tianji"): "${TIANJI_ASSET_DIR}",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def camera_xml(name: str, camera: dict) -> str:
    """A fixed world camera equivalent to a MuJoCo free camera (lookat, distance, azimuth, elevation)."""
    azimuth, elevation = math.radians(camera["azimuth"]), math.radians(camera["elevation"])
    forward = np.array(
        [math.cos(elevation) * math.cos(azimuth), math.cos(elevation) * math.sin(azimuth), math.sin(elevation)]
    )
    position = np.asarray(camera["lookat"], dtype=float) - camera["distance"] * forward
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    values = " ".join(f"{v:.6f}" for v in [*right, *up])
    pos = " ".join(f"{v:.6f}" for v in position)
    return f'<camera name="{name}" mode="fixed" pos="{pos}" xyaxes="{values}" fovy="{camera["fovy"]:g}" />'


def write_npz(path: Path, arrays: dict, compression=zipfile.ZIP_DEFLATED) -> None:
    """A standard .npz (np.load reads it) with fixed member timestamps, so re-running gives the same bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, value in arrays.items():
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, value, allow_pickle=False)
            info = zipfile.ZipInfo(name + ".npy", date_time=(2026, 10, 14, 0, 0, 0))
            info.compress_type = compression
            archive.writestr(info, buffer.getvalue())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    config = json.loads((FAMILY / "task.json").read_text())
    source = json.loads((FAMILY / "provenance.json").read_text())
    model_bytes = (args.source / "model.xml").read_bytes()
    trajectory_bytes = (args.source / "trajectory.npz").read_bytes()
    if sha(model_bytes) != source["model_xml_sha256"] or sha(trajectory_bytes) != source["trajectory_sha256"]:
        raise SystemExit("accepted source files differ from the hashes frozen in provenance.json")
    xml = model_bytes.decode()
    for absolute, token in TOKENS.items():
        xml = xml.replace(absolute, token)
    leftover = re.findall(r'file="(/[^"]*)"', xml)
    if leftover:
        raise SystemExit(f"absolute asset paths left: {leftover[:3]}")
    cameras = "".join(camera_xml(name, camera) for name, camera in config["cameras"].items())
    if xml.count("<worldbody>") != 1:
        raise SystemExit("expected exactly one <worldbody>")
    xml = xml.replace("<worldbody>", "<worldbody>" + cameras, 1)
    assets = FAMILY / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "sweep_sharpa.xml").write_text(xml)

    external = []
    for token, relative in sorted(set(re.findall(r'file="\$\{([A-Z_]+)\}/([^"]+)"', xml))):
        base = {"DEXHAND_ASSET_DIR": REPO / "images/dexhand/assets/hand",
                "TIANJI_ASSET_DIR": REPO / "images/everyday_dexterity/assets/tianji"}[token]
        data = (base / relative).read_bytes()
        external.append({"token": token, "path": relative, "sha256": sha(data), "bytes": len(data)})
    (assets / "external_assets.json").write_text(json.dumps({"schema_version": 1, "files": external}, indent=1) + "\n")

    import mujoco  # authoring only: read the layout of the frozen model

    model = mujoco.MjModel.from_xml_path(str(args.source / "model.xml"))
    with np.load(args.source / "trajectory.npz", allow_pickle=False) as archive:
        actions = np.asarray(archive["actions"], dtype=np.float64)
        initial_qpos = np.asarray(archive["initial_qpos"], dtype=np.float64)
    joints = [model.joint(j).name for j in range(model.njnt)]
    qposadr = np.asarray(model.jnt_qposadr, dtype=np.int64)
    qposdim = np.diff(np.append(qposadr, model.nq)).astype(np.int64)
    write_npz(
        assets / "reset.npz",
        {
            "initial_qpos": initial_qpos,
            "initial_ctrl": actions[0].copy(),
            "joint_names": np.array(joints),
            "joint_qposadr": qposadr,
            "joint_qposdim": qposdim,
            "actuator_names": np.array([model.actuator(i).name for i in range(model.nu)]),
        },
    )

    manifest = {
        "schema_version": 1,
        "files": {
            name: sha((assets / name).read_bytes())
            for name in ("sweep_sharpa.xml", "reset.npz", "external_assets.json")
        },
        "derivation": "sweep_sharpa.xml: the frozen scene model with mesh paths tokenized and the task cameras added; "
        "reset.npz: the frozen initial joint positions and the initial (holding) motor targets",
    }
    (assets / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")

    # Oracle = the accepted rows unchanged, plus HOLD_ROWS copies of their last row (the lifted-pan hold). A bit-exact
    # replay succeeds at row 132,392 and never reaches the padding; it only adds terminal-hold margin when a replay
    # differs slightly (e.g. rows perturbed by noise).
    oracle = np.concatenate([actions, np.repeat(actions[-1:], HOLD_ROWS, axis=0)])
    # One archive would be 7.2 MB; the repository limit is 2 MB per file, so the rows are stored as parts with the
    # shared splitter (trajectory.json + trajectory.partNN.npz, sha256 of the concatenated float64 rows).
    import sys
    import tempfile

    sys.path.insert(0, str(REPO / "scripts/dexhand/shared/solution"))
    from solution_parts import split

    solution = FAMILY / "solution"
    for old in solution.glob("trajectory*"):
        old.unlink()
    with tempfile.TemporaryDirectory() as scratch:
        full = Path(scratch) / "oracle.npz"
        write_npz(full, {"actions": np.asfortranarray(oracle), "hand": np.array("sharpa")}, compression=zipfile.ZIP_LZMA)
        split(full, solution, task="sweep_dustpan")
    print(json.dumps({"external_files": len(external), "rows": len(actions), **manifest["files"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
