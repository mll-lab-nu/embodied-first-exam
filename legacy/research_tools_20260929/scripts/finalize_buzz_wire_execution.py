#!/usr/bin/env python3
"""Describe a completed live execution for independent audit; never grant success.

The live driver permits diagnostic submissions and rewinds. Its label alone is
not evidence: audit_buzz_wire_policy must reject any rewind, contact, gap in
history, or missing released Task success before the execution can be archived.
"""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def finalize(folder):
    config = json.loads((folder/"development_config.json").read_text())
    last = json.loads((folder/"live_state.json").read_text())
    if not last["task"]["task_success"]:
        raise ValueError("Live execution has not achieved Task success")
    # Use this execution's birth metadata, including when the prefix came from
    # an unfinished development run that has no final run_report.json.
    birth = json.loads((folder/"private/static_model.json").read_text())["episode"]
    if (birth["episode_id"] != last["state"]["episode_id"]
            or birth["seed"] != config["seed"]
            or birth["task_id"] != config["config"]["task_id"]
            or birth["variation_id"] != config["config"]["variation_id"]):
        raise ValueError("Birth metadata differs from the execution being finalized")
    submissions = {}
    for path in sorted((folder/"policy_submissions").glob("*/manifest.json")):
        manifest = json.loads(path.read_text())
        for name, expected in manifest.items():
            if digest(path.parent/name) != expected:
                raise ValueError(f"Changed policy submission: {path.parent/name}")
        submissions[path.parent.name] = manifest
    evidence = {}
    for pattern in ("commands/*.json", "command_*_response.json", "prefix_actions.json",
                    "development_config.json", "private/static_model.json",
                    "policy_submissions/*/*.py", "policy_submissions/*/manifest.json",
                    "planning_artifacts/*"):
        for path in sorted(folder.glob(pattern)):
            if path.is_file():
                evidence[str(path.relative_to(folder))] = digest(path)
    report = dict(status="task_success_pending_independent_audit", config=config["config"],
        seed=config["seed"], variant=config["config"]["variation_id"], instance_id=birth["instance_id"],
        policy_kind="segmented_feedback_with_compiled_prefix", compiled_prefix_steps=config["prefix_steps"],
        task_success=True, task_result=last["task"], physics_steps=last["state"]["physics_step"],
        simulation_time_s=last["state"]["sim_time_s"], submitted_policies=submissions,
        submission_artifact_sha256=evidence,
        qualification="Single frozen seed instance; ordinary JOINT_ABS submissions from home; contact_weld_v1; "
                      "no RGB/video; no continuous-contact or pure-friction claim. Audit must independently "
                      "verify that the complete execution has no rewinds or forbidden contacts.")
    (folder/"run_report.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    result = finalize(args.run.resolve())
    print(result["status"])
