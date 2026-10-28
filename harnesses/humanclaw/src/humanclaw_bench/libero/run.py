"""Single-episode runner. Heavy dependencies are imported after configuration."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import random
import signal
import sys
import time

from humanclaw_bench.experiments.recorder import TraceRecorder, event, span


class EpisodeDeadlineExceeded(BaseException):
    """A declared benchmark budget, not a model/service infrastructure failure."""


@contextmanager
def deadline(seconds):
    """Enforce the declared decision wall-clock budget on the owner thread."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return
    def expired(*_):
        """Raise an episode-budget interruption that SDK retries cannot swallow."""
        raise EpisodeDeadlineExceeded("Episode wall-clock budget exhausted")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def configure_roborsi(roboroot, home, config):
    """Set frozen direct-API role settings before upstream imports."""
    sys.path.insert(0, str(Path(roboroot).resolve()))
    settings = {"ROBORSI_HOME": str(home), "ROBORSI_RUN_MODE": "frozen", "ROBORSI_ROLE_SESSION": "0",
        "ROBORSI_OPENAI_TRANSPORT": "responses", "ROBORSI_VLM_PROVIDER": "openai",
        "ROBORSI_REASONING_EFFORT": config.get("reasoning_effort", "medium"),
        "ROBORSI_OPENAI_MAX_OUTPUT_TOKENS": str(config.get("max_output_tokens", 8192)),
        "ROBORSI_VLM_MODEL": "openai/" + config["model"],
        "ROBORSI_PERCEPTION_MODEL": "openai/" + config.get("perception_model", config["model"])}
    os.environ.update(settings)
    return settings


def run_episode(*, harness, task, seed, output, config, roboroot, max_calls=40,
                max_control_steps=20000, resolution=256, settle_steps=20, pricing=None,
                initial_from=None):
    """Own one isolated attempt from startup through metrics and cleanup."""
    from .backend import RoboBackend, source_identity
    from .protocol import ToolService
    from .service import MeteredService
    from .adapters import run_bare, run_native, run_roborsi, robor_instrumentation
    from .report import summarize
    from .replay import log_replay
    from .provenance import framework_identity, assets_identity, OBSERVABILITY, validate_pricing
    from humanclaw_bench.harnesses.runtime import native_connection
    import numpy as np

    # Never persist credentials; only the configured environment variable name.
    if any("key" in key.lower() and key != "api_key_env" for key in config):
        raise ValueError("Use api_key_env; inline credentials are not supported")
    validate_pricing(pricing)
    metadata = {"benchmark": "libero-pro", "harness": harness, "task": task, "seed": seed,
                "config": config, "max_calls": max_calls, "max_control_steps": max_control_steps,
                "resolution": resolution, "settle_steps": settle_steps, "roborsi_root": str(roboroot),
                "initial_from": str(initial_from) if initial_from else None,
                "protocol": "libero_tools_v1", "mode": "live", "role_session": 0, "run_mode": "frozen"}
    recorder = TraceRecorder(Path(output).expanduser().resolve(), metadata, pricing)
    recorder.directory.chmod(0o700)
    backend = bridge = None
    outcome = {"benchmark_success": None, "infrastructure_error": False}
    failure = None
    with recorder:
        try:
            with span("episode.startup", kind="module"):
                recorder.write_json("framework.json", framework_identity())
                recorder.write_json("assets.json", assets_identity())
                recorder.write_json("observability.json", OBSERVABILITY)
                settings = configure_roborsi(roboroot, recorder.directory / "roborsi_home", config)
                recorder.write_json("effective_environment.json", settings)
                random.seed(seed)
                np.random.seed(seed)
                backend = RoboBackend(task, seed, recorder.directory, roboroot=roboroot,
                    max_control_steps=max_control_steps, resolution=resolution, settle_steps=settle_steps)
                recorder.write_json("capabilities.json", backend.manifest())
                recorder.write_json("initial_state.json", backend.initial_snapshot)
                (recorder.directory / "PUBLIC_KNOWLEDGE.md").write_text(backend.knowledge)
                if initial_from:
                    origin = Path(initial_from)
                    prior = json.loads((origin / "capabilities.json").read_text())
                    if prior["catalog_hash"] != backend.catalog_hash:
                        raise ValueError("Same-configuration rerun refused: capability catalog/source drift")
                    current = backend.manifest()
                    for key in ("versions", "scene_sha256", "controller", "action_dimension", "controller_config"):
                        if prior.get(key) != current.get(key):
                            raise ValueError(f"Same-configuration rerun refused: {key} drift")
                    old_framework = origin / "framework.json"
                    if old_framework.exists() and json.loads(old_framework.read_text())["actual_source_sha256"] != framework_identity()["actual_source_sha256"]:
                        raise ValueError("Same-configuration rerun refused: benchmark adapter source drift")
                    backend.restore(json.loads((origin / "initial_state.json").read_text()))
                    backend.initial_snapshot = backend.snapshot()
                    initial = json.loads(backend.journal.db.execute(
                        "SELECT value FROM metadata WHERE key='initial'").fetchone()[0])
                    initial["snapshot"] = backend.initial_snapshot
                    backend.journal.metadata("initial", initial)
                    recorder.write_json("initial_state.json", backend.initial_snapshot)
                bridge = ToolService(backend, recorder.run_id, recorder.directory,
                    max_calls=max_calls, max_control_steps=max_control_steps)
                url, credential = native_connection(config)
            with MeteredService(bridge, upstream_url=url, api_key=credential,
                    azure=config.get("auth", "azure") == "azure",
                    timeout=config.get("request_timeout_seconds", 600),
                    allowed_models=[config["model"], config.get("perception_model", config["model"])]) as meter:
                # Catch any OpenAI-compatible helper using environment-based SDK
                # construction, in addition to the explicit RoboRSI client hook.
                os.environ.update(OPENAI_BASE_URL=meter.url + "/v1", OPENAI_API_BASE=meter.url + "/v1",
                                  OPENAI_API_KEY=meter.bearer, ROBORSI_OPENAI_BASE_URL=meter.url + "/v1",
                                  ROBORSI_OPENAI_API_KEY=meter.bearer)
                with robor_instrumentation(meter, bridge, config):
                    with span("episode.decision", kind="module") as decision:
                        meter.context = __import__("contextvars").copy_context()
                        with deadline(config.get("timeout_seconds", 1800)):
                            if harness == "bare":
                                result = run_bare(bridge, meter, config)
                            elif harness in {"codex", "pi"}:
                                result = run_native(harness, bridge, meter, config)
                            else:
                                result = run_roborsi(bridge, meter, config)
                        decision.set_output(result)
                outcome.update(termination_reason=bridge.termination,
                               benchmark_success=backend.success(), control_steps=backend.control_steps,
                               environment_calls=bridge.step, model_requests=meter.calls)
                if bridge.failure and bridge.termination != "control_budget":
                    outcome["infrastructure_error"] = True
                if source_identity(roboroot)["source_tree_sha256"] != backend.source["source_tree_sha256"]:
                    raise RuntimeError("Frozen RoboRSI capability files changed during the episode")
        except BaseException as exc:
            failure = exc
            is_budget = isinstance(exc, EpisodeDeadlineExceeded)
            outcome.update(infrastructure_error=not is_budget,
                           termination_reason="wall_clock_budget" if is_budget else type(exc).__name__, error=str(exc))
            if backend is not None:
                try:
                    outcome["benchmark_success"] = backend.success()
                except Exception:
                    pass
        finally:
            if bridge is not None:
                bridge.shutdown()
            if backend is not None:
                try:
                    backend.close()
                except Exception as exc:
                    event("cleanup.failed", name="environment.close", data={"error": str(exc)})
                    outcome["cleanup_error"] = str(exc)
                    outcome["infrastructure_error"] = True
                    failure = failure or exc
            recorder.finish(status="failed" if failure or outcome["infrastructure_error"] else "completed",
                            outcome=outcome, error=failure)
    report = summarize(recorder.directory)
    log_replay(recorder.directory)
    print(json.dumps({"run_directory": str(recorder.directory), "outcome": outcome,
                      "model_requests": report["model_requests"], "usage_coverage": report["usage_coverage"]}))
    return recorder.directory, report


