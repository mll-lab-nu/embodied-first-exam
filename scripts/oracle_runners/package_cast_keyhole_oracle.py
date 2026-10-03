#!/usr/bin/env python3
"""Package a private Cast Keyhole reference for a frozen Harbor instance.

This writes a PRIVATE candidate only. It never marks a task oracle=full or
changes the dataset. Harbor oracle/nop and independent replay must pass first.
Feedback mode uses the successful local policy as its basis and generates new
actions through the frozen public Session instead of replaying the local trace.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(run, instance_path, output, *, allow_gripper_roundtrip_loss=None, feedback=False):
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
    conversion_audit = dict(native_tolerance_m=1e-6,
                            allowed_loss_reason=allow_gripper_roundtrip_loss)
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
conversion_audit = json.loads(CONVERSION_LITERAL)
roundtrips = []
for arm, column in session.robot.grip_index.items():
    for target in np.unique(native[:, column]):
        width = float(np.float32(session.robot.native_to_width(arm, target)))
        recovered = float(session.robot.width_to_native(arm, width))
        error = abs(recovered - float(target))
        roundtrips.append(dict(arm=arm, native_m=float(target), public_width_m=width,
                               recovered_native_m=recovered, error_m=error))
print(json.dumps(dict(gripper_roundtrip=roundtrips, **conversion_audit)), flush=True)
if any(not np.isfinite(item["error_m"]) for item in roundtrips):
    raise ValueError("Nonfinite public gripper conversion")
if (any(item["error_m"] > conversion_audit["native_tolerance_m"] for item in roundtrips)
        and not conversion_audit["allowed_loss_reason"]):
    raise ValueError("Native gripper target is not representable by public widths; "
                     "regenerate the reference with the recovered native target")
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
        "PAYLOAD_LITERAL", repr(payload)).replace(
        "CONVERSION_LITERAL", repr(json.dumps(conversion_audit, sort_keys=True)))
    output.mkdir(parents=True, exist_ok=False)
    solution = output / "solution"
    solution.mkdir()
    script = solution / "oracle_cast_keyhole.py"
    helpers = {}
    if feedback:
        source_hashes = json.loads((run / "source_manifest.json").read_text())["source_hashes"]
        relative_files = [
            "topogym/planning/__init__.py", "topogym/planning/cast_keyhole/__init__.py",
            "topogym/planning/cast_keyhole/policy.py", "topogym/planning/cast_keyhole/simplified_policy.py",
            "topogym/planning/cast_keyhole/kinematics.py", "topogym/planning/rigid_reference/__init__.py",
            "topogym/planning/rigid_reference/geometry.py", "topogym/planning/rigid_reference/feedback.py",
        ]
        for relative in relative_files:
            source = run / "source_snapshot" / relative
            if digest(source) != source_hashes.get(relative.removeprefix("topogym/")):
                raise ValueError("Changed successful-run policy source: " + relative)
            target = solution / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            helpers[relative] = digest(target)
        relative = "topogym/planning/cast_keyhole/public_session.py"
        target = solution / relative
        shutil.copy2(Path(__file__).resolve().parents[2] / relative, target)
        helpers[relative] = digest(target)
        code = '''"""Private feedback reference for its frozen instance; all movement uses Session.step."""
import hashlib, json
from pathlib import Path
import topogym
identity = json.loads(IDENTITY_LITERAL)
if (session.config != identity["config"] or session.asset_identity != identity["assets"]
        or session.instance_sha != identity["state_sha"]
        or session.env._task.instance_id != identity["local_instance_id"]
        or session.action_layout != identity["layout"] or session.n_steps != 0):
    raise ValueError("Reference requires its exact frozen instance at episode start")
for name, expected in json.loads(HELPERS_LITERAL).items():
    if hashlib.sha256((Path("/solution")/name).read_bytes()).hexdigest() != expected:
        raise ValueError("Private reference helper changed: " + name)
topogym.__path__.append("/solution/topogym")
from topogym.planning.cast_keyhole.public_session import run_feedback_policy
run_feedback_policy(session, Path("/app/output"))
'''.replace("IDENTITY_LITERAL", repr(json.dumps(identity, sort_keys=True))).replace(
            "HELPERS_LITERAL", repr(json.dumps(helpers, sort_keys=True)))
    script.write_text(code)
    manifest = dict(status="private_feedback_candidate" if feedback else "private_replay_candidate", harbor_qualified=False,
        local_run=str(run.resolve()), instance_path=str(instance_path.resolve()),
        instance_sha256=digest(instance_path), local_report_sha256=digest(run/"run_report.json"),
        native_sha256=reference["sha256"], script_sha256=digest(script),
        rows=None if feedback else reference["rows"], local_basis_rows=reference["rows"],
        gripper_roundtrip_audit=conversion_audit,
        execution="public_session_feedback" if feedback else "native_target_replay",
        private_helpers_sha256=helpers,
        conversion="target Session adapter native_to_width, then public float32 JOINT_ABS",
        required="independent oracle, repeated replay, nop and both Harbor modes")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--instance", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-gripper-roundtrip-loss", metavar="REASON",
                        help="Explicitly allow lossy legacy gripper commands for a documented replay experiment")
    parser.add_argument("--feedback", action="store_true",
                        help="Package private passive policy helpers to generate actions inside the frozen Session")
    args = parser.parse_args()
    print(json.dumps(package(args.run, args.instance, args.output,
                             allow_gripper_roundtrip_loss=args.allow_gripper_roundtrip_loss,
                             feedback=args.feedback), indent=2))
