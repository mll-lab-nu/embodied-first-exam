#!/usr/bin/env python3
"""Replay a frozen Claws episode through the shared Nyx rigid-history recorder."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=lambda p: Path(p).resolve())
    parser.add_argument("--output", required=True, type=lambda p: Path(p).resolve())
    args = parser.parse_args()
    source = args.run/"source_snapshot"
    manifest = json.loads((args.run/"source_manifest.json").read_text())
    for name, expected in manifest.items():
        path = (source/name).resolve()
        if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen source differs: "+name)
    sys.path.insert(0, str(source))
    import torch
    from topogym.simulator import Env, SimulatorConfig
    torch.set_num_threads(1)
    root = Path(__file__).resolve().parents[1]

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    replay = load("claws_shared_replay", root/"topogym/recording/rigid_replay.py")
    evidence = load("claws_evidence_reader", root/"topogym/planning/interlocked_claws/evidence.py")
    trail = args.run/"trail"
    values = json.loads((trail/"config.json").read_text())
    if values["task_id"] != "interlocked_claws":
        raise ValueError("Expected a Claws run")
    values.update(enable_rgb=True, enable_depth=False, history_storage="memory", work_dir=None)
    episode = json.loads((trail/"private/static_model.json").read_text())["episode"]
    history = trail/"private/physics_states.jsonl"
    digest = hashlib.sha256()
    with history.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    metadata = dict(source_run=str(args.run), source_physics_states_sha256=digest.hexdigest(),
                    source_instance_id=episode["instance_id"], start="task_pregrasp_birth",
                    assistance="contact_weld_v1", home_approach_included=False)
    with Env(SimulatorConfig(**values)) as env:
        env.reset(seed=episode["seed"])
        if (env._task.instance_id != episode["instance_id"]
                or dict(env._asset_build.sha256) != json.loads((trail/"asset_manifest.json").read_text())):
            raise ValueError("Replay task or geometry differs from the executed episode")
        with history.open() as stream:
            rows = (evidence.decode_record(json.loads(line), trail/"private") for line in stream)
            result = replay.record_rigid_history(env, rows, args.output, metadata=metadata)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
