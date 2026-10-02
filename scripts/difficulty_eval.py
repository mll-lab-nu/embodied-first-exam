#!/usr/bin/env python3
"""Prepare and run difficulty evaluations through the existing Harbor CLI.

The Bash entry point bootstraps Docker (or explicit local mode). Sampling and result classification
remain in their dedicated modules; each sample/mode still gets one Harbor job.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager, suppress
import fcntl
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import sample_difficulty_instances as sampling
import difficulty_hf_auth as hf_auth

ROOT = Path(__file__).resolve().parents[1]
PROMPT_KEY = object()
AUTH_VARIABLES = ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE",
                  "OPENROUTER_BASE_URL", "CODEX_FORCE_AUTH_JSON", "CODEX_AUTH_JSON_PATH")
COMPLETE = {"solved", "unsolved", "not_evaluable", "invalid_submission"}
RETRYABLE = {"interrupted", "infra_failed", "invalid_job"}


class EvaluationError(Exception):
    """An actionable error whose message contains no credentials or raw argv."""


class Interrupted(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse may echo unexpected tokens, including a misplaced API key.
        super().error("invalid arguments; use --help to see accepted options")


class ApiKeyAction(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        if namespace.api_key is not None:
            raise EvaluationError("--api-key supplied more than once")
        if value == "":
            raise EvaluationError("empty --api-key")
        namespace.api_key = value


def parse_args(argv=None):
    parser = ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog="Docker launcher options: --backend docker|local (default docker), --controller-image <digest or local image ID>. "
               "Docker subcommands: check, auth login --device-auth, auth status. "
               "Direct keys may enter shell history/process argv. Use --api-key without a value for hidden TTY input.")
    parser.add_argument("--run-id")
    parser.add_argument("--phase", choices=("plan", "prepare", "preflight", "run", "collect", "upload", "all"), default="all")
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--work-dir", type=Path, help="Docker default: launcher cwd/topogym-work; direct Python default: repository")
    parser.add_argument("--gpu-device", default="0", help="host GPU index or UUID")
    parser.add_argument("--cuda-flavor", choices=("cu128", "cu130"), default="cu128",
                        help="runtime CUDA profile; cu130 requires host NVIDIA driver R580+")
    parser.add_argument("--release-lock", type=Path, help="published image digest manifest; otherwise build from fixed recipes")
    sampling.add_sampling_arguments(parser)
    parser.add_argument("--rerun-incomplete", action="store_true", help="with --resume, create a new attempt for interrupted/infra jobs")
    parser.add_argument("--auth", choices=("subscription", "api-key"))
    parser.add_argument("--provider", choices=("openai", "openrouter"), default="openai")
    parser.add_argument("--agent")
    parser.add_argument("--model", help="required for run/all; no implicit model substitution")
    parser.add_argument("--agent-arg", action="append", default=[], metavar="KEY=VALUE", help="version or reasoning_effort; repeatable")
    parser.add_argument("--auth-json", type=Path, help="default: $CODEX_HOME/auth.json or ~/.codex/auth.json")
    parser.add_argument("--api-key", nargs="?", const=PROMPT_KEY, action=ApiKeyAction, metavar="VALUE")
    parser.add_argument("--api-key-env", help="fallback variable; default: provider's key variable")
    parser.add_argument("--env-file", type=Path, help="parse the selected key as data, never shell-source")
    parser.add_argument("--gpu-wait-s", type=int, default=600)
    parser.add_argument("--gpu-min-free-mb", type=int, default=12000)
    hf_auth.add_arguments(parser)
    args = parser.parse_args(argv)
    if args.list_tasks:
        return args
    hf_auth.validate_arguments(args)
    if not re.fullmatch(r"(?:[0-9]+|GPU-[A-Za-z0-9-]+)", args.gpu_device):
        raise EvaluationError("invalid --gpu-device")
    if not args.run_id or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", args.run_id):
        raise EvaluationError("--run-id must contain 1..80 letters/digits/_/-")
    if args.gpu_wait_s < 0 or args.gpu_min_free_mb < 0:
        raise EvaluationError("GPU limits must be nonnegative integers")
    if args.rerun_incomplete and not args.resume:
        raise EvaluationError("--rerun-incomplete requires --resume")
    if args.api_key is not None:
        if args.auth not in (None, "api-key"):
            raise EvaluationError("--api-key conflicts with subscription auth")
        args.auth = "api-key"
    if args.auth == "subscription" and (args.provider != "openai" or args.env_file or args.api_key_env):
        raise EvaluationError("subscription requires OpenAI and no API key source")
    if args.auth == "api-key" and args.auth_json is not None:
        raise EvaluationError("--auth-json conflicts with API-key auth")
    if any(not re.fullmatch(r"(version|reasoning_effort)=[a-zA-Z0-9._-]+", arg) for arg in args.agent_arg):
        raise EvaluationError("--agent-arg supports version=... and reasoning_effort=... only")
    return args


def dotenv_key(path, name):
    try:
        lines = path.expanduser().read_text().splitlines()
    except OSError:
        raise EvaluationError("cannot read explicit --env-file") from None
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise EvaluationError("invalid dotenv line (values are data, never shell code)")
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if key in values:
            raise EvaluationError("duplicate dotenv variable")
        values[key] = value
    if not values.get(name):
        raise EvaluationError("selected key missing/empty in explicit --env-file")
    return values[name]


def authentication(args, base_env):
    """Return a child-only environment and a non-secret execution identity."""
    if not args.model or not args.auth:
        raise EvaluationError("run/all requires --model and --auth (or --api-key)")
    if args.provider == "openai":
        args.agent = args.agent or "codex"
        if args.agent != "codex":
            raise EvaluationError("OpenAI supports --agent codex")
        if "/" not in args.model:
            args.model = "openai/" + args.model
        if not args.model.startswith("openai/"):
            raise EvaluationError("OpenAI model must be openai/<model> or an unprefixed model name")
    else:
        args.agent = args.agent or "harbor_agents.codex_openrouter:CodexOpenRouter"
        if args.agent != "harbor_agents.codex_openrouter:CodexOpenRouter":
            raise EvaluationError("unsupported OpenRouter agent")
        if not re.fullmatch(r"openrouter/[^/]+/.+", args.model) or args.auth != "api-key":
            raise EvaluationError("OpenRouter requires API key and openrouter/<provider>/<model>")
    env = dict(base_env)
    if args.auth == "subscription":
        args.auth_json = (args.auth_json or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json").expanduser().resolve()
        try:
            data = json.loads(args.auth_json.read_text())
            if not (data.get("tokens") or {}).get("access_token"):
                raise ValueError()
        except (OSError, ValueError, TypeError, AttributeError):
            raise EvaluationError("subscription auth.json is unreadable or contains no ChatGPT token") from None
        env.update(CODEX_FORCE_AUTH_JSON="1", CODEX_AUTH_JSON_PATH=str(args.auth_json))
        if os.environ.get("TOPOGYM_CONTAINER") == "1":
            env["TOPOGYM_PERSIST_AUTH"] = "1"
    else:
        variable = args.api_key_env or ("OPENAI_API_KEY" if args.provider == "openai" else "OPENROUTER_API_KEY")
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", variable):
            raise EvaluationError("invalid --api-key-env name")
        if args.api_key is PROMPT_KEY:
            if not sys.stdin.isatty():
                raise EvaluationError("hidden --api-key input requires a TTY; use --api-key=VALUE, --env-file or --api-key-env")
            key = getpass.getpass("API key: ")
        elif args.api_key is not None:
            key = args.api_key
        elif args.env_file:
            key = dotenv_key(args.env_file, variable)
        else:
            key = os.environ.get("TOPOGYM_LAUNCH_KEY", os.environ.get(variable, ""))
        if not key or "\n" in key or "\r" in key:
            raise EvaluationError("API key missing/empty or contains newline")
        env["OPENAI_API_KEY" if args.provider == "openai" else "OPENROUTER_API_KEY"] = key
    os.environ.pop("TOPOGYM_LAUNCH_KEY", None)
    args.api_key = None
    identity = dict(auth=args.auth, provider=args.provider, agent=args.agent, model=args.model, agent_args=args.agent_arg)
    return env, identity


@contextmanager
def lock(path, message):
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EvaluationError(message) from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_json(path):
    return json.loads(path.read_text())


def progress(message, *, error=False):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S%z")
    print(f"[{timestamp}] {message}", file=sys.stderr if error else sys.stdout, flush=True)


def stage(phase):
    number, title = {"plan": (1, "planning"), "prepare": (2, "preparing"),
                     "preflight": (3, "preflight"), "run": (4, "running"),
                     "collect": (5, "collecting")}[phase]
    progress(f"=== stage {number}/5 {title} ===")


def task_progress(row, index, total, activity, *, mode=None):
    unit = "trial" if mode else "instance"
    detail = f"{row['difficulty']} | {row['sample_id']} | seed={row['scene_seed']}"
    if mode:
        detail += f" | {mode}"
    progress(f"==== currently on task 「{row['task_id']}」 | {unit} {index}/{total} | {detail} | {activity} ====")


class Commands:
    """Own subprocess groups and enforce the existing host resource guard."""
    def __init__(self, env, run):
        self.env, self.run, self.child = env, run, None
        self.resource_peaks = dict(cpu_percent=0.0, memory_percent=0.0)

    def stop(self):
        child = self.child
        if child is None:
            return
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
        try:
            child.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=5)
        self.child = None

    def check_resources(self):
        import psutil
        cpu, memory = psutil.cpu_percent(), psutil.virtual_memory().percent
        self.resource_peaks['cpu_percent'] = max(self.resource_peaks['cpu_percent'], cpu)
        self.resource_peaks['memory_percent'] = max(self.resource_peaks['memory_percent'], memory)
        if memory >= 90:
            sampling.atomic_json(self.run / "resource-stop.json", dict(cpu_percent=cpu, memory_percent=memory,
                pid=self.child.pid if self.child else None))
            raise EvaluationError("Memory reached 90%; owned work stopped; see resource-stop.json")

    def run_command(self, argv, *, log=None, append=False, capture=False, env=None, input_text=None,
                    monitor=False, timeout=None, check=False):
        with ExitStack() as stack:
            output = stack.enter_context(log.open("a" if append else "w")) if log else (subprocess.PIPE if capture else subprocess.DEVNULL)
            if monitor:
                import psutil
                psutil.cpu_percent()
            deadline = time.monotonic() + timeout if timeout is not None else None
            try:
                self.child = subprocess.Popen([str(value) for value in argv], cwd=ROOT, env=env or self.env,
                    start_new_session=True, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT, text=True)
                while True:
                    try:
                        stdout, _ = self.child.communicate(input=input_text, timeout=2)
                        code = self.child.returncode
                        self.child = None
                        break
                    except subprocess.TimeoutExpired:
                        input_text = None  # communicate retains the pending input across timeout retries
                        if monitor:
                            self.check_resources()
                        if deadline is not None and time.monotonic() >= deadline:
                            raise EvaluationError(f"{Path(argv[0]).name} timed out")
                if check and code:
                    suffix = f"; see {log}" if log else ""
                    raise EvaluationError(f"{Path(argv[0]).name} failed (exit {code}){suffix}")
                return code, stdout or ""
            finally:
                if self.child is not None:
                    self.stop()
                if monitor:
                    sampling.atomic_json(self.run / 'resource-usage.json', self.resource_peaks)


LIMITED_SMOKE = """from rcb_client import Robot
import numpy as np
r = Robot(base='http://localhost:8000'); spec = r.spec(); obs = r.get_obs()
assert obs.last and all(np.isfinite(v).all() for v in obs.last.values())
dim = spec['action_types']['joint_position']['dim']
first, count, _ = spec['proprio_groups']['joint_cmd']
assert count == dim
q = np.asarray(obs.meta['proprio']['now'][first:first+count], dtype=np.float32)
res = r.submit('joint_position', q[None,:], dt=1/spec['control_hz'])
assert res.meta.get('ok') and res.last
after = np.asarray(res.meta['proprio']['now'][first:first+count], dtype=np.float32)
assert np.allclose(after, q, atol=1e-6, rtol=0)
print('limited protocol smoke passed', flush=True)
"""

CANARY_VERIFIER = """#!/bin/bash
mkdir -p /logs/verifier
find /logs/verifier -mindepth 1 -maxdepth 1 ! -name test-stdout.txt -exec rm -rf {} +
python - <<'CHECK'
import json
try:
    d=json.load(open('/app/output/canary.json'))
    ok=d.get('ready') is True and isinstance(d.get('image_description'),str) and len(d['image_description'].strip())>5
