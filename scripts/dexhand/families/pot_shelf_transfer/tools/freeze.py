#!/usr/bin/env python3
"""Authoring only: freeze the accepted T17 trial-14 model into this family's runtime assets.

Input (read-only, never modified):
  artifacts/scene-expansion-50/evidence/pot_transfer/trial-14/{model.xml,trajectory.npz}
  scripts/scene_expansion/tasks/pot_transfer/assets/converted/pot_*.stl
  images/dexhand/assets/hand/ (Sharpa Wave), images/everyday_dexterity/assets/tianji/ (Tianji Marvin arms)

Output (this family folder):
  assets/pot_sharpa.xml   the accepted MJCF, byte-for-byte except (a) absolute mesh paths -> @SHARPA@/@TIANJI@/@POT@
                          placeholders and (b) three named static cameras appended to <worldbody> (no physics effect)
  assets/pot/*.stl        the five pot meshes (identical bytes)
  assets/manifest.json    sha256 + size of the frozen XML and of every mesh it references, per asset root
  assets/reset.json       the accepted keyframe by joint / actuator name (used for the Wuji reset)
  solution/trajectory.npz the accepted 8,850 x 58 Sharpa rows (+ hand, task)

`--check` re-derives everything in memory and fails on any difference.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
WORKSPACE = REPO.parent
TRIAL = WORKSPACE / "artifacts/scene-expansion-50/evidence/pot_transfer/trial-14"
POT_SOURCE = REPO / "scripts/scene_expansion/tasks/pot_transfer/assets/converted"
SHARPA = REPO / "images/dexhand/assets/hand"
TIANJI = REPO / "images/everyday_dexterity/assets/tianji"
ACCEPTED = {
    "model_sha256": "eb4a5469f4b31e9976932d6a5d7de1d1ef92972c2ced3aae1de64450efa5562c",
    "initial_sha": "00ac17f0114d1291559153500ceb2ac3d32d084518b2853b4771c64f1815dbb1",
    "final_sha": "5bcddef8f382025f542e2529d4a866fe43b7f1ba876f292c9c059d4f8654e7da",
    "steps": 8850,
}
ROOTS = {
    "SHARPA": (str(SHARPA) + "/", "sharpa"),
    "TIANJI": (str(TIANJI) + "/", "tianji"),
    "POT": (str(POT_SOURCE) + "/", "pot"),
}
# Static presentation/observation cameras. They are appended after all physical elements; cameras carry no mass,
# contact or constraint, so the accepted dynamics are unchanged (verified bit for bit by tools/verify_oracle.py).
CAMERAS = [
    # name, lookat, distance, azimuth (deg), elevation (deg), fovy (deg)
    ("overview", (0.48, 0.13, 0.89), 2.10, 130.0, -28.0, 45.0),
    ("front", (0.48, 0.22, 0.90), 1.80, 90.0, -30.0, 50.0),
    ("shelf", (0.46, 0.31, 0.90), 1.05, 155.0, -25.0, 50.0),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def camera_xml(name, lookat, distance, azimuth, elevation, fovy) -> str:
    """A fixed MJCF camera equivalent to a MuJoCo free camera (lookat, distance, azimuth, elevation)."""
    a, e = np.radians(azimuth), np.radians(elevation)
    forward = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    position = np.asarray(lookat) - distance * forward
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    text = lambda values: " ".join(f"{float(v):.9g}" for v in values)  # noqa: E731
    return (
        f'<camera name="{name}" mode="fixed" pos="{text(position)}" xyaxes="{text(right)} {text(up)}" '
        f'fovy="{fovy:g}" />'
    )


def frozen_xml() -> tuple[str, dict]:
    raw = (TRIAL / "model.xml").read_bytes()
    if sha(raw) != ACCEPTED["model_sha256"]:
        raise SystemExit("trial-14 model.xml differs from the accepted model hash")
    text = raw.decode()
    used: dict[str, set] = {key: set() for key in ROOTS}

    def replace(match):
        path = match.group(1)
        for key, (prefix, _) in ROOTS.items():
            if path.startswith(prefix):
                relative = path[len(prefix):]
                used[key].add(relative)
                return f'file="@{key}@/{relative}"'
        raise SystemExit(f"unexpected mesh path {path}")

    text = re.sub(r'file="([^"]+)"', replace, text)
    if "/home/" in text:
        raise SystemExit("absolute path left in the frozen model")
    cameras = "".join(camera_xml(*camera) for camera in CAMERAS)
    marker = "</worldbody>"
    if text.count(marker) != 1:
        raise SystemExit("expected exactly one </worldbody>")
    text = text.replace(marker, cameras + marker)
    return text, used


def manifest_for(xml: str, used: dict) -> dict:
    roots = {}
    for key, (prefix, name) in ROOTS.items():
        base = Path(prefix)
        files = {}
        for relative in sorted(used[key]):
            data = (base / relative).read_bytes()
            files[relative] = {"bytes": len(data), "sha256": sha(data)}
        roots[name] = {"placeholder": f"@{key}@", "files": files}
    roots["sharpa"].update(env="DEXHAND_ASSET_DIR", default="/opt/dexhand/hand")
    roots["tianji"].update(env="DEXHAND_TIANJI_DIR", default="/opt/dexhand/tianji")
    roots["pot"].update(relative="pot")
    return {
        "schema_version": 1,
        "model": {"file": "pot_sharpa.xml", "bytes": len(xml.encode()), "sha256": sha(xml.encode())},
        "roots": roots,
    }


def reset_record() -> dict:
    import mujoco

    model = mujoco.MjModel.from_xml_path(str(TRIAL / "model.xml"))
    key = model.key("start")
    qpos = {}
    for joint in range(model.njnt):
        start = int(model.jnt_qposadr[joint])
        end = int(model.jnt_qposadr[joint + 1]) if joint + 1 < model.njnt else model.nq
        qpos[model.joint(joint).name] = [float(x) for x in key.qpos[start:end]]
    ctrl = {model.actuator(i).name: float(key.ctrl[i]) for i in range(model.nu)}
    return {"keyframe": "start", "qpos_by_joint": qpos, "ctrl_by_actuator": ctrl}


def oracle_bytes() -> bytes:
    with np.load(TRIAL / "trajectory.npz", allow_pickle=False) as archive:
        actions = np.asarray(archive["actions"], dtype=np.float64)
    if actions.shape != (ACCEPTED["steps"], 58):
        raise SystemExit(f"unexpected accepted action shape {actions.shape}")
    buffer = io.BytesIO()
    np.savez_compressed(buffer, actions=actions, hand=np.array("sharpa"), task=np.array("pot_shelf_transfer"))
    return buffer.getvalue()


def outputs() -> dict[Path, bytes]:
    xml, used = frozen_xml()
    result = {
        FAMILY / "assets/pot_sharpa.xml": xml.encode(),
        FAMILY / "assets/manifest.json": (json.dumps(manifest_for(xml, used), indent=2, sort_keys=True)
                                          + "\n").encode(),
        FAMILY / "assets/reset.json": (json.dumps(reset_record(), indent=1, sort_keys=True) + "\n").encode(),
    }
    for relative in sorted(used["POT"]):
        result[FAMILY / "assets/pot" / relative] = (POT_SOURCE / relative).read_bytes()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = outputs()
    oracle = FAMILY / "solution/trajectory.npz"
    bad = [path for path, data in files.items() if not path.is_file() or path.read_bytes() != data]
    if oracle.is_file():
        with np.load(oracle, allow_pickle=False) as archive, np.load(TRIAL / "trajectory.npz") as accepted:
            same = (np.array_equal(archive["actions"], accepted["actions"]) and str(archive["hand"]) == "sharpa"
                    and archive["actions"].dtype == np.float64)
    else:
        same = False
    if args.check:
        for path in bad:
            print("DIFF", path.relative_to(FAMILY))
        if not same:
            print("DIFF solution/trajectory.npz")
        print("freeze check:", "clean" if not bad and same else "differences")
        return int(bool(bad) or not same)
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if not same:
        oracle.parent.mkdir(parents=True, exist_ok=True)
        oracle.write_bytes(oracle_bytes())
    print(f"froze {len(files)} files and the oracle into {FAMILY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
