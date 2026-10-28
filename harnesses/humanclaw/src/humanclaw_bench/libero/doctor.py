"""GPU environment, actuator-journal and physical-replay check; no model calls."""
import argparse
import json
from pathlib import Path

from humanclaw_bench.experiments.recorder import TraceRecorder, span
from .run import configure_roborsi


def doctor(roboroot, output, task="libero_object_task/0"):
    """Check real actuation and physical replay without invoking a model."""
    from .backend import RoboBackend
    from .protocol import ToolService
    from .replay import physics_replay, log_replay
    from .report import summarize
    output = Path(output).resolve()
    recorder = TraceRecorder(output, {"harness": "physics_selfcheck", "benchmark": "libero-pro-selfcheck",
        "task": task, "seed": 0, "config": {"model": "gpt-6-astra"}, "model_calls_expected": 0})
    configure_roborsi(roboroot, recorder.directory / "roborsi_home", {"model": "gpt-6-astra"})
    with recorder:
        backend = RoboBackend(task, 0, recorder.directory, roboroot=roboroot)
        bridge = ToolService(backend, recorder.run_id, recorder.directory)
        try:
            recorder.write_json("capabilities.json", backend.manifest())
            recorder.write_json("initial_state.json", backend.initial_snapshot)
            with span("episode.decision"):
                response = bridge.call_tool("gripper", {"state": "open", "request_id": "selfcheck-open", "observation_id": 0})
                if response["status"] != "completed" or response["control_steps"] < 1:
                    raise RuntimeError(f"Controller selfcheck failed: {response.get('error') or response.get('result')}")
            recorder.finish(outcome={"benchmark_success": backend.success(), "infrastructure_error": False,
                                     "control_steps": backend.control_steps, "termination_reason": "scripted_selfcheck"})
        finally:
            bridge.shutdown()
            backend.close()
    replay, replay_dir = physics_replay(recorder.directory, roboroot=roboroot)
    summarize(recorder.directory)
    log_replay(recorder.directory)
    result = {"run_directory": str(recorder.directory), "replay_directory": str(replay_dir),
              "passed": replay["state_consistent"] and replay["success_consistent"],
              "max_absolute_error": replay["max_absolute_error"], "model_requests": 0}
    (output / "doctor.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--roborsi-root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--task", default="libero_object_task/0")
    a = p.parse_args()
    result = doctor(a.roborsi_root, a.output, a.task)
    raise SystemExit(0 if result["passed"] else 1)
