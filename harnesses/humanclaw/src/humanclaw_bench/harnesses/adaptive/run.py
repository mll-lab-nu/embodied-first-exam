"""Run the pinned Pi session from a minimal public bootstrap JSON document."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from humanclaw_bench.environment import load_project_environment
from humanclaw_bench.experiments.integration import register_capabilities
from humanclaw_bench.experiments.recorder import TraceRecorder
from humanclaw_bench.harnesses.runtime import NativeHarness, load_harness_config


def main(argv=None):
    """Save provider traces and local adaptation evidence without claiming task scores."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--harness-config", type=Path, default=Path("configs/harnesses/pi_adaptive.json"))
    parser.add_argument("--model-config", type=Path, default=Path("configs/models/azure_gpt6_astra.json"))
    args = parser.parse_args(argv)
    load_project_environment()
    bootstrap = json.loads(args.bootstrap.read_text())
    config = load_harness_config(args.harness_config)
    model = json.loads(args.model_config.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    recorder = TraceRecorder(output, {"benchmark": "public-interface", "harness": "pi", "task": bootstrap["task"]})
    with recorder:
        register_capabilities("pi")
        try:
            result = NativeHarness("pi", config, model).run(bootstrap, output)
        except Exception as exc:
            recorder.finish(outcome={"task_success": None, "error": str(exc)})
            raise
        recorder.finish(outcome={"task_success": None, "steps": result["steps"], "termination_reason": result["termination_reason"]})
    (output / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"native_directory": result["native_directory"], "interface": result["interface"]["local_adaptation_status"],
                      "task_outcome": "unscorable", "model_requests": result["model_requests"]}))


if __name__ == "__main__":
    main()