except (OSError,ValueError,TypeError): ok=False
json.dump({'success':int(ok)},open('/logs/verifier/reward.json','w'))
open('/logs/verifier/reward.txt','w').write(str(int(ok)))
CHECK
"""


class DifficultyEvaluation:
    def __init__(self, args):
        self.args = args
        self.work = (args.work_dir or ROOT).resolve()
        self.run = self.work / "runs/difficulty_trials" / args.run_id
        self.jobs = self.work / "jobs/difficulty_trials" / args.run_id
        self.source = self.run / "source"
        self.manifest_path = self.run / "manifest.lock.json"
        self.manifest = self.collector = self.auth_env = None
        self.owns_gpu_lock = False
        self.python = sys.executable
        self.harbor = os.environ.get("TOPOGYM_HARBOR", str(ROOT / ".venv-harbor/bin/harbor"))
        env = hf_auth.clean_environment(os.environ, args)
        for name in (*AUTH_VARIABLES, args.api_key_env, "TOPOGYM_LAUNCH_KEY"):
            if name:
                env.pop(name, None)
        env.update(PYTHONPATH=str(self.source), PATH=str(Path(self.python).parent) + os.pathsep + env.get("PATH", ""))
        self.commands = Commands(env, self.run)
        self.delivery = None
        self.gpu_device = args.gpu_device
        if os.environ.get("TOPOGYM_CONTAINER") == "1":
            from difficulty_delivery import Delivery, configure_host_metrics
            configure_host_metrics()
            if args.phase != "upload":
                self.delivery = Delivery(self.work, self.commands, gpu_device=args.gpu_device,
                                         run_id=args.run_id, release_lock=args.release_lock, cuda_flavor=args.cuda_flavor)
                if not any(arg.startswith("version=") for arg in args.agent_arg):
                    args.agent_arg.append("version=" + self.delivery.info["codex_version"])

    def load_collector(self):
        # Load the run's frozen implementation; old manifests keep their original semantics.
        sys.path.insert(0, str(self.source / "scripts"))
        spec = importlib.util.spec_from_file_location("difficulty_frozen_collector", self.source / "scripts/collect_batch_results.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.collector = module

    def collect(self, *, announce=False):
        if announce:
            stage("collect")
        result = self.collector.collect_manifest(self.manifest_path, self.jobs)
        if announce:
            progress(f"Summary: {self.run / 'summary.md'}")
        return result

    def execute(self):
        if self.args.phase == "upload" and not self.manifest_path.is_file():
            raise EvaluationError("phase upload requires an existing collected run; check --work-dir and --run-id")
        if not hf_auth.active(self.args):
            if self.args.results_to_hf:
                progress("[hf-upload] Upload deferred: this phase does not publish results")
            elif self.args.phase in ("all", "run", "collect"):
                progress("[hf-upload] Upload disabled")
            return self.execute_evaluation()
        from difficulty_results_hf import UploadLog, Publisher, export_snapshot, publication_lock, recovery_command
        self.run.mkdir(parents=True, exist_ok=True)
        secrets = [os.environ.get(key) for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", self.args.api_key_env) if key]
        log = UploadLog(self.run, secrets)
        publisher, result = None, None
        try:
            if not self.args.hf_dry_run:
                token, source = hf_auth.resolve_token(self.args)
                log.scrub.secrets += (token,)
                publisher = Publisher(self.run, self.args, token, log, self.commands.check_resources)
                publisher.preflight(source)
            result = 0 if self.args.phase == "upload" else self.execute_evaluation()
            if self.auth_env:
                log.scrub.secrets += tuple(self.auth_env.get(key) for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY") if self.auth_env.get(key))
            # Lock order: run then publisher. GPU lease has already been released.
            with lock(self.run / ".lock", "another invocation owns this run-id"):
                with publication_lock(self.run):
                    staging, descriptor = export_snapshot(self.run, self.args, log, self.commands.check_resources)
                    if self.args.hf_dry_run:
                        log.emit("dry_run", f"Dry run: no upload performed | snapshot={staging} | prefix={descriptor['identity']['prefix']}")
                    else:
                        publisher.publish(staging, descriptor)
            return result
        except (Interrupted, KeyboardInterrupt):
            log.emit("interrupted", "Upload interrupted; local results retained", "WARN")
            log.emit("recovery", recovery_command(self.args, self.work))
            raise
        except (hf_auth.HFError, OSError, ValueError, KeyError, TypeError) as error:
            code = error.code if isinstance(error, hf_auth.HFError) else "invalid_results"
            log.emit("failed", f"Upload failed | reason={code} | evaluation_exit_code={result} | upload_status=failed", "ERROR", error_code=code)
            if isinstance(error, hf_auth.HFError):
                log.emit("failure_detail", str(error), "ERROR", error_code=code)
            if publisher:
                with suppress(OSError):
                    publisher.state("failed", error_code=code, evaluation_exit_code=result)
            log.emit("local_results", f"Local results retained: {self.run}")
            if result is None and self.args.phase != "upload":
                log.emit("not_started", "Evaluation did not complete; fix the error before resuming the requested evaluation phase")
            else:
                log.emit("recovery", "Restore credentials/network access if needed, then retry: " + recovery_command(self.args, self.work))
            return result or (2 if code in {"invalid_results", "identity_conflict", "configuration"} else 3)

    def execute_evaluation(self):
        self.run.mkdir(parents=True, exist_ok=True)
        with lock(self.run / ".lock", "another invocation owns this run-id"):
            stage("plan")
            progress(f"Run: {self.args.run_id} | requested phase: {self.args.phase} | CUDA: {self.args.cuda_flavor}")
            progress("Validating frozen manifest/source" if self.manifest_path.exists() else "Sampling instances and freezing source")
            options = {name: getattr(self.args, name) for name in ("setting", "tasks", "sampling_seed", "samples_per_difficulty",
                       "agent_wall_clock_s", "concurrency", "resume")}
            new_manifest = not self.manifest_path.exists()
            self.manifest = sampling.prepare_manifest(self.run, **options)
            if new_manifest and self.args.results_to_hf:
                from difficulty_results_hf import utc
                sampling.atomic_json(self.run / "run-created.json", dict(created_at=utc()))
            profile_path = self.run / "cuda-profile.json"
            profile = dict(cuda_flavor=self.args.cuda_flavor)
            if profile_path.exists() and read_json(profile_path) != profile:
                raise EvaluationError("CUDA profile changed; use a new run-id")
            if not profile_path.exists():
                sampling.atomic_json(profile_path, profile)
            if self.delivery:
                source_identity = read_json(self.run / "source_identity.json")
                if source_identity.get("release_id") != self.delivery.release_id:
                    raise EvaluationError("run belongs to a different release; resume with its original controller")
            progress(f"Planning complete: {self.manifest['instance_count']} instances, {self.manifest['trial_count']} trials, "
                     f"agent budget {self.manifest['settings']['agent_wall_clock_s']}s | {self.manifest_path}")
            if self.args.phase == "plan":
                return 0
            self.load_collector()
            if self.args.phase == "collect":
                return self.collect(announce=True)
            self.budget = self.manifest["settings"]["agent_wall_clock_s"]
            self.source_sha = self.manifest["source_sha256"]
            self.image = "topogym-local/rcb-topogym-difficulty:" + self.source_sha[:20] + "-" + self.args.cuda_flavor
            self.commands.env.update(TOPOGYM_TOOL_IMAGE=self.image, TOPOGYM_RUN_ROOT=str(self.run), TOPOGYM_RUN_ID=self.args.run_id)
            previous = self.run / "resource-stop.json"
            if previous.exists():
                previous.rename(self.run / f"resource-stop.{time.time_ns()}.json")
            if self.args.phase in ("run", "all"):
                self.auth_env, identity = authentication(self.args, self.commands.env)
                path = self.run / "execution.lock.json"
                if path.exists() and read_json(path) != identity:
                    raise EvaluationError("execution configuration changed; use a new run-id")
                if not path.exists():
                    sampling.atomic_json(path, identity)
            if self.commands.run_command(["docker", "info"])[0]:
                raise EvaluationError("Docker daemon is not accessible")
            with ExitStack() as resources:
                resources.enter_context(lock(self.run.parent / ".gpu.lock", "another difficulty run owns the GPU execution lock"))
                if self.delivery:
                    resources.enter_context(self.delivery.gpu_lock())
                    self.gpu_device = self.delivery.gpu_uuid
                    self.gpu_ready()
                    self.image = self.delivery.ensure_images(self.source)
                    self.delivery.environment_check(self.source)
                    self.commands.env.update(TOPOGYM_TOOL_IMAGE=self.image)
                    if self.auth_env:
                        for key, value in self.commands.env.items():
                            if key.startswith("TOPOGYM_") or key == "TMPDIR":
                                self.auth_env[key] = value
                    sampling.atomic_json(self.run / "controller.json", dict(owner=self.delivery.owner,
                        workspace=self.delivery.workspace, release_id=self.delivery.release_id, gpu_uuid=self.gpu_device,
                        image_id=self.delivery.inspect(self.delivery.owner)["Image"]))
                self.owns_gpu_lock = True
                try:
                    for phase in (("prepare", "preflight", "run") if self.args.phase == "all" else (self.args.phase,)):
                        stage(phase)
                        getattr(self, "run_trials" if phase == "run" else phase)()
                        if phase in ("prepare", "preflight"):
                            self.require_phase_complete(phase)
                            progress(f"{phase} complete: all {self.manifest['instance_count']} instances passed")
                    result = self.collect(announce=True)
                    if self.args.phase in ("prepare", "preflight"):
                        return 0
                    return result
                except BaseException:
                    # Preserve evidence while still holding both locks, even on a signal.
                    self.commands.stop()
                    self.cleanup_containers()
                    with suppress(Exception):
                        self.redact_outputs()
                    with suppress(Exception):
                        self.collect()
                    raise
                finally:
                    self.owns_gpu_lock = False

    def build_dir(self, row):
        return self.run / "build" / row["slug"]

    def require_phase_complete(self, phase):
        """Gate the next stage on every planned sample, including before canary."""
        marker = {"prepare": "prepared.json", "preflight": "preflight.ok.json"}[phase]
        missing = [row["slug"] for row in self.manifest["instances"] if not (self.build_dir(row) / marker).is_file()]
        if missing:
            raise EvaluationError(f"{phase} phase incomplete; model execution blocked: " + ", ".join(missing))
        if phase == "preflight":
            self.verify_image()
            self.verify_packages()
            for row in self.manifest["instances"]:
                proof = read_json(self.build_dir(row)/marker)
                if proof.get("passed") is not True or proof.get("evidence_identity") != self.preflight_identity(row):
                    raise EvaluationError("preflight evidence is stale; rerun preflight: " + row["slug"])

    def task_dir(self, row, mode="unlimited"):
        suffix = {"unlimited": "-privileged", "limited": "-standard"}[mode]
        return self.run / "tasks" / (row["slug"] + suffix)

    def resource_labels(self):
        if self.delivery:
            return self.delivery.labels()
        workspace = hashlib.sha256(str(self.work.resolve()).encode()).hexdigest()
        owner = hashlib.sha256(str(self.run.resolve()).encode()).hexdigest()
        return {"topogym.workspace": workspace, "topogym.difficulty-run": self.args.run_id,
                "topogym.owner": "local-" + owner, "topogym.role": "work"}

    def cleanup_containers(self):
        if not self.owns_gpu_lock:
            return
        if self.delivery:
            self.delivery.cleanup()
            return
        labels = self.resource_labels()
        filters = [part for key, value in labels.items() for part in ("--filter", f"label={key}={value}")]
        with suppress(OSError, EvaluationError):
            _, output = self.commands.run_command(["docker", "ps", "-aq", *filters], capture=True, timeout=15)
            for ident in output.splitlines():
                if not re.fullmatch(r"[a-f0-9]{12,64}", ident):
                    continue
                self.remove_owned_container(ident)

    def remove_owned_container(self, ident):
        code, detail = self.commands.run_command(["docker", "inspect", ident], capture=True, timeout=15)
        if code:
            return
        try:
            container = json.loads(detail)[0]
            actual = container["Config"].get("Labels") or {}
            if all(actual.get(k) == v for k, v in self.resource_labels().items()):
                self.commands.run_command(["docker", "rm", "-f", container["Id"]], timeout=30)
        except (ValueError, KeyError, IndexError, TypeError):
            return  # fail closed on incomplete ownership evidence

    def redact_outputs(self):
        if self.auth_env is None:
            return
        args = ["--process-env", "--var", "OPENAI_API_KEY", "--var", "OPENROUTER_API_KEY", "--redact"]
        targets = ([self.jobs] if self.jobs.is_dir() else []) + list(self.run.glob("d*-a*.log")) + list(self.run.glob("canary-a*.log"))
        auths = [None]
        backups = []
        if self.args.auth == "subscription":
            if self.delivery:
                backups = list(self.args.auth_json.parent.glob(".scan-auth-*.json"))
            auths = [self.args.auth_json, *backups]
        # Scan pre-refresh and current tokens separately; no credential archive in jobs.
        for auth in auths:
            auth_args = ["--codex-auth", str(auth)] if auth else []
            for path in targets:
                self.commands.run_command([self.python, self.source / "scripts/scan_secrets.py", path, *args, *auth_args], env=self.auth_env, check=True)
        for path in backups:
            path.unlink()

    def gpu_ready(self):
        deadline = time.monotonic() + self.args.gpu_wait_s
        next_notice = 0
        while True:
            code, output = self.commands.run_command(["nvidia-smi", "-i", self.gpu_device, "--query-gpu=memory.free,utilization.gpu",
                                                      "--format=csv,noheader,nounits"], capture=True, timeout=15)
            if code:
                raise EvaluationError("GPU unavailable: nvidia-smi failed")
            free, utilization = map(int, output.strip().split(","))
            if free >= self.args.gpu_min_free_mb and utilization < 10:
                if next_notice:
                    progress(f"GPU {self.gpu_device} ready; continuing")
                return
            if time.monotonic() >= deadline:
                raise EvaluationError("GPU busy; bounded wait expired, no other process was stopped")
            if time.monotonic() >= next_notice:
                progress(f"Waiting for GPU {self.gpu_device}: {free} MiB free, {utilization}% utilization; "
                         f"up to {max(0, int(deadline - time.monotonic()))}s remaining")
                next_notice = time.monotonic() + 30
            time.sleep(2)

    def image_info(self):
        _, output = self.commands.run_command(["docker", "image", "inspect", self.image], capture=True, check=True, timeout=30)
        return json.loads(output)[0]

    def verify_image(self):
        path = self.run / "image.json"
        if not path.exists():
            raise EvaluationError("prepare phase has not built an image")
        expected, actual = read_json(path), self.image_info()
        if self.delivery:
            self.delivery.verify_images()
            if (expected.get("release_id") != self.delivery.release_id or expected["source_sha256"] != self.source_sha
                    or expected.get("gpu_uuid") != self.gpu_device or expected["id"] != actual["Id"]
                    or expected.get("images") != self.delivery.images):
                raise EvaluationError("frozen release/image/GPU identity changed")
            return
        if (expected["id"] != actual["Id"] or expected["source_sha256"] != self.source_sha
                or (actual["Config"].get("Labels") or {}).get("topogym.source") != self.source_sha):
            raise EvaluationError("frozen image identity changed")

    def verify_packages(self):
        for row in self.manifest["instances"]:
            marker = self.build_dir(row) / "prepared.json"
            if marker.exists():
                for name, sha in read_json(marker)["files"].items():
                    if sampling.file_hash(self.run / name) != sha:
                        raise EvaluationError("prepared package changed: " + name)

    def docker_sim(self, *args):
        from difficulty_delivery import label_args
        labels = self.resource_labels()
        user = ["--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"] if self.delivery else []
        return ["docker", "run", "--rm", "--runtime", "nvidia", "--gpus", f"device={self.gpu_device}", *label_args(labels),
                *user, "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "RCB_SESSION_LOG=",
                "-e", "NVIDIA_VISIBLE_DEVICES=" + self.gpu_device,
                "-v", f"{self.run}:{self.run}", "-w", self.run, self.image, *args]

    @staticmethod
    def valid_blanket_state(state):
        try:
            manifest = read_json(state)
            arrays = manifest["arrays"]
            payload = state.parent / arrays["path"]
            return (payload.resolve().is_relative_to(state.parent.resolve())
                    and sampling.file_hash(payload) == arrays["sha256"]
                    and state.stat().st_mode & 0o044 == 0o044
                    and payload.stat().st_mode & 0o044 == 0o044)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def prepare_blanket(self, row, build):
        """Publish only complete assets; keep interrupted attempts for diagnosis."""
        with lock(build / ".blanket.lock", "another preparation owns this instance"):
            pointer = build / "blanket.prepared.json"
            if pointer.exists():
                try:
                    record = read_json(pointer)
                    state = Path(record["state"])
                except (OSError, ValueError, KeyError, TypeError):
                    record, state = {}, build / "missing-preparation-manifest"
                if (record.get("seed") == row["scene_seed"] and record.get("source") == self.source_sha
                        and self.valid_blanket_state(state) and sampling.file_hash(state) == record["sha256"]):
                    return state
            legacy = build / "blanket/state/manifest.json"
            if not pointer.exists() and self.valid_blanket_state(legacy):
                return legacy
            attempts = sorted(build.glob("blanket-attempt-[0-9][0-9][0-9]"))
            if len(attempts) >= 3:
                progress(f"Blanket preparation exhausted 3 attempts; preserved logs: {build}", error=True)
                return None
            number = max([int(p.name.rsplit('-', 1)[1]) for p in attempts] + [0]) + 1
            attempt = build / f"blanket-attempt-{number:03d}"
            # The preparation CLI owns creation of this directory. A failed CLI
            # is still counted, even if it exited before creating its output.
            code, _ = self.commands.run_command(self.docker_sim("python", self.source / "scripts/prepare_blanket_initial_states.py",
                "--seeded", "--seed", row["scene_seed"], "--acceptance", "scene_layout", "--output", attempt),
                log=build / f"blanket-attempt-{number:03d}.log", monitor=True)
            attempt.mkdir(exist_ok=True)
            state = attempt / "state/manifest.json"
            if code or not self.valid_blanket_state(state):
                progress(f"Blanket preparation incomplete; preserved {attempt}", error=True)
                return None
            sampling.atomic_json(pointer, dict(state=str(state), sha256=sampling.file_hash(state),
                                               seed=row["scene_seed"], source=self.source_sha))
            return state

    def prepare(self):
        self.gpu_ready()
        if self.delivery and not (self.run / "image.json").exists():
            sampling.atomic_json(self.run / "image.json", dict(image=self.image, id=self.image_info()["Id"],
                source_sha256=self.source_sha, release_id=self.delivery.release_id,
                gpu_uuid=self.gpu_device, images=self.delivery.images))
        elif not (self.run / "image.json").exists():
            from cuda_profiles import build_args, check_driver
            if self.args.cuda_flavor == 'cu130':
                _, version = self.commands.run_command(['nvidia-smi', '-i', self.gpu_device,
                    '--query-gpu=driver_version', '--format=csv,noheader'], capture=True, check=True, timeout=30)
                check_driver(self.args.cuda_flavor, version.strip())
            arguments = [arg for key, value in build_args(self.source, self.args.cuda_flavor).items()
                         for arg in ('--build-arg', f'{key}={value}')]
            progress(f"Building frozen source image: {self.image} | log: {self.run / 'image-build.log'}")
            self.commands.run_command(["docker", "build", "--label", "topogym.source=" + self.source_sha, "-t", self.image,
                *arguments, "-f", self.source / "images/topogym/Dockerfile", self.source], log=self.run / "image-build.log", monitor=True, check=True)
            sampling.atomic_json(self.run / "image.json", dict(image=self.image, id=self.image_info()["Id"], source_sha256=self.source_sha))
        self.verify_image()
        self.verify_packages()
        for index, row in enumerate(self.manifest["instances"], 1):
            build = self.build_dir(row)
            build.mkdir(parents=True, exist_ok=True)
            if (build / "prepared.json").exists():
                task_progress(row, index, self.manifest["instance_count"], "skip: already prepared")
                continue
            task_progress(row, index, self.manifest["instance_count"], "preparing")
            progress(f"Preparation log: {build / 'prepare.log'}")
            self.gpu_ready()
            params = []
            if row["task_id"] == "blanket_flatten":
                state = self.prepare_blanket(row, build)
                if state is None:
                    continue
                sampling.atomic_json(build / "parameters.json", dict(initial_state_path=str(state), initial_state_resource=None,
                                                                    initial_state_sha256=sampling.file_hash(state)))
                params = ["--task-parameters", build / "parameters.json"]
            instance_path = self.task_dir(row) / "environment/instance.json"
            selection = ["--variation", "seeded", "--scene-seed", row["scene_seed"]]
            if instance_path.exists():
                self.check_selection(row, read_json(instance_path))
                selection, params = ["--instance", instance_path], []
            code, _ = self.commands.run_command([self.python, self.source / "scripts/topogym_mk_task.py", row["task_id"], *selection,
                "--slug", row["slug"], "--tasks-root", self.run / "tasks", "--build-root", self.run / "build", "--image", self.image,
                "--agent-wall-clock-s", self.budget, *params], log=build / "prepare.log", monitor=True)
            if code:
                progress(f"Preparation blocked: {row['slug']}; see {build / 'prepare.log'}", error=True)
                continue
            code, _ = self.commands.run_command([self.python, self.source / "scripts/topogym_mk_limited.py", row["task_id"], "-",
                "--unlimited-task", self.task_dir(row), "--tasks-root", self.run / "tasks", "--build-root", self.run / "build",
                "--agent-wall-clock-s", self.budget], log=build / "prepare.log", append=True, monitor=True)
            if code == 0:
                self.freeze_package(row)
                progress(f"Prepared: {row['slug']}")
            else:
                progress(f"Limited package preparation failed; see {build / 'prepare.log'}", error=True)
        tasks = self.run / "tasks"
        tasks.mkdir(exist_ok=True)
        text = '[dataset]\nname = "topogym/difficulty-eval"\nversion = "0.1.0"\n'
        for path in sorted(tasks.glob("*/task.toml")):
            text += f'\n[[tasks]]\nname = "topogym/{path.parent.name}"\npath = "{path.parent.name}"\n'
        (tasks / "dataset.toml").write_text(text)

    @staticmethod
    def check_selection(row, instance):
        if (instance.get("task"), instance.get("variation_id"), instance.get("seed")) != (row["task_id"], "seeded", row["scene_seed"]):
            raise EvaluationError("frozen instance selection mismatch; use a new run-id")

    def freeze_package(self, row):
        import yaml
        instance_path = self.task_dir(row) / "environment/instance.json"
        instance = read_json(instance_path)
        self.check_selection(row, instance)
        if instance["resolved_variation_id"] != row["resolved_variation_id"]:
            raise EvaluationError("frozen instance does not match manifest selection")
        files = {}
        for mode in sampling.MODES:
            folder = self.task_dir(row, mode)
            if not (folder / "tests/docker-compose.yaml").exists():
                (folder / "tests/docker-compose.yaml").write_text("services:\n  main: {}\n")
            for path in folder.rglob("docker-compose.yaml"):
                data = yaml.safe_load(path.read_text())
                for service in data["services"].values():
                    service.setdefault("labels", {}).update(self.resource_labels())
                if self.delivery:
                    from difficulty_delivery import decorate_compose
                    decorate_compose(data, self.delivery.labels(), self.gpu_device, uid=os.getuid(), gid=os.getgid())
                path.write_text(yaml.safe_dump(data, sort_keys=False))
            files.update({str(path.relative_to(self.run)): sampling.file_hash(path) for path in sorted(folder.rglob("*")) if path.is_file()})
        out = self.run / "instances" / row["task_id"] / row["difficulty"] / row["sample_id"]
        out.mkdir(parents=True, exist_ok=True)
        sampling.atomic_json(out / "identity.json", dict(instance=str(instance_path), sha256=sampling.file_hash(instance_path), sample_sha256=row["sample_sha256"]))
        sampling.atomic_json(self.build_dir(row) / "prepared.json", dict(files=files))

    def preflight_identity(self, row):
        """Bind a pass to actual package bytes and the verified runtime, not a filename."""
        _, gpu = self.commands.run_command(["nvidia-smi", "-i", self.gpu_device,
            "--query-gpu=uuid,name,driver_version,compute_cap", "--format=csv,noheader"],
            capture=True, check=True, timeout=15)
        client_proof = self.build_dir(row)/"limited-client-image.json"
        client = None
        if client_proof.exists():
            client = read_json(client_proof)
            _, current = self.commands.run_command(["docker", "image", "inspect", "--format", "{{.Id}}", client["image"]],
                                                  capture=True, check=True, timeout=15)
            client = dict(client, id=current.strip())
        return dict(probe_version=5, prepared_sha256=sampling.file_hash(self.build_dir(row)/"prepared.json"),
                    tool_sha256=sampling.file_hash(self.task_dir(row)/"environment/rcb_topogym.py"),
                    image=read_json(self.run/"image.json"), gpu_device=self.gpu_device, gpu_profile=gpu.strip(),
                    client_image=client, probe_sha256=sampling.file_hash(self.source/"scripts/difficulty_eval.py"))

    def preflight(self):
        self.verify_image()
        self.verify_packages()
        checks = ("check-task-structure", "check-task-fields", "check-dockerfile", "check-instruction", "check-verifier-isolation", "check-limited-texts")
        for index, row in enumerate(self.manifest["instances"], 1):
            build = self.build_dir(row)
            if not (build / "prepared.json").exists():
                task_progress(row, index, self.manifest["instance_count"], "blocked: not prepared")
                continue
            evidence = self.preflight_identity(row)
            tool = self.task_dir(row) / "environment/rcb_topogym.py"
            previous = read_json(build / "preflight.ok.json") if (build / "preflight.ok.json").exists() else {}
            if ((build / "preflight.ok.json").exists()
                    and previous.get("passed") is True and previous.get("evidence_identity") == evidence):
                task_progress(row, index, self.manifest["instance_count"], "skip: preflight already passed")
                continue
            task_progress(row, index, self.manifest["instance_count"], "preflight")
            progress(f"Preflight log: {build / 'preflight.log'}")
            for name in ("smoke", "limited"):
                if (build / name).exists():
                    (build / name).rename(build / f"{name}.previous.{time.time_ns()}")
            codes = [self.commands.run_command(["bash", self.source / "ci_checks" / f"{check}.sh", self.task_dir(row, mode)],
                     log=build / "preflight.log", append=True)[0] for mode in sampling.MODES for check in checks]
            if any(codes):
                progress(f"Preflight static checks failed; see {build / 'preflight.log'}", error=True)
                continue
            self.gpu_ready()
            common = ["--task", row["task_id"], "--instance", self.task_dir(row) / "environment/instance.json"]
            code, _ = self.commands.run_command(self.docker_sim("python", tool, "smoke", *common, "--out-dir", build / "smoke"),
                log=build / "preflight.log", append=True, monitor=True)
            if code:
                progress(f"Preflight simulation smoke failed; see {build / 'preflight.log'}", error=True)
                continue
            code, _ = self.commands.run_command(self.docker_sim("python", tool, "replay", *common, "--traj", build / "smoke/trajectory.npz", "--repeat", "1", "--strict"),
                log=build / "preflight.log", append=True, monitor=True)
            if code or not self.limited_preflight(row):
                progress(f"Preflight replay/limited check failed; see {build / 'preflight.log'}", error=True)
                continue
            proof = read_json(build / "prepared.json")
            proof.update(passed=True, scope="short_build_action_reset_rgb_and_limited_protocol_deadline", solvability_proven=False,
                         evidence_identity=self.preflight_identity(row))
            sampling.atomic_json(build / "preflight.ok.json", proof)
            progress(f"Preflight passed: {row['slug']}")

    def limited_preflight(self, row):
        build, task = self.build_dir(row), self.task_dir(row, "limited")
        (build / "limited").mkdir(parents=True)
        owner = self.resource_labels()["topogym.owner"][-12:]
        container = f"tg-check-{owner}-{row['slug'].removeprefix('topogym-')}"
        # Probe the generated standard client's pinned recipe, including in Docker delivery.
        # The controller/canary image is a different role and cannot stand in for this image.
        client_image = f"topogym-local/preflight-client:{self.source_sha[:12]}"
        self.commands.run_command(["docker", "build", "-t", client_image, task/"environment"],
                                  log=build/"client-build.log", monitor=True, check=True)
        _, client_id = self.commands.run_command(["docker", "image", "inspect", "--format", "{{.Id}}", client_image],
                                                capture=True, check=True, timeout=15)
        sampling.atomic_json(build/"limited-client-image.json", dict(image=client_image, id=client_id.strip()))
        client_cmd = ["docker", "run", "--rm", "--name", container+"-client", "--network", "container:"+container,
                      "-i", "-w", "/tmp", "-e", "PYTHONPATH=/check"]
        for name in ("rcb_client.py", "rcb1.py"):
            client_cmd += ["-v", f"{task}/environment/{name}:/check/{name}:ro"]
        from difficulty_delivery import label_args
        client_cmd += label_args(self.resource_labels())
        if self.delivery:
            client_cmd += ["--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
        client_cmd += [client_image, "python", "-"]
        cmd = ["docker", "run", "-d", "--name", container, "--restart", "on-failure:6", "--runtime", "nvidia", "--gpus", f"device={self.gpu_device}", "--network", "none",
               *label_args(self.resource_labels()), "-w", "/tmp"]
        if self.delivery:
            from difficulty_delivery import label_args
            cmd += [*label_args(self.delivery.labels()), "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
        for value in ("NVIDIA_DRIVER_CAPABILITIES=all", "RCB_TASK=" + row["task_id"], "RCB_INSTANCE=/srv/instance.json",
                      "NVIDIA_VISIBLE_DEVICES=" + self.gpu_device,
                      "RCB_WALL_CLOCK_S=30", "RCB_DATA=/data", "PYTHONPATH=/srv:/check:/opt/topogym"):
            cmd += ["-e", value]
        cmd += ["-v", f"{task}/environment/sim:/srv:ro", "-v", f"{task}/environment:/check:ro", "-v", f"{build}/limited:/data",
                self.image, "sh", "/srv/run.sh"]
        try:
            if self.commands.run_command(cmd, log=build / "preflight.log", append=True)[0]:
                return False
            if self.commands.run_command(client_cmd, input_text=LIMITED_SMOKE,
                    log=build / "preflight.log", append=True, monitor=True)[0]:
                return False
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                self.commands.check_resources()
                data = self.collector.load_json(build / "limited/final.json")
                if data.get("done") or data.get("finalized"):
                    # The live service dumps and exits; run.sh keeps the container alive
                    # while the same collect hook as Harbor performs a fresh replay.
                    code, _ = self.commands.run_command(
                        ["docker", "exec", "-e", "RCB_COLLECT_END_TIMEOUT_S=900", container, "sh", "/srv/finalize.sh"],
                        log=build/"preflight.log", append=True, monitor=True, timeout=1800)
                    data = self.collector.load_json(build / "limited/final.json")
                    passed = (code == 0 and data.get("finalized") is True
                              and isinstance(data.get("replay_success"), bool)
                              and data.get("video") is True and (build/"limited/replay.mp4").is_file()
                              and not any(data.get(key) for key in ("infra_error", "gpu_lost", "error"))
                              and data.get("reason") in ("timeout", "success"))
                    with (build / "preflight.log").open("a") as stream:
                        stream.write("limited deadline and finalization " + ("passed\n" if passed else "failed\n"))
                    return passed
                time.sleep(2)
            return False
        finally:
            self.commands.run_command(["docker", "logs", container], log=build / "limited/server.log", timeout=15)
            self.remove_owned_container(container+"-client")
            self.remove_owned_container(container)

    def launch_job(self, task, job):
        if self.delivery:
            sampling.atomic_json(self.run / "active-job.json", dict(owner=self.delivery.owner, job=job, started_at=time.time()))
            if self.args.auth == "subscription":
                backup = self.args.auth_json.parent / f".scan-auth-{time.time_ns()}.json"
                backup.write_bytes(self.args.auth_json.read_bytes())
        cmd = [self.harbor, "run", "-p", task, "-a", self.args.agent, "-m", self.args.model, "-n", "1", "-k", "1",
               "--max-retries", "0", "-o", self.jobs, "--job-name", job]
        for arg in self.args.agent_arg:
            cmd += ["--ak", arg]
        login = "chatgpt" if self.args.auth == "subscription" else "api"
        cmd += ["--ak", 'config={"forced_login_method":"' + login + '"}']
        (self.jobs / job).mkdir()  # reserve before launch; interruption never reuses the attempt
        progress(f"Harbor job: {job} | log: {self.run / (job + '.log')}")
        try:
            code, _ = self.commands.run_command(cmd, log=self.run / f"{job}.log", env=self.auth_env, monitor=True)
            with (self.run / "exit_codes.tsv").open("a") as stream:
                stream.write(f"{job}\t{code}\n")
        finally:
            self.cleanup_containers()
            self.redact_outputs()
        trials = [path.parent for path in (self.jobs / job).glob("*/result.json")]
        if trials:
            account_code, _ = self.commands.run_command([self.python, self.source / "scripts/account_failure_check.py", *trials],
                                                       log=self.jobs / job / "account-check.jsonl")
            code = account_code or code
        return code

    def canary_passed(self, job):
        results = list(job.glob("*/result.json"))
        data = self.collector.load_json(results[0]) if len(results) == 1 else {}
        return bool(data.get("finished_at") and not data.get("exception_info") and
                    ((data.get("verifier_result") or {}).get("rewards") or {}).get("success") == 1)

    def prepare_canary(self):
        valid = [path.parent for path in sorted((self.run / "build").glob("*/preflight.ok.json"))]
        if not valid:
            raise EvaluationError("no sample has passed preflight")
        folder = self.run / "canary/tasks/topogym-auth-canary"
        if (folder / "prepared.json").is_file():
            return folder
        if folder.exists():
            folder.rename(folder.with_name(folder.name + f".incomplete.{time.time_ns()}"))
        for sub in ("environment", "tests", "solution"):
            (folder / sub).mkdir(parents=True)
        images = list((valid[0] / "smoke/initial_rgb").glob("*.png"))
        if not images:
            raise EvaluationError("preflight camera image missing")
        shutil.copy(images[0], folder / "environment/camera.png")
        image = self.delivery.images["client"]["image"] if self.delivery else self.image
        (folder / "environment/Dockerfile").write_text(f"FROM {image}\nCOPY camera.png /app/camera.png\nRUN mkdir -p /app/output\nWORKDIR /app\n")
        (folder / "environment/docker-compose.yaml").write_text("services:\n  main:\n    labels: " + json.dumps(self.resource_labels()) + "\n")
        if self.delivery:
            import yaml
            from difficulty_delivery import decorate_compose
            path = folder / "environment/docker-compose.yaml"
            path.write_text(yaml.safe_dump(decorate_compose(yaml.safe_load(path.read_text()),
                self.delivery.labels(), self.gpu_device), sort_keys=False))
        (folder / "instruction.md").write_text('Authentication/tool canary. Use a shell command to inspect /app/camera.png, then use your image viewing tool to view it. '
            'Write /app/output/canary.json containing {"ready": true, "image_description": "a short description of what you see"}. Do not start a simulator. This check is separate from task scoring.\n')
        (folder / "README.md").write_text("Short authentication, shell and image canary; not a task-solving trial.\n")
        (folder / "tests/test.sh").write_text(CANARY_VERIFIER)
        (folder / "tests/test.sh").chmod(0o755)
        (folder / "solution/solve.sh").write_text("#!/bin/bash\nexit 1\n")
        (folder / "solution/solve.sh").chmod(0o755)
        (folder / "task.toml").write_text('schema_version = "1.3"\nartifacts = ["/app/output/"]\n[task]\nname = "topogym/topogym-auth-canary"\n'
            f'[agent]\ntimeout_sec = {min(600, self.budget)}\n[verifier]\ntimeout_sec = 120\n[environment]\nbuild_timeout_sec = 1800\n')
        sampling.atomic_json(folder / "prepared.json", dict(complete=True))
        return folder

    def canary(self):
        attempts = sorted(self.jobs.glob("canary-a[0-9][0-9][0-9]"))
        if attempts and self.canary_passed(attempts[-1]):
            progress(f"Canary: skip; {attempts[-1].name} already passed")
            return
        if attempts and not self.args.rerun_incomplete:
            raise EvaluationError("previous canary incomplete/failed; use --resume --rerun-incomplete to create a new attempt")
        number = int(attempts[-1].name[-3:]) + 1 if attempts else 1
        if number > 999:
            raise EvaluationError("too many canary attempts")
        folder = self.prepare_canary()
        job = f"canary-a{number:03d}"
        progress(f"Authentication/tool/image canary: {job} (excluded from task statistics)")
        if self.launch_job(folder, job) or not self.canary_passed(self.jobs / job):
            raise EvaluationError("authentication/tool/image canary failed; task queue not started")
        progress(f"Canary passed: {job}")

    def run_trials(self):
        self.verify_image()
        self.verify_packages()
        self.require_phase_complete("prepare")
        self.require_phase_complete("preflight")
        if not os.access(self.harbor, os.X_OK):
            raise EvaluationError("Harbor executable missing: set TOPOGYM_HARBOR")
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.canary()
        for index, row in enumerate(self.manifest["instances"], 1):
            for mode_index, mode in enumerate(sampling.MODES, 1):
                trial_index = (index - 1) * len(sampling.MODES) + mode_index
                task = self.task_dir(row, mode)
                stem = f"d{row['task_number']:02d}-{row['difficulty']}-{row['sample_id']}-{mode}"
                attempts = sorted(self.jobs.glob(stem + "-a[0-9][0-9][0-9]"))
                if attempts and not (self.args.rerun_incomplete and self.collector.classify_trial(attempts[-1], row, mode)[0] in RETRYABLE):
                    task_progress(row, trial_index, self.manifest["trial_count"], f"skip: preserving {attempts[-1].name}", mode=mode)
                    continue
                number = int(attempts[-1].name[-3:]) + 1 if attempts else 1
                if number > 999:
                    raise EvaluationError("too many attempts")
                job = f"{stem}-a{number:03d}"
                task_progress(row, trial_index, self.manifest["trial_count"], f"starting attempt {number}", mode=mode)
                self.gpu_ready()
                self.verify_image()
                code = self.launch_job(task, job)
                self.collect()
                if code:
                    raise EvaluationError(f"Harbor failed; pending queue preserved (see {job}.log)")
                status = self.collector.classify_trial(self.jobs / job, row, mode)[0]
                progress(f"Trial result: {job} | status={status}")
                if status not in COMPLETE:
                    raise EvaluationError(f"trial infrastructure incomplete ({status}); pending queue preserved")


def on_signal(signum, frame):
    # A second signal must not interrupt artifact collection and owned-process cleanup.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise Interrupted()


def main(argv=None):
    os.umask(0o077)
    try:
        args = parse_args(argv)
        if args.work_dir:
            from difficulty_delivery import safe_work_dir
            args.work_dir = safe_work_dir(args.work_dir)
        if args.setting:
            args.setting = args.setting.resolve()
        if args.hf_token_file is not None:
            # Preserve invocation-relative host paths; read_token rejects symlinks.
            args.hf_token_file = args.hf_token_file.expanduser().absolute()
        os.chdir(ROOT)
        if args.list_tasks:
            for number, task in enumerate(sampling.TASK_IDS, 1):
                print(f"{number:2d}\t{task}")
            return 0
        handlers = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            with ExitStack() as session:
                if os.environ.get("TOPOGYM_CONTAINER") == "1" and args.auth == "subscription" and args.phase != "upload":
                    auth_home = Path(os.environ["CODEX_HOME"])
                    session.enter_context(lock(auth_home / ".auth.lock", "another operation is using this login"))
                    if args.auth_json:
                        data = args.auth_json.read_bytes()
                        import hashlib
                        imported = auth_home / "imports" / hashlib.sha256(data).hexdigest() / "auth.json"
                        if not imported.exists():
                            imported.parent.mkdir(parents=True, exist_ok=True)
                            imported.write_bytes(data)
                        args.auth_json = imported
                return DifficultyEvaluation(args).execute()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    except (Interrupted, KeyboardInterrupt):
        progress("Interrupted; existing attempts and evidence retained", error=True)
        return 130
    except (EvaluationError, ValueError, OSError, KeyError) as error:
        progress(f"ERROR: {error}", error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
