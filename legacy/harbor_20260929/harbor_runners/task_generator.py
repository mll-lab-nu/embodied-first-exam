"""Freeze small Harbor task definitions; never duplicate the simulator project."""
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import tempfile

import toml
import yaml

from . import HARBOR_VERSION
from .config import name, validate, resolve_instances
from .hooks import run_label
from .usage_bridge import require_capabilities, socket_directory, wrap_agent
from .endpoints import resolve_model, freeze_routes


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(config, root, run_id, *, scripted_scenario=None):
    from harbor.models.job.config import JobConfig
    from harbor.models.task.config import TaskConfig
    config = resolve_instances(validate(config))
    root = Path(root).resolve()
    run = root / "runs" / "harbor" / name(run_id)
    budgeted = config["usage"]["mode"] != "off"
    if scripted_scenario is not None:
        if scripted_scenario not in {"normal", "invalid", "cancel", "pick-cube"}:
            raise ValueError("Unknown scripted test scenario")
        if budgeted:
            raise ValueError("Token limits are not enforced for Scripted tests; use usage off")
        config["execution"] = dict(harness="scripted", scenario=scripted_scenario)
        config.pop("model", None)
        agent = dict(import_path="harbor_runners.agents.scripted:ScriptedAgent",
                     kwargs=dict(scenario=scripted_scenario), env={})
    else:
        connection = resolve_model(config.get("model"), version=config["opencode_version"],
                                   path=config.get("providers_file"))
        require_capabilities(connection, config["usage"])
        config["execution"] = dict(harness="opencode")
        config["model_connection"] = connection
        endpoints, binding = freeze_routes(connection)
        agent = wrap_agent(connection, config["usage"], run)
    run.parent.mkdir(parents=True, exist_ok=True)
    if run.exists():
        raise FileExistsError(f"Run already exists and is frozen: {run}")
    staging = Path(tempfile.mkdtemp(prefix=".prepare-", dir=run.parent))
    try:
        task_root = staging / "harbor_tasks"
        task_root.mkdir()
        for instance in config["instances"]:
            task = task_root / instance["name"]
            environment = task / "environment"
            environment.mkdir(parents=True)
            (task / "tests").mkdir()
            write_json(environment / "instance.json", instance)
            write_json(environment / "usage.json", config["usage"])
            template = files("harbor_runners").joinpath("templates/instruction.md").read_text()
            access = ("Observation mode: limited. Measured robot proprioception is available; "
                      "object/world and task truth are not authorized.")
            if instance["mode"] == "unlimited":
                fields = ", ".join(instance["state_fields"]) or "none"
                access = ("Observation mode: unlimited. Measured robot proprioception is available. "
                          f"Additional authorized privileged fields: {fields}.")
            access += " Available cameras and their fields are listed in /rollout/spec.json."
            # Replace task text last so literal placeholder-like task text is preserved.
            (task / "instruction.md").write_text(template.replace("{{OBSERVATION_ACCESS}}", access)
                .replace("{{TASK_INSTRUCTION}}", instance["instruction"]))
            (task / "tests/test.sh").write_text("#!/bin/sh\nset -eu\nexec topogym-rollout-verify\n")
            os.chmod(task / "tests/test.sh", 0o755)
            spec = dict(schema_version="1.4",
                metadata=dict(topogym_instance=instance["name"], evaluation=instance["evaluation"],
                    topogym_gpus=config["gpus"], topogym_gpu_allocation="docker_compose"),
                agent=dict(user="agent", timeout_sec=config["timeout_sec"]),
                verifier=dict(user="root", timeout_sec=120, collect=[dict(
                    command="topogym-rollout-verify", user="root", timeout_sec=60)]),
                # Harbor 0.23.0 Docker rejects generic environment.gpus > 0
                # before starting Compose. Allocate via Compose below instead;
                # keep the real requirement in metadata and resolved config.
                environment=dict(docker_image=config["image"], cpus=4,
                    memory_mb=16384, workdir="/workspace", healthcheck=dict(
                        command="chmod go-w /logs/verifier && runuser -u agent -- topogym-rollout ready --check-initial",
                        timeout_sec=5, interval_sec=2, start_period_sec=300, start_interval_sec=2, retries=10)),
                artifacts=[dict(source="/trial/rollout", destination="topogym-rollout"),
                           dict(source="/trial/worker.log", destination="worker.log")])
            if not instance["simulator"].get("enable_rgb", True):
                spec["environment"]["healthcheck"]["command"] = "chmod go-w /logs/verifier && runuser -u agent -- topogym-rollout ready"
            if budgeted:
                spec["agent"]["network_mode"] = "no-network"
                spec["verifier"]["network_mode"] = "no-network"
            TaskConfig.model_validate(spec)
            (task / "task.toml").write_text(toml.dumps(spec))
            # Absolute bind path: Harbor's compose base lives elsewhere. Only the
            # frozen tiny instance file is mounted, never the source checkout.
            service = dict(command=["/bin/sh", "-c", "exec topogym-rollout-worker > /trial/worker.log 2>&1"],
                labels=[run_label(run)],
                init=True, user="root", working_dir="/workspace", pids_limit=512,
                shm_size="2gb", security_opt=["no-new-privileges:true"],
                volumes=[dict(type="bind", source=str(run / "harbor_tasks" / instance["name"] / "environment/instance.json"),
                    target="/etc/topogym/instance.json", read_only=True)],
                environment={"NVIDIA_DRIVER_CAPABILITIES": "all"})
            service["volumes"].append(dict(type="bind", source=str(run / "harbor_tasks" /
                instance["name"] / "environment/usage.json"), target="/etc/topogym/usage.json", read_only=True))
            if budgeted:
                service["volumes"].append(dict(type="bind", source=str(socket_directory(run)),
                    target="/run/topogym-usage", read_only=True))
                # Raw sockets could bypass transparent TCP egress controls.
                service["cap_drop"] = ["NET_RAW"]
            if config["gpus"]:
                # GPU DeviceRequests alone can expose CUDA libraries under runc
                # without NVIDIA's Vulkan ICD manifests. Nyx also needs the
                # NVIDIA runtime's graphics mounts (capabilities=all above).
                service["runtime"] = "nvidia"
                devices = dict(driver="nvidia", capabilities=["gpu"])
                if config.get("gpu_devices") is not None:
                    devices["device_ids"] = config["gpu_devices"]
                else:
                    devices["count"] = config["gpus"]
                # This is the GPU allocation authority for the Docker backend.
                # Docker must satisfy it or fail; there is no CPU fallback.
                service["deploy"] = {"resources": {"reservations": {"devices": [devices]}}}
            (environment / "docker-compose.yaml").write_text(yaml.safe_dump(
                {"services": {"main": service}, "networks": {"default": {"labels": [run_label(run)]}}}, sort_keys=False))
        job = dict(job_name="job", jobs_dir=str(run / "jobs"),
            n_attempts=config["attempts"], n_concurrent_trials=config["concurrency"],
            retry={"max_retries": 0}, environment={"type": "docker", "delete": False,
                "kwargs": {"keep_containers": True}},
            agents=[agent], datasets=[{"path": str(run / "harbor_tasks")}])
        JobConfig.model_validate(job)
        write_json(staging / "job.json", job)
        write_json(staging / "experiment.resolved.json", config)
        project = Path(__file__).resolve().parents[1]
        write_json(staging / "rollout_sources.resolved.json", {str(p.relative_to(project)): file_hash(p)
            for folder in (project / "topogym/agents/rollout", project / "topogym/simulator/rollout_simulation",
                           project / "topogym/recording") for p in sorted(folder.rglob("*.py"))})
        if budgeted:
            write_json(staging / "agent_urls.resolved.json", endpoints)
            write_json(staging / "usage_binding.resolved.json", binding)
            project = Path(__file__).resolve().parents[1]
            write_json(staging / "usage_sources.resolved.json", {str(p.relative_to(project)): file_hash(p)
                for folder in (project / "topogym/agents/usage", project / "harbor_runners")
                for p in sorted(folder.rglob("*.py"))})
        manifest = dict(schema_version=2, harbor_version=HARBOR_VERSION,
            run_id=run_id, task_count=len(config["instances"]),
            expected_trials=len(config["instances"]) * config["attempts"],
            files={str(p.relative_to(staging)): file_hash(p) for p in sorted(staging.rglob("*")) if p.is_file()})
        write_json(staging / "manifest.json", manifest)
        # Make task definitions read-only. Hash verification also detects edits by
        # the host owner, who can of course change permissions intentionally.
        for path in task_root.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
        staging.rename(run)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return run


def verify_frozen(run):
    run = Path(run)
    manifest = json.loads((run / "manifest.json").read_text())
    for relative, expected in manifest["files"].items():
        path = run / relative
        if path.is_symlink() or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Frozen run input changed: {relative}")
    expected_tasks = {p for p in manifest["files"] if p.startswith("harbor_tasks/")}
    actual_tasks = {str(p.relative_to(run)) for p in (run / "harbor_tasks").rglob("*") if p.is_file()}
    if expected_tasks != actual_tasks:
        raise ValueError("Frozen task set changed")
    return manifest
