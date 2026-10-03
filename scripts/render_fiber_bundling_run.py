#!/usr/bin/env python3
"""Render a continuous saved Fiber episode using its frozen runtime and shared recorder."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument("--output", type=lambda p: Path(p).resolve(), required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.run / "source_snapshot"))
    import torch
    from topogym.simulator import Env, SimulatorConfig
    from topogym.utils.io import sha256_file
    torch.set_num_threads(1)
    source = Path(__file__).resolve().parents[1] / "topogym/recording/rigid_replay.py"
    spec = importlib.util.spec_from_file_location("shared_rigid_replay", source)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    values = json.loads((args.run / "config.json").read_text())
    values.update(enable_rgb=True, enable_depth=False, history_storage="memory", work_dir=None)
    if values["task_id"] != "fiber_bundling":
        raise ValueError("This entry is for Fiber runs")
    episode = json.loads((args.run / "private/static_model.json").read_text())["episode"]
    path = args.run / "private/physics_states.jsonl"
    def open_history():
        return path.open("rb") if path.exists() else gzip.open(path.with_suffix(".jsonl.gz"), "rb")
    digest = hashlib.sha256()
    with open_history() as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    metadata = dict(source_run=str(args.run), source_physics_states_sha256=digest.hexdigest(),
        renderer_implementation_sha256=sha256_file(source), source_instance_id=episode["instance_id"])
    with Env(SimulatorConfig(**values)) as env:
        env.reset(seed=episode["seed"])
        if env._task.instance_id != episode["instance_id"]:
            raise ValueError("Render instance differs from source")
        if dict(env._asset_build.sha256) != json.loads((args.run / "asset_manifest.json").read_text()):
            raise ValueError("Render assets differ from source")
        with open_history() as stream:
            result = replay.record_rigid_history(env, (json.loads(line) for line in stream), args.output,
                                               metadata=metadata)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