def main():
    """Dispatch single-run, log replay, physical replay, rerun and report commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--harness", choices=["bare", "codex", "pi", "roborsi"], required=True)
    run.add_argument("--task", default="libero_object_task/0")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--output", required=True)
    run.add_argument("--config", required=True)
    run.add_argument("--roborsi-root", required=True)
    run.add_argument("--env-file")
    run.add_argument("--max-calls", type=int, default=40)
    run.add_argument("--max-control-steps", type=int, default=20000)
    run.add_argument("--pricing")
    replay = sub.add_parser("replay")
    replay.add_argument("run_directory")
    replay.add_argument("--mode", choices=["log", "physics"], required=True)
    replay.add_argument("--roborsi-root")
    rerun = sub.add_parser("rerun")
    rerun.add_argument("run_directory")
    rerun.add_argument("--output", required=True)
    rerun.add_argument("--env-file")
    report = sub.add_parser("report")
    report.add_argument("root")
    args = parser.parse_args()
    if getattr(args, "env_file", None):
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    if args.command == "run":
        _, report = run_episode(harness=args.harness, task=args.task, seed=args.seed, output=args.output,
            config=json.loads(Path(args.config).read_text()), roboroot=args.roborsi_root,
            max_calls=args.max_calls, max_control_steps=args.max_control_steps,
            pricing=json.loads(Path(args.pricing).read_text()) if args.pricing else None)
        return int(report["outcome"].get("infrastructure_error", False))
    if args.command == "rerun":
        origin = Path(args.run_directory)
        manifest = json.loads((origin / "run.json").read_text())
        m = manifest["metadata"]
        run_episode(harness=m["harness"], task=m["task"], seed=m["seed"], output=args.output,
            config=m["config"], roboroot=m["roborsi_root"], max_calls=m["max_calls"],
            max_control_steps=m["max_control_steps"], resolution=m["resolution"],
            settle_steps=m["settle_steps"], pricing=manifest["pricing"], initial_from=origin)
    elif args.command == "replay":
        from .replay import log_replay, physics_replay
        if args.mode == "log":
            print(log_replay(args.run_directory))
        else:
            if not args.roborsi_root:
                parser.error("--roborsi-root is required for physics replay")
            m = json.loads((Path(args.run_directory) / "run.json").read_text())["metadata"]
            configure_roborsi(args.roborsi_root, Path(args.run_directory) / "replay_home", m["config"])
            result, output = physics_replay(args.run_directory, roboroot=args.roborsi_root)
            print(json.dumps({k: v for k, v in result.items() if k not in {"differences", "runtime"}}))
            print(output)
    else:
        from .report import aggregate
        directories = sorted(p.parent for p in Path(args.root).rglob("run.json")
                             if "physics_replays" not in p.parts)
        result = aggregate(directories)
        path = Path(args.root) / "libero_summary.json"
        path.write_text(json.dumps(result, indent=2))
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
