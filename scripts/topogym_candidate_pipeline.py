#!/usr/bin/env python3
"""Resume a frozen candidate build of the active release, exact restore, Harbor nop checks and activation.

Environment qualification and oracle success are separate. This command never
inherits success from historical runs or edits their task packages.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from topogym_versions import identity, require_task, task_lock, digest
from topogym.planning.harbor_bridge.binding import bind_tasks, inspect_image, inspect_runtime, preflight
from topogym.utils.process_limits import run_guarded
from difficulty_eval import EvaluationError


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(path)


def gpu_ready(gpu):
    """Check GPU accessibility once, without a memory or utilization threshold."""
    subprocess.run(["nvidia-smi", "-i", gpu, "--query-gpu=uuid", "--format=csv,noheader"],
                       capture_output=True, text=True, timeout=20, check=True)


class Pipeline:
    def __init__(self, args):
        self.args, self.folder = args, args.candidate.resolve()
        self.document = read(self.folder / "candidate.json")
        self.source = Path(self.document["source_snapshot"])
        if hashlib.sha256((self.folder / "source_manifest.json").read_bytes()).hexdigest() != self.document["source_manifest_sha256"]:
            raise ValueError("Candidate source manifest was modified")
        for name, expected in read(self.folder / "source_manifest.json").items():
            if hashlib.sha256((self.source / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Candidate source was modified: {name}")
        for name, expected in self.document["input_hashes"].items():
            if hashlib.sha256((self.folder / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Candidate recipe/input was modified: {name}")
        self.release = identity(self.source)
        if self.release != identity(ROOT):
            raise ValueError("Candidate definition differs from the active source; prepare a new candidate")
        self.image = inspect_image(self.document["image"])
        if inspect_runtime(self.image)["source"] != self.release["source"]:
            raise ValueError("Candidate image differs from frozen source; rebuild it")
        image_lock = self.folder / "image.lock.json"
        if image_lock.exists() and read(image_lock) != self.image:
            raise ValueError("Candidate image tag moved; use a new candidate")
        if not image_lock.exists():
            save(image_lock, self.image)
        self.rows = [r for r in self.document["instances"] if not args.families or r["family"] in args.families]
        self.status_path = self.folder / "pipeline_status.json"
        self.state = read(self.status_path) if self.status_path.exists() else dict(release=self.release, instances={}, harbor_qualified=False)

    def ready(self):
        gpu_ready(self.args.gpu)

    def wait_for_experiments(self):
        """User-selected prerequisites; observe them, never stop or remove them."""
        deadline = time.monotonic() + self.args.wait_timeout_s
        while self.args.after_containers:
            running = []
            for name in self.args.after_containers:
                result = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", name],
                                        capture_output=True, text=True, timeout=20)
                if result.returncode and "No such" not in result.stderr:
                    raise ValueError("Cannot inspect prerequisite experiment: " + name)
                if result.stdout.strip() == "true":
                    running.append(name)
            if not running:
                break
            self.state.update(status="waiting_for_existing_experiments", waiting_for=running)
            save(self.status_path, self.state)
            if time.monotonic() >= deadline:
                raise ValueError("Waiting deadline reached; existing experiments were preserved, resume the candidate later")
            print("Waiting for existing experiments: " + ", ".join(running), flush=True)
            time.sleep(30)
        self.state.update(status="running", waiting_for=[])
        save(self.status_path, self.state)

    def slug(self, row):
        return Path(row["source"]).parent.parent.name.removesuffix("-privileged")

    def tasks(self, row):
        return [self.folder / "tasks" / (self.slug(row) + "-" + mode) for mode in ("privileged", "standard")]

    def run(self, command, env, label):
        if inspect_image(self.document["image"])["id"] != self.image["id"]:
            raise ValueError("Candidate image tag moved during execution")
        self.ready()
        output = self.folder / "execution" / f"{label}-{time.time_ns()}"
        output.mkdir(parents=True)
        actual_env = dict(os.environ, **env)
        if "TOPOGYM_GPU_UUID" in actual_env:
            actual_env["TOPOGYM_GPU_UUID"] = self.args.gpu
        command = [str(value) for value in command]
        container_name = None
        if command[:2] == ["docker", "run"]:
            container_name = f"topogym-v{self.release['tooling_version']}-build-" + uuid.uuid4().hex
            command[2:2] = ["--name", container_name]
        if "--gpus" in command:
            command[command.index("--gpus") + 1] = "device=" + self.args.gpu
        print(f"Running {label}; log {output / 'runtime.log'}", flush=True)
        try:
            code = run_guarded(command, output, cwd=ROOT, env=actual_env)
        finally:
            if container_name:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
        if code:
            raise ValueError(f"{label} failed; see {output}")

    def build(self):
        for row in self.rows:
            slug = self.slug(row)
            tasks = self.tasks(row)
            privileged_ready = (tasks[0] / "task_release.json").exists()
            if privileged_ready:
                require_task(tasks[0], self.source, inspect_docker=True)
            # Preserve complete twins; rerun unfinished stages with a new log.
            for command in row["commands"]:
                argv = command["argv"]
                text = " ".join(argv)
                task = tasks[1] if "topogym_mk_limited.py" in text else tasks[0] if "topogym_mk_task.py" in text else None
                if task and (task / "task_release.json").exists():
                    require_task(task, self.source, inspect_docker=True)
                    continue
                if task and task.exists():
                    task.rename(task.with_name(task.name + ".incomplete." + str(time.time_ns())))
                stage = next((name for name in ("export-ipc-state", "make-instance") if name in argv), None)
                if stage and privileged_ready:
                    continue
                if stage:
                    output = Path(argv[argv.index("--out") + 1])
                    receipt = output.parent / (stage + ".receipt.json")
                    if receipt.exists():
                        proof = read(receipt)
                        if proof.get("image_id") != self.image["id"] or proof.get("command") != argv:
                            raise ValueError(f"Intermediate stage belongs to a different recipe: {receipt}")
                        for name, expected in proof["files"].items():
                            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                                raise ValueError(f"Intermediate output changed: {name}")
                        continue
                    if output.exists():
                        output.rename(output.with_name(output.name + ".incomplete." + str(time.time_ns())))
                self.run(argv, command["env"], slug)
                if stage:
                    files = [output] if output.is_file() else [p for p in output.rglob("*") if p.is_file()]
                    if not files:
                        raise ValueError(f"Build produced no output: {output}")
                    save(receipt, dict(image_id=self.image["id"], command=argv,
                        files={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}))
            for task in tasks:
                require_task(task, self.source, inspect_docker=True)
            self.state["instances"].setdefault(slug, {})["built"] = True
            save(self.status_path, self.state)
        paths = [t for row in self.document["instances"] for t in self.tasks(row) if (t / "task_release.json").exists()]
        version = self.release["tooling_version"]
        content = f'[dataset]\nname = "topogym/v{version}"\nversion = "{version}"\n'
        for task in paths:
            content += f'\n[[tasks]]\nname = "topogym/{task.name}"\npath = "{task.name}"\n'
        (self.folder / "tasks/dataset.toml").write_text(content)
        catalog = self.folder / "runtime_catalog"
        if len(paths) == 2 * len(self.document["instances"]) and not (catalog / "runtime_catalog.json").exists():
            if catalog.exists():
                catalog.rename(catalog.with_name(catalog.name + ".incomplete." + str(time.time_ns())))
            bind_tasks(paths, catalog)

    def restore(self):
        for row in self.rows:
            slug = self.slug(row)
            tasks = self.tasks(row)
            for task in tasks:
                require_task(task, self.source, inspect_docker=True)
            if task_lock(tasks[0]) != task_lock(tasks[1]):
                raise ValueError(f"Twins differ: {slug}")
            state = self.state["instances"].setdefault(slug, {})
            expected = digest(task_lock(tasks[0]))
            prior = state.get("restore")
            if (prior and read(prior).get("instance_exact") is True
                    and read(prior).get("binding_id") == expected and state.get("binding_sha256") == expected):
                continue
            self.ready()
            output = self.folder / "preflight" / f"{slug}-{time.time_ns()}"
            preflight(tasks[0], tasks[0] / "tests/runtime_binding.json", output, gpu=self.args.gpu, execute=True)
            state.update(restore=str(output / "startup.json"), binding_sha256=expected)
            save(self.status_path, self.state)

    def harbor(self):
        from check_topogym_trial import check
        for row in self.rows:
            slug = self.slug(row)
            state = self.state["instances"].setdefault(slug, {})
            if not state.get("restore") or read(state["restore"]).get("instance_exact") is not True:
                raise ValueError(f"Exact restore required before Harbor: {slug}")
            for task in self.tasks(row):
                require_task(task, self.source, inspect_docker=True)
                binding_hash = digest(task_lock(task))
                previous = state.get(task.name)
                if previous and previous.get("binding_sha256") == binding_hash:
                    check(previous["job"], 0, task)
                    continue
                name = task.name + "-nop-" + str(time.time_ns())
                jobs = self.folder / "harbor/jobs"
                self.run([self.args.harbor, "run", "-p", task, "-a", "nop", "-n", "1", "-k", "1",
                          "--max-retries", "0", "-o", jobs, "--job-name", name], {}, name)
                check(jobs / name, 0, task)
                state[task.name] = dict(job=str(jobs / name), binding_sha256=binding_hash)
                save(self.status_path, self.state)

    def activate(self):
        from check_topogym_trial import check
        if identity(ROOT) != self.release:
            raise ValueError("Active definition changed during validation; candidate was preserved, not activated")
        if len(self.document["instances"]) != 39:
            raise ValueError("Activation requires all 39 instances / 78 task packages")
        for row in self.document["instances"]:
            slug = self.slug(row); state = self.state["instances"].get(slug, {})
            for task in self.tasks(row):
                require_task(task, self.source, inspect_docker=True)
                if state.get("binding_sha256") != digest(task_lock(task)):
                    raise ValueError(f"Restore proof missing/stale: {slug}")
                proof = read(state["restore"])
                if proof.get("instance_exact") is not True or proof.get("binding_id") != state["binding_sha256"]:
                    raise ValueError(f"Restore failed: {slug}")
                smoke = state[task.name]
                if smoke.get("binding_sha256") != digest(task_lock(task)):
                    raise ValueError(f"Harbor proof missing/stale: {task.name}")
                check(smoke["job"], 0, task)
        catalog = self.folder / "runtime_catalog/runtime_catalog.json"
        if not catalog.exists():
            raise ValueError("Runtime catalog is missing")
        manifest = ROOT / "ci_checks/topogym_active_release.json"
        data = read(manifest)
        data["active"].update(tasks_root=os.path.relpath(self.folder / "tasks", ROOT),
            runtime_catalog=os.path.relpath(catalog, ROOT), status="environment_qualified",
            definition_sha256=self.release["definition_sha256"])
        save(manifest, data)
        self.state.update(harbor_qualified=True, oracle_qualified=False)
        save(self.status_path, self.state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--phase", choices=("build", "preflight", "harbor-smoke", "activate", "all"), default="all")
    parser.add_argument("--families", nargs="*")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--gpu-wait-s", type=int, default=0,
                        help="deprecated compatibility option; GPU checks no longer wait")
    parser.add_argument("--gpu-min-free-mb", type=int, default=0,
                        help="deprecated compatibility option; free GPU memory no longer gates execution")
    parser.add_argument("--harbor", default=str(ROOT / ".venv-harbor/bin/harbor"))
    parser.add_argument("--after-containers", nargs="*", default=[])
    parser.add_argument("--wait-timeout-s", type=int, default=86400)
    args = parser.parse_args()
    pipeline = None
    try:
        from difficulty_eval import lock
        with lock(args.candidate / ".pipeline.lock", "another process owns this candidate"):
            pipeline = Pipeline(args)
            pipeline.wait_for_experiments()
            for phase in (("build", "preflight", "harbor-smoke", "activate") if args.phase == "all" else (args.phase,)):
                getattr(pipeline, {"preflight": "restore", "harbor-smoke": "harbor"}.get(phase, phase))()
            pipeline.state.update(status="completed", phase=args.phase)
            save(pipeline.status_path, pipeline.state)
        return 0
    except (ValueError, KeyError, OSError, EvaluationError, subprocess.SubprocessError) as error:
        if pipeline is not None:
            pipeline.state.update(status="blocked", error=str(error))
            save(pipeline.status_path, pipeline.state)
        parser.exit(2, f"Candidate blocked: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
