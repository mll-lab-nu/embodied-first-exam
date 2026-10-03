#!/usr/bin/env python3
"""Bind a successful local reference to a frozen Harbor instance for replay testing.

This writes a PRIVATE candidate only. It never marks a task oracle=full or
changes the dataset. Harbor oracle/nop and independent replay must pass first.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(run, instance_path, output):
    run, instance_path, output = map(Path, (run, instance_path, output))
    report = json.loads((run / "run_report.json").read_text())
    reference = json.loads((run / "native_reference.json").read_text())
    config = json.loads((run / "config.json").read_text())
    instance = json.loads(instance_path.read_text())
    if (report.get("status") != "passed" or report.get("task_success") is not True
            or report.get("part") != "all" or not report.get("from_default_home")
            or reference.get("local_task_success") is not True):
        raise ValueError("A complete successful local run from home is required")
    if instance.get("task") != "cast_keyhole" or config["variation_id"] not in {
            "cast_keyhole_very_easy", "cast_keyhole_easier"}:
        raise ValueError("Only the two simplified Cast Keyhole references are supported")
    target_variation = instance.get("resolved_variation_id", instance.get("variation_id"))
    if (target_variation != config["variation_id"]
            or instance.get("evaluable_for_task_success") is not True
            or reference["instance_id"] != report["instance_id"]):
        raise ValueError("Reference and target instance identities disagree")
    for filename, key in (("config.json", "config_sha256"),
                          ("source_manifest.json", "source_manifest_sha256")):
        if digest(run / filename) != reference[key]:
            raise ValueError("Changed reference provenance: " + filename)
    artifact = run / "native_joint_targets.npz"
    if reference["artifact"] != artifact.name or digest(artifact) != reference["sha256"]:
        raise ValueError("Changed native control artifact")
    if report["asset_sha256"] != reference["asset_sha256"]:
        raise ValueError("Local asset provenance disagrees")
    if instance.get("asset_identity") != reference["asset_sha256"]:
        raise ValueError("Frozen instance assets differ from the successful local scene")
    # These fields affect transport, evidence or observation. Every other
    # setting, including assistance and physics sampling, must match exactly.
    transport = {"control_mode", "observation_mode", "history_storage", "enable_rgb",
                 "enable_depth", "enable_privileged", "seed", "work_dir", "asset_root",
                 "max_physics_steps"}
    physical = lambda c: {k: v for k, v in c.items() if k not in transport}
    target_config = dict(instance["simulator"], variation_id=target_variation)
    if physical(config) != physical(target_config):
        raise ValueError("Frozen instance physics/task configuration differs")
    with np.load(artifact, allow_pickle=False) as data:
        targets, ticks, layout = data["targets"], data["physics_steps"], data["layout"].tolist()
        expected_layout = [n.replace("_native_gripper", "_gripper") for n in layout]
        if (targets.ndim != 2 or targets.shape != (reference["rows"], len(layout))
                or not np.isfinite(targets).all() or ticks.shape != (len(targets),)
                or expected_layout != instance["action_layout"]
                or ticks.sum() != reference["physics_steps"]
                or not np.all(ticks[:-1] == config["control_decimation"])
                or not 1 <= ticks[-1] <= config["control_decimation"]):
            raise ValueError("Control layout or tick history is inconsistent")
    identity = dict(config=instance["simulator"], assets=instance["asset_identity"],
                    state_sha=instance["state_sha"], local_instance_id=reference["instance_id"],
                    layout=expected_layout)
    payload = base64.b85encode(artifact.read_bytes()).decode("ascii")
    # One self-contained file fits the existing --oracle generator. Decode
    # only numeric NPZ data, never a pickle or development-tool dependency.
    code = '''"""Private replay candidate; requires independent Harbor qualification."""
import base64, io, json
import numpy as np
identity = json.loads(IDENTITY_LITERAL)
if (session.config != identity["config"] or session.asset_identity != identity["assets"]
        or session.instance_sha != identity["state_sha"]
        or session.env._task.instance_id != identity["local_instance_id"]
        or session.action_layout != identity["layout"] or session.n_steps != 0):
    raise ValueError("Reference requires its exact frozen instance at episode start")
with np.load(io.BytesIO(base64.b85decode(PAYLOAD_LITERAL)), allow_pickle=False) as data:
    native = data["targets"].copy()
for step_index, original in enumerate(native, 1):
    row = original.copy()
    for arm, column in session.robot.grip_index.items():
        row[column] = session.robot.native_to_width(arm, original[column])
    # The public Session converts float32 opening widths to native commands
    # and executes real physics. The Task owns terminal partial-step timing.
    if session.step(row):
        break
    if step_index % 200 == 0:
        print(json.dumps(dict(oracle_row=step_index, sim_time_s=session.sim_time_s)), flush=True)
if not session.success():
    from dataclasses import asdict
    print(json.dumps(dict(oracle_task_result=asdict(session.env._task.result)),
                     default=lambda value: value.tolist()), flush=True)
    raise RuntimeError("Native reference did not survive Harbor width/float32 replay")
'''.replace("IDENTITY_LITERAL", repr(json.dumps(identity, sort_keys=True))).replace(
        "PAYLOAD_LITERAL", repr(payload))
    output.mkdir(parents=True, exist_ok=False)
    solution = output / "solution"
    solution.mkdir()
    script = solution / "oracle_cast_keyhole.py"
    script.write_text(code)
    manifest = dict(status="private_replay_candidate", harbor_qualified=False,
        local_run=str(run.resolve()), instance_path=str(instance_path.resolve()),
        instance_sha256=digest(instance_path), local_report_sha256=digest(run/"run_report.json"),
        native_sha256=reference["sha256"], script_sha256=digest(script), rows=reference["rows"],
        conversion="target Session adapter native_to_width, then public float32 JOINT_ABS",
        required="independent oracle, repeated replay, nop and both Harbor modes")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.run, args.instance, args.output), indent=2))
