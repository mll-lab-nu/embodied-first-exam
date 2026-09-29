#!/usr/bin/env python3
"""Compile one successful development lineage; this does not create proof."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def compile_actions(folder, end_state_id):
    states, endings = {}, {}
    ticks = folder/"private/physics_states.jsonl"
    controls = folder/"private/control_steps.jsonl"
    for line in ticks.open():
        row = json.loads(line)
        state = row["state"]
        states[state["state_id"]] = state
        if state["state_id"] == end_state_id:
            endings = row["task"]["result"]
    if not endings.get("task_success"):
        raise ValueError("The selected development state has no Task success")
    lineage, cursor = [], end_state_id
    while cursor is not None:
        state = states[cursor]
        lineage.append(state)
        cursor = state["parent_state_id"]
    lineage.reverse()
    if [s["physics_step"] for s in lineage] != list(range(len(lineage))):
        raise ValueError("Selected lineage does not cover every tick from birth")
    selected, actions = {s["state_id"] for s in lineage[1:]}, {}
    for line in controls.open():
        row = json.loads(line)
        if row["kind"] != "completed" or row["state_ref"]["state_id"] not in selected:
            continue
        if row["physics_steps"] != 1 or row["info"]["control_mode"] != "JOINT_ABS":
            raise ValueError("Compilation requires one ordinary joint action per World tick")
        key = row["state_ref"]["state_id"]
        if key in actions:
            raise ValueError("Duplicate completed action")
        actions[key] = row["info"]["executed_joint_targets"]
    if set(actions) != selected:
        raise ValueError("A selected physics tick has no completed ordinary action")
    development = json.loads((folder/"development_config.json").read_text())
    config = development["config"]
    return dict(schema="buzz_compiled_joint_policy_v1", config=config, seed=development["seed"],
        control_dt_s=config["physics_dt_s"]*config["control_decimation"],
        actions=[actions[s["state_id"]] for s in lineage[1:]],
        provenance=dict(source_run=str(folder.resolve()), end_state_id=end_state_id,
            lineage_state_ids=[s["state_id"] for s in lineage],
            original_manifest=json.loads((folder/"run_source_manifest.json").read_text()),
            input_sha256={p.name:digest(p) for p in (ticks, controls)},
            qualification="Development lineage only. Must execute afresh from home; no state restoration."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("end_state_id", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = compile_actions(args.run, args.end_state_id)
    args.output.write_text(json.dumps(document, separators=(",", ":"))+"\n")
    print(f"Compiled {len(document['actions'])} actions. No qualification has been performed.")


if __name__ == "__main__":
    main()
