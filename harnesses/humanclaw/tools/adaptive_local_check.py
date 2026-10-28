"""Run actual Pi/model discovery against local public fixtures, never the pilot server."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from humanclaw_bench.environment import load_project_environment
from humanclaw_bench.experiments.recorder import TraceRecorder
from humanclaw_bench.experiments.integration import register_capabilities
from humanclaw_bench.harnesses.runtime import NativeHarness, load_harness_config, native_paper_cost, runtime_identity

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from adaptive_public_fixture import PublicInstrument
from adaptive_heldout_fixture import PublicSwitchboard


def run(output, family):
    """Expose only the public bootstrap; score fixture truth outside all agent inputs."""
    load_project_environment()
    output.mkdir(parents=True, exist_ok=True)
    config = load_harness_config("configs/harnesses/pi_adaptive.json")
    config["timeout_seconds"] = 900  # The ordinary local fixture task timeout.
    config["request_timeout_seconds"] = 120
    # Save the generic runtime identity before constructing/revealing the public fixture.
    (output / "frozen-runtime.json").write_text(json.dumps(runtime_identity("pi", config), indent=2))
    fixture = PublicSwitchboard() if family == "heldout" else PublicInstrument(family)
    record = {"family": family, "mode": "autonomous_model", "start": "cold", "human_interventions": [],
              "declared_scope": ["observation", "bounded_action_receipt"], "scheduled_trials": 1,
              "bootstrap": fixture.bootstrap(), "failure_stage": None}
    (output / "trial-spec.json").write_text(json.dumps(record, indent=2))
    recorder = TraceRecorder(output, {"benchmark": "public-interface-local", "harness": "pi", "family": family})
    start = time.monotonic()
    try:
        with recorder:
            register_capabilities("pi")
            try:
                result = NativeHarness("pi", config, {"model": "gpt-6-astra", "max_tokens": 12288}).run(fixture.bootstrap(), output)
                record["native_result"] = result
            except Exception as exc:
                record.update(error=str(exc), failure_stage="native_session")
            recorder.finish(outcome={"task_success": fixture.outcome(output)["task_success"], "steps": len(fixture.actions)})
        report_files = list(output.rglob("interface-trial.json"))
        interface = json.loads(report_files[-1].read_text()) if report_files else {}
        checks = fixture.outcome(output)
        observed, action = checks["public_sample"], checks["bounded_actions"]
        registered = interface.get("local_adaptation_status") == "pass"
        if not registered and record["failure_stage"] is None:
            record["failure_stage"] = "discovery" if not interface.get("adapters") else "validation_or_registration"
        record.update(adaptation_status="pass" if observed and action and registered else "fail",
                      task_outcome="success" if checks["task_success"] else "failure",
                      independent_checks={**checks, "registered": registered},
                      interface=interface, elapsed_seconds=time.monotonic() - start,
                      cost=native_paper_cost(interface.get("raw_model_usage", []), len(fixture.actions)))
        (output / "result.json").write_text(json.dumps(record, indent=2))
        print(json.dumps({k: record[k] for k in ("family", "adaptation_status", "task_outcome", "elapsed_seconds", "failure_stage")}))
        return record
    finally:
        fixture.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--family", choices=["schema", "client", "rgbd", "heldout"], default="schema")
    args = parser.parse_args()
    run(args.output.resolve(), args.family)
