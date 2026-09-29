"""Generate frozen Harbor tasks, invoke native harbor run, collect verified output."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import signal
import os
from datetime import datetime, timezone
from uuid import uuid4

from .collect import collect
from .config import load_config, expand, name, validate
from .preflight import check
from .task_generator import prepare, verify_frozen
from .agents.credentials import credential_environment, selected_secrets, redact, redact_logs
from .hooks import cleanup, recover
from .collect import atomic_json
from .rollout_output_report import summarize, format_summary
from .usage_bridge import socket_directory
from .endpoints import PROJECT


def launch(run, root, *, api_key=None, env_file=None):
    run = Path(run).resolve()
    config = json.loads((run / "experiment.resolved.json").read_text())
    budgeted = config["usage"]["mode"] != "off"
    environment = credential_environment(root, env_file, api_key=api_key, required=budgeted)
    check(run, environ=environment)
    if (run / "jobs/job").exists():
        raise FileExistsError("This frozen run already has a job; collect it or prepare a new run-id")
    command = [str(Path(sys.executable).with_name("harbor")), "run", "--config", str(run / "job.json")]
    secrets = selected_secrets(environment)
    if budgeted:
        sockets = socket_directory(run)
        sockets.mkdir(mode=0o755, exist_ok=True)
        if sockets.is_symlink() or sockets.stat().st_uid != os.getuid():
            raise ValueError("Unsafe usage socket directory")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True, env=environment)
    try:
        for line in process.stdout:
            print(redact(line, secrets), end="", flush=True)
        code = process.wait()
    except KeyboardInterrupt:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=120)  # allow Harbor verifier/collect/teardown
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        code = 130
    finally:
        process.stdout.close()
        redact_logs(run, secrets)
        # Native artifact hooks run before Harbor deletes the containers. Collection
        # here only verifies and relocates their already-downloaded host exports.
        index = collect(run, root)
        summary = summarize(run)
        try:
            cleanup_result = cleanup(run, index)
        except (OSError, RuntimeError) as error:
            cleanup_result = {"status": "retained", "reason": type(error).__name__}
        atomic_json(run / "cleanup.json", cleanup_result)
        if budgeted:
            try:
                sockets.rmdir()  # never delete sockets owned by a still-running trial
            except OSError:
                pass
        print(redact(format_summary(summary), secrets), flush=True)
    return code if code else (0 if index["pipeline_passed"] else 1)


def apply_usage_args(config, args):
    mode = getattr(args, "usage_mode", None)
    supplied = args.input_token_limit is not None or args.output_token_limit is not None
    if mode is not None or supplied:
        mode = mode or config.get("usage", {}).get("mode", "off")
        if mode == "off" and supplied:
            raise ValueError("Token limits require --usage-mode observed or strict")
        if mode == "off":
            config["usage"] = {"mode": "off"}
        else:
            config["usage"] = {**config.get("usage", {}), "mode": mode}
            limits = config["usage"].setdefault("limits", {})
            for dimension in ("input", "output"):
                value = getattr(args, dimension + "_token_limit")
                if value is not None:
                    limits[dimension + "_tokens"] = value


def new_run_id():
    return "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid4().hex[:8]


def build_parser():
    parser = argparse.ArgumentParser(description="Run a preset TopoGym experiment with OpenCode.")
    def location_options(target, *, defaults=False):
        target.add_argument("--root", type=Path, default=PROJECT if defaults else argparse.SUPPRESS,
                            help="Output workspace (default: project root)")
        target.add_argument("--env-file", type=Path, default=None if defaults else argparse.SUPPRESS,
                            help="Optional private dotenv file; default: <root>/.secrets/harbor.env")
    def key_options(target):
        group = target.add_mutually_exclusive_group()
        group.add_argument("--api-key", help="Key belonging to the model's provider (not saved)")
        group.add_argument("--api-key-stdin", action="store_true", help="Read the API key from one stdin line")
    location_options(parser, defaults=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for command_name in ("prepare", "run"):
        command = sub.add_parser(command_name, help="Freeze inputs" if command_name == "prepare" else "Prepare and launch")
        location_options(command)
        key_options(command)
        selection = command.add_mutually_exclusive_group()
        selection.add_argument("--experiment", help="Preset name in configs/harbor/experiments (no .yaml)")
        selection.add_argument("--config", type=Path, help="Advanced: experiment YAML path")
        command.add_argument("--defaults", type=Path, help="Advanced: deployment defaults YAML")
        command.add_argument("--run-id", help="Optional unique ID; automatically generated by default")
        command.add_argument("--model-name", "--model", dest="model", required=True,
                             help="Full OpenCode model: provider_id/model_id")
        command.add_argument("--image", help="Advanced: existing Docker image tag/digest")
        command.add_argument("--opencode-version", help="Advanced: pinned OpenCode version")
        command.add_argument("--attempts", type=int, help="Attempts per instance (default: preset or 1)")
        command.add_argument("--concurrency", type=int, help="Concurrent trials (default: preset or 1)")
        command.add_argument("--difficulty", nargs="+", help="Variations within the selected task preset")
        command.add_argument("--seeds", type=int, nargs="+", help="Seed sweep; each seed creates an instance")
        command.add_argument("--mode", choices=("limited", "unlimited"),
                             help="Observation access for every instance (default: preset); independent of token limits")
        command.add_argument("--state-fields", nargs="*", choices=("robot", "world", "task"),
                             help="Privileged fields in unlimited mode (default: preset; no values clears the list)")
        allocation = command.add_mutually_exclusive_group()
        allocation.add_argument("--gpus", type=int, help="GPUs per trial (default: deployment)")
        allocation.add_argument("--gpu-devices", nargs="+", help="Explicit GPU IDs per trial")
        command.add_argument("--timeout-sec", type=float, help="Agent wall-clock limit; default: preset or 1800")
        command.add_argument("--input-token-limit", type=int, help="Per-trial input token limit, including cached input")
        command.add_argument("--output-token-limit", type=int, help="Per-trial output token limit, including reasoning")
        command.add_argument("--initial-observation-steps", type=int, help="Initial real simulation steps (default: 5)")
    for command_name in ("launch", "preflight", "collect"):
        command = sub.add_parser(command_name)
        location_options(command)
        key_options(command)
        command.add_argument("--run-dir", required=True, type=Path)
        if command_name == "collect":
            command.add_argument("--recover", action="store_true", help="Recover artifacts from retained containers")
    for command_name in ("usage-status", "usage-update"):
        command = sub.add_parser(command_name)
        command.add_argument("--trial-dir", required=True, type=Path)
        if command_name == "usage-update":
            command.add_argument("--input-token-limit", required=True, type=int)
            command.add_argument("--output-token-limit", required=True, type=int)
            command.add_argument("--revision", required=True, type=int)
            command.add_argument("--reason", required=True)
    return parser


def config_from_args(args):
    path = args.config
    if args.experiment:
        path = PROJECT / "configs/harbor/experiments" / (name(args.experiment) + ".yaml")
    overrides = {key: getattr(args, key) for key in (
        "image", "model", "opencode_version", "attempts", "concurrency", "timeout_sec", "gpus")
        if getattr(args, key) is not None}
    if args.gpu_devices is not None:
        overrides.update(gpu_devices=args.gpu_devices, gpus=len(args.gpu_devices))
    config = load_config(path, defaults_file=args.defaults, overrides=overrides)
    if args.gpus is not None:
        config.pop("gpu_devices", None)
    apply_usage_args(config, args)
    if args.difficulty or args.seeds is not None:
        expand(config, difficulties=args.difficulty, seeds=args.seeds)
    for instance in config["instances"]:
        if args.mode is not None:
            instance["mode"] = args.mode
            instance["simulator"]["enable_privileged"] = args.mode == "unlimited"
            if args.mode == "limited":
                instance["state_fields"] = []
        if args.state_fields is not None:
            instance["state_fields"] = list(args.state_fields)
        if args.initial_observation_steps is not None:
            instance["initial_observation_steps"] = args.initial_observation_steps
    return validate(config)


def input_key(args, *, required):
    key = args.api_key
    if args.api_key_stdin:
        key = sys.stdin.readline().rstrip("\r\n")
        if not key:
            raise ValueError("No API key received on stdin")
    if key is None and required:
        environment = credential_environment(args.root, args.env_file, required=False)
        from .endpoints import CREDENTIAL_ENV
        key = environment.get(CREDENTIAL_ENV)
        if not key and sys.stdin.isatty():
            import getpass
            key = getpass.getpass("Provider API key: ")
    return key


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    secrets = (args.api_key,) if getattr(args, "api_key", None) else ()
    try:
        if args.command in {"usage-status", "usage-update"}:
            from topogym.agents.usage import UsageLedger
            import getpass
            path = args.trial_dir / "usage/ledger.sqlite"
            if not path.is_file():
                raise ValueError("No active/persisted usage ledger for this trial")
            ledger = UsageLedger(path)
            result = ledger.snapshot() if args.command == "usage-status" else ledger.update_limits(
                input_tokens=args.input_token_limit, output_tokens=args.output_token_limit,
                expected_revision=args.revision, actor=getpass.getuser(), reason=args.reason)
            print(json.dumps(result, indent=2))
            return 0
        if args.command in {"prepare", "run"}:
            config = config_from_args(args)
            # Prepare never loads or requires an upstream credential.
            if args.command == "prepare":
                run = prepare(config, args.root, args.run_id or new_run_id())
                print(f"Frozen run: {run}", flush=True)
                return 0
            key = input_key(args, required=True)
            environment = credential_environment(args.root, args.env_file, api_key=key)
            secrets = selected_secrets(environment)
            run = prepare(config, args.root, args.run_id or new_run_id())
            print(f"Frozen run: {run}", flush=True)
            return launch(run, args.root, api_key=key, env_file=args.env_file)
        verify_frozen(args.run_dir)
        config = json.loads((args.run_dir / "experiment.resolved.json").read_text())
        required = args.command != "collect" and config["usage"]["mode"] != "off"
        key = input_key(args, required=required)
        environment = credential_environment(args.root, args.env_file, api_key=key, required=required)
        secrets = selected_secrets(environment)
        if args.command == "launch":
            return launch(args.run_dir, args.root, api_key=key, env_file=args.env_file)
        if args.command == "preflight":
            print(json.dumps(check(args.run_dir, environ=environment), indent=2))
            return 0
        if args.recover:
            recover(args.run_dir)
        redact_logs(args.run_dir, secrets)
        result = collect(args.run_dir, args.root)
        summarize(args.run_dir)
        atomic_json(args.run_dir / "cleanup.json", cleanup(args.run_dir, result))
        print(json.dumps(result, indent=2))
        return 0 if result["pipeline_passed"] else 1
    except (ValueError, RuntimeError, OSError) as error:
        print(redact(str(error), secrets), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
