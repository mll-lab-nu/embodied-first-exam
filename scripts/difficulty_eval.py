#!/usr/bin/env python3
"""Prepare and run difficulty evaluations through the existing Harbor CLI.

The Bash entry point only launches this module. Sampling and result classification
remain in their dedicated modules; each sample/mode still gets one Harbor job.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager, suppress
import fcntl
import getpass
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
        epilog="Direct keys may enter shell history/process argv. Use --api-key without a value for hidden TTY input.")
    parser.add_argument("--run-id")
    parser.add_argument("--phase", choices=("plan", "prepare", "preflight", "run", "collect", "all"), default="all")
    parser.add_argument("--list-tasks", action="store_true")
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
    args = parser.parse_args(argv)
    if args.list_tasks:
        return args
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
            key = os.environ.get(variable, "")
        if not key or "\n" in key or "\r" in key:
            raise EvaluationError("API key missing/empty or contains newline")
        env["OPENAI_API_KEY" if args.provider == "openai" else "OPENROUTER_API_KEY"] = key
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
        if cpu >= 90 or memory >= 90:
            sampling.atomic_json(self.run / "resource-stop.json", dict(cpu_percent=cpu, memory_percent=memory,
                pid=self.child.pid if self.child else None))
            raise EvaluationError("CPU or memory reached 90%; owned work stopped; see resource-stop.json")

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


LIMITED_SMOKE = """from rcb_client import Robot
import numpy as np
r = Robot(base='http://localhost:8000'); spec = r.spec(); obs = r.get_obs()
assert obs.last and all(np.isfinite(v).all() for v in obs.last.values())
dim = spec['action_types']['joint_position']['dim']
q = np.asarray(obs.meta['proprio']['now'][:dim], dtype=np.float32)
res = r.submit('joint_position', q[None,:], dt=1/spec['control_hz'])
assert res.meta.get('ok') and res.last
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
        self.run = ROOT / "runs/difficulty_trials" / args.run_id
        self.jobs = ROOT / "jobs/difficulty_trials" / args.run_id
        self.source = self.run / "source"
        self.manifest_path = self.run / "manifest.lock.json"
        self.manifest = self.collector = self.auth_env = None
        self.owns_gpu_lock = False
        self.python = sys.executable
        self.harbor = os.environ.get("TOPOGYM_HARBOR", str(ROOT / ".venv-harbor/bin/harbor"))
        env = dict(os.environ)
        for name in (*AUTH_VARIABLES, args.api_key_env):
            if name:
                env.pop(name, None)
        env.update(PYTHONPATH=str(self.source), PATH=str(Path(self.python).parent) + os.pathsep + env.get("PATH", ""))
        self.commands = Commands(env, self.run)

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
        self.run.mkdir(parents=True, exist_ok=True)
        with lock(self.run / ".lock", "another invocation owns this run-id"):
            stage("plan")
            progress(f"Run: {self.args.run_id} | requested phase: {self.args.phase}")
            progress("Validating frozen manifest/source" if self.manifest_path.exists() else "Sampling instances and freezing source")
            options = {name: getattr(self.args, name) for name in ("setting", "tasks", "sampling_seed", "samples_per_difficulty",
                       "agent_wall_clock_s", "concurrency", "resume")}
            self.manifest = sampling.prepare_manifest(self.run, **options)
            progress(f"Planning complete: {self.manifest['instance_count']} instances, {self.manifest['trial_count']} trials, "
                     f"agent budget {self.manifest['settings']['agent_wall_clock_s']}s | {self.manifest_path}")
            if self.args.phase == "plan":
                return 0
            self.load_collector()
            if self.args.phase == "collect":
                return self.collect(announce=True)
            self.budget = self.manifest["settings"]["agent_wall_clock_s"]
            self.source_sha = self.manifest["source_sha256"]
            self.image = "topogym-local/rcb-topogym-difficulty:" + self.source_sha[:20]
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
            with lock(self.run.parent / ".gpu.lock", "another difficulty run owns the GPU execution lock"):
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

    def task_dir(self, row, mode="unlimited"):
        return self.run / "tasks" / (row["slug"] + ("-limited" if mode == "limited" else ""))

    def cleanup_containers(self):
        if not self.owns_gpu_lock:
            return
        with suppress(OSError, EvaluationError):
            _, output = self.commands.run_command(["docker", "ps", "-aq", "--filter", "label=topogym.difficulty-run=" + self.args.run_id], capture=True, timeout=15)
            ids = [line for line in output.splitlines() if re.fullmatch(r"[a-f0-9]{12,64}", line)]
            if ids:
                self.commands.run_command(["docker", "rm", "-f", *ids], timeout=30)

    def redact_outputs(self):
        if self.auth_env is None:
            return
        args = ["--process-env", "--var", "OPENAI_API_KEY", "--var", "OPENROUTER_API_KEY", "--redact"]
        if self.args.auth == "subscription":
            args += ["--codex-auth", str(self.args.auth_json)]
        targets = ([self.jobs] if self.jobs.is_dir() else []) + list(self.run.glob("d*-a*.log")) + list(self.run.glob("canary-a*.log"))
        for path in targets:
            self.commands.run_command([self.python, self.source / "scripts/scan_secrets.py", path, *args], env=self.auth_env, check=True)

    def gpu_ready(self):
        deadline = time.monotonic() + self.args.gpu_wait_s
        next_notice = 0
        while True:
            code, output = self.commands.run_command(["nvidia-smi", "-i", "0", "--query-gpu=memory.free,utilization.gpu",
                                                      "--format=csv,noheader,nounits"], capture=True, timeout=15)
            if code:
                raise EvaluationError("GPU unavailable: nvidia-smi failed")
            free, utilization = map(int, output.strip().split(","))
            if free >= self.args.gpu_min_free_mb and utilization < 10:
                if next_notice:
                    progress("GPU 0 ready; continuing")
                return
            if time.monotonic() >= deadline:
                raise EvaluationError("GPU busy; bounded wait expired, no other process was stopped")
            if time.monotonic() >= next_notice:
                progress(f"Waiting for GPU 0: {free} MiB free, {utilization}% utilization; "
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
        return ["docker", "run", "--rm", "--runtime", "nvidia", "--gpus", "device=0", "--label",
                "topogym.difficulty-run=" + self.args.run_id, "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "RCB_SESSION_LOG=",
                "-v", f"{self.run}:{self.run}", "-w", self.run, self.image, *args]

    def prepare(self):
        self.gpu_ready()
        if not (self.run / "image.json").exists():
            progress(f"Building frozen source image: {self.image} | log: {self.run / 'image-build.log'}")
            self.commands.run_command(["docker", "build", "--label", "topogym.source=" + self.source_sha, "-t", self.image,
                "-f", self.source / "images/topogym/Dockerfile", self.source], log=self.run / "image-build.log", monitor=True, check=True)
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
                state = build / "blanket/state/manifest.json"
                if not state.exists():
                    if (build / "blanket").exists():
                        progress(f"Preserving incomplete Blanket preparation: {build / 'blanket'}", error=True)
                        continue
                    code, _ = self.commands.run_command(self.docker_sim("python", self.source / "scripts/prepare_blanket_initial_states.py",
                        "--seeded", "--seed", row["scene_seed"], "--acceptance", "scene_layout", "--output", build / "blanket"),
                        log=build / "blanket.log", monitor=True)
                    if code:
                        progress(f"Blanket preparation failed; see {build / 'blanket.log'}", error=True)
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
            for path in folder.rglob("docker-compose.yaml"):
                data = yaml.safe_load(path.read_text())
                for service in data["services"].values():
                    service.setdefault("labels", {})["topogym.difficulty-run"] = self.args.run_id
                path.write_text(yaml.safe_dump(data, sort_keys=False))
            files.update({str(path.relative_to(self.run)): sampling.file_hash(path) for path in sorted(folder.rglob("*")) if path.is_file()})
        out = self.run / "instances" / row["task_id"] / row["difficulty"] / row["sample_id"]
        out.mkdir(parents=True, exist_ok=True)
        sampling.atomic_json(out / "identity.json", dict(instance=str(instance_path), sha256=sampling.file_hash(instance_path), sample_sha256=row["sample_sha256"]))
        sampling.atomic_json(self.build_dir(row) / "prepared.json", dict(files=files))

    def preflight(self):
        self.verify_image()
        self.verify_packages()
        checks = ("check-task-structure", "check-task-fields", "check-dockerfile", "check-instruction", "check-verifier-isolation", "check-limited-texts")
        tool = self.source / "harbor_templates/topogym/common/rcb_topogym.py"
        for index, row in enumerate(self.manifest["instances"], 1):
            build = self.build_dir(row)
            if not (build / "prepared.json").exists():
                task_progress(row, index, self.manifest["instance_count"], "blocked: not prepared")
                continue
            if (build / "preflight.ok.json").exists():
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
            proof.update(passed=True, scope="short_build_action_reset_rgb_and_limited_protocol_deadline", solvability_proven=False)
            sampling.atomic_json(build / "preflight.ok.json", proof)
            progress(f"Preflight passed: {row['slug']}")

    def limited_preflight(self, row):
        build, task = self.build_dir(row), self.task_dir(row, "limited")
        (build / "limited").mkdir(parents=True)
        container = f"tg-check-{self.source_sha[:12]}-{row['slug'].removeprefix('topogym-')}"
        cmd = ["docker", "run", "-d", "--name", container, "--runtime", "nvidia", "--gpus", "device=0", "--network", "none",
               "--label", "topogym.difficulty-run=" + self.args.run_id]
        for value in ("NVIDIA_DRIVER_CAPABILITIES=all", "RCB_TASK=" + row["task_id"], "RCB_INSTANCE=/srv/instance.json",
                      "RCB_WALL_CLOCK_S=30", "RCB_DATA=/data", "PYTHONPATH=/srv:/check:/opt/topogym"):
            cmd += ["-e", value]
        cmd += ["-v", f"{task}/environment/sim:/srv:ro", "-v", f"{task}/environment:/check:ro", "-v", f"{build}/limited:/data",
                self.image, "python", "/srv/server.py"]
        try:
            if self.commands.run_command(cmd, log=build / "preflight.log", append=True)[0]:
                return False
            if self.commands.run_command(["docker", "exec", "-i", container, "python", "-"], input_text=LIMITED_SMOKE,
                    log=build / "preflight.log", append=True, monitor=True)[0]:
                return False
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                self.commands.check_resources()
                data = self.collector.load_json(build / "limited/final.json")
                if data.get("video_done"):
                    passed = bool(data.get("finalized")) and data.get("replay_success") is not None and data.get("reason") in ("timeout", "success")
                    with (build / "preflight.log").open("a") as stream:
                        stream.write("limited deadline and finalization " + ("passed\n" if passed else "failed\n"))
                    return passed
                time.sleep(2)
            return False
        finally:
            self.commands.run_command(["docker", "logs", container], log=build / "limited/server.log", timeout=15)
            self.commands.run_command(["docker", "rm", "-f", container], timeout=30)

    def launch_job(self, task, job):
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
        if folder.exists():
            return folder
        for sub in ("environment", "tests", "solution"):
            (folder / sub).mkdir(parents=True)
        images = list((valid[0] / "smoke/initial_rgb").glob("*.png"))
        if not images:
            raise EvaluationError("preflight camera image missing")
        shutil.copy(images[0], folder / "environment/camera.png")
        (folder / "environment/Dockerfile").write_text(f"FROM {self.image}\nCOPY camera.png /app/camera.png\nRUN mkdir -p /app/output\nWORKDIR /app\n")
        (folder / "environment/docker-compose.yaml").write_text("services:\n  main:\n    labels:\n      topogym.difficulty-run: " + json.dumps(self.args.run_id) + "\n")
        (folder / "instruction.md").write_text('Authentication/tool canary. Use a shell command to inspect /app/camera.png, then use your image viewing tool to view it. '
            'Write /app/output/canary.json containing {"ready": true, "image_description": "a short description of what you see"}. Do not start a simulator. This check is separate from task scoring.\n')
        (folder / "README.md").write_text("Short authentication, shell and image canary; not a task-solving trial.\n")
        (folder / "tests/test.sh").write_text(CANARY_VERIFIER)
        (folder / "tests/test.sh").chmod(0o755)
        (folder / "solution/solve.sh").write_text("#!/bin/bash\nexit 1\n")
        (folder / "solution/solve.sh").chmod(0o755)
        (folder / "task.toml").write_text('schema_version = "1.3"\nartifacts = ["/app/output/"]\n[task]\nname = "topogym/topogym-auth-canary"\n'
            f'[agent]\ntimeout_sec = {min(600, self.budget)}\n[verifier]\ntimeout_sec = 120\n[environment]\nbuild_timeout_sec = 1800\n')
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
    os.chdir(ROOT)
    try:
        args = parse_args(argv)
        if args.list_tasks:
            for number, task in enumerate(sampling.TASK_IDS, 1):
                print(f"{number:2d}\t{task}")
            return 0
        handlers = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
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
