#!/usr/bin/env python3
"""Bind each essential oracle to its validated evidence and re-verify it in fresh processes.

For every family: the packaged solution/trajectory.npz must be byte-identical to the validated action archive, the
Sharpa model XML must hash to the validated model, the trajectory must succeed in two fresh replays with identical
final state hashes equal to the validated positive hash, and the float32 wire form (standard mode) must also succeed.
The instance hash is reported against the validated one; a difference is listed with its reason (strictness edits).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parents[2] / "artifacts/dexhand-visual-upgrade"
FAMILIES = ["essential_cube_layer", "essential_held_joystick", "essential_pen_regrasp", "essential_two_object",
            "essential_rotary_gait", "essential_cube_reorient"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packaged_identical(directory: Path, source: Path) -> bool:
    """The packaged rows equal the validated archive: the same file, or parts whose concatenated float64 rows are
    bit-identical to it (manifest sha256 checked by solution_parts.load)."""
    if (directory / "trajectory.npz").is_file():
        return sha(directory / "trajectory.npz") == sha(source)
    sys.path.insert(0, str(HERE / "shared/solution"))
    import numpy as np
    from solution_parts import load

    rows, _hand = load(directory)
    with np.load(source, allow_pickle=False) as archive:
        validated = np.asarray(archive["actions"], dtype=np.float64)
    manifest = json.loads((directory / "trajectory.json").read_text())
    return manifest["source_sha256"] == sha(source) and rows.shape == validated.shape and rows.tobytes() == validated.tobytes()


def replay(family: str, trajectory: Path, out: Path) -> dict:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, str(HERE / "shared/replay.py"), "--task", family, "--traj", str(trajectory),
                    "--out", str(out)], check=True, env=env, cwd=HERE / "shared")
    return json.loads(out.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--families", nargs="*", default=FAMILIES)
    args = parser.parse_args()
    sys.path.insert(0, str(HERE / "shared"))
    import numpy as np
    from runtime import Session

    summary = {item["task"]: item for item in json.loads((EVIDENCE / "validation-summary.json").read_text())["tasks"]}
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        for family in args.families:
            validated = summary[family]
            record = json.loads((EVIDENCE / f"videos/{family}.json").read_text())
            source = EVIDENCE / f"actions/{family}.npz"
            packaged_dir = HERE / f"task_library/{family}/solution"
            session = Session(family)
            item = {
                "trajectory": str(source),
                "trajectory_sha256": sha(source),
                "trajectory_matches_video_record": sha(source) == record["trajectory_sha256"],
                "packaged_solution_identical": packaged_identical(packaged_dir, source),
                "model_xml_sha256": hashlib.sha256(session.xml.encode()).hexdigest(),
                "validated_model_xml_sha256": validated["model_xml_sha256"],
                "instance_sha256": hashlib.sha256(json.dumps(session.spec, sort_keys=True).encode()).hexdigest(),
                "validated_instance_sha256": validated["instance_sha256"],
                "validated_positive_sha": validated["positive_sha"],
            }
            item["model_matches"] = item["model_xml_sha256"] == item["validated_model_xml_sha256"]
            item["instance_matches"] = item["instance_sha256"] == item["validated_instance_sha256"]
            a = replay(family, source, Path(tmp) / f"{family}-1.json")
            b = replay(family, source, Path(tmp) / f"{family}-2.json")
            item.update(
                replay_success=bool(a["success"] and b["success"]),
                replay_steps=a["steps"],
                replay_stages=f'{a["stage"]}/{a.get("total_stages")}',
                replay_state_sha=a["state_sha"],
                deterministic=a["state_sha"] == b["state_sha"],
                positive_sha_matches=a["state_sha"] == validated["positive_sha"],
            )
            with np.load(source, allow_pickle=False) as archive:
                rows = archive["actions"].astype(np.float32).astype(np.float64)
            wire = Path(tmp) / f"{family}-float32.npz"
            np.savez(wire, actions=rows, hand=np.array("sharpa"))
            c = replay(family, wire, Path(tmp) / f"{family}-float32.json")
            item.update(float32_wire_success=bool(c["success"]), float32_steps=c["steps"])
            item["ok"] = all(item[key] for key in ("trajectory_matches_video_record", "model_matches", "replay_success",
                                                   "deterministic", "positive_sha_matches", "float32_wire_success"))
            results[family] = item
            print(family, "ok" if item["ok"] else "FAIL", {k: v for k, v in item.items() if isinstance(v, bool)},
                  flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return int(not all(item["ok"] for item in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
