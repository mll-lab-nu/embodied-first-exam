"""Experiment config is distinct from frozen instance config and Harbor job config."""
import copy
import ast
import hashlib
import json
from pathlib import Path
import re

from topogym.agents.usage.config import validate_usage
from .endpoints import PROJECT, DEFAULT_TABLE, read_mapping, validate_version

DEFAULTS = PROJECT / "configs/harbor/defaults.yaml"


def name(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}", value) is None:
        raise ValueError(f"Unsafe or empty identifier: {value!r}")
    return value


def load_config(path=None, *, defaults_file=None, overrides=None):
    """Merge deployment, experiment and explicit options before validation."""
    defaults_path = Path(defaults_file or DEFAULTS).resolve()
    deployment, _ = read_mapping(defaults_path)
    allowed = {"schema_version", "experiment_config", "image", "opencode_version",
               "gpus", "gpu_devices", "providers_file"}
    if (set(deployment) - allowed or type(deployment.get("schema_version")) is not int
            or deployment["schema_version"] != 1
            or not isinstance(deployment.get("experiment_config"), str)):
        raise ValueError("Invalid deployment defaults")
    experiment_path = Path(path).resolve() if path is not None else (
        defaults_path.parent / deployment["experiment_config"]).resolve()
    value = {k: v for k, v in deployment.items() if k not in {"schema_version", "experiment_config"}}
    value["providers_file"] = str((defaults_path.parent / deployment["providers_file"]).resolve()
        if "providers_file" in deployment else DEFAULT_TABLE)
    experiment, _ = read_mapping(experiment_path)
    if {"agent", "agent_profile", "agent_urls_file"} & set(experiment):
        raise ValueError("Agent profiles are retired; use model-name and providers.yaml")
    if "providers_file" in experiment:
        raise ValueError("providers_file belongs in deployment defaults, not the experiment")
    value.update(experiment)
    if overrides and "gpus" in overrides and "gpu_devices" not in overrides:
        value.pop("gpu_devices", None)
    value.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return validate(value)


def validate(value):
    value = copy.deepcopy(value)
    if set(value) - {"experiment", "image", "model", "opencode_version", "providers_file",
                     "attempts", "concurrency", "usage", "instances", "timeout_sec", "gpus", "gpu_devices"}:
        raise ValueError("Unknown experiment field")
    if "providers_file" in value and (not isinstance(value["providers_file"], str) or not value["providers_file"]):
        raise ValueError("providers_file must be a path")
    validate_version(value.get("opencode_version"))
    name(value.get("experiment"))
    usage = validate_usage(value.setdefault("usage", {"mode": "observed"}))
    if usage["mode"] != "off":
        value["usage"] = usage
    for key in ("attempts", "concurrency"):
        number = value.setdefault(key, 1)
        if type(number) is not int or number < 1:
            raise ValueError(f"{key} must be a positive integer")
    if type(value.setdefault("gpus", 1)) is not int or value["gpus"] < 0:
        raise ValueError("gpus must be a nonnegative integer")
    devices = value.get("gpu_devices")
    if devices is not None and (not isinstance(devices, list) or len(devices) != value["gpus"]
            or len(set(devices)) != len(devices) or any(not isinstance(d, str) or not d for d in devices)):
        raise ValueError("gpu_devices must contain exactly gpus distinct string IDs")
    timeout = value.setdefault("timeout_sec", 1800)
    if type(timeout) not in {int, float} or not 0 < timeout <= 86400:
        raise ValueError("timeout_sec must be positive and at most one day")
    if not isinstance(value.get("image"), str) or not value["image"].strip():
        raise ValueError("A shared image tag or digest is required")
    if not isinstance(value.get("instances"), list) or not value["instances"]:
        raise ValueError("instances must be a nonempty list")
    names = set()
    for instance in value["instances"]:
        if set(instance) - {"name", "simulator", "mode", "state_fields", "observation_profile", "evaluation", "fixture", "instruction", "catalog", "initial_observation_steps"}:
            raise ValueError("Unknown instance field")
        identity = name(instance["name"])
        if identity in names:
            raise ValueError("Duplicate instance name")
        names.add(identity)
        instruction = instance.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"{identity}: instruction must contain the task goal and requirements")
        profile = instance.get("observation_profile")
        if profile is not None and (not isinstance(profile, dict) or set(profile) - {
                "rgb_camera_ids", "calibration_camera_ids"}):
            raise ValueError(f"{identity}: observation_profile only accepts camera selection; "
                             "put task text in instruction")
        initial_steps = instance.setdefault("initial_observation_steps", 5)
        if type(initial_steps) is not int or not 0 <= initial_steps <= 1000:
            raise ValueError("initial_observation_steps must be an integer in [0, 1000]")
        config = instance["simulator"]
        if not isinstance(config, dict) or "task_id" not in config:
            raise ValueError("Each instance needs simulator.task_id")
        name(config["task_id"])
        # No host imports of Genesis. Full SimulatorConfig validation occurs in the worker.
        if set(config) - {"task_id", "robot_id", "variation_id", "task_parameters", "seed", "compute_backend",
                         "precision", "physics_dt_s", "solver_substeps", "control_decimation", "max_physics_steps",
                         "reset_physics_steps", "enable_rgb", "observation_mode", "control_mode", "enable_privileged",
                         "render_backend"}:
            raise ValueError("Unknown simulator option or owner-only filesystem path")
        seed = config.setdefault("seed", 0)
        if type(seed) is not int or not 0 <= seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        mode = instance.setdefault("mode", "limited")
        if mode not in {"limited", "unlimited"}:
            raise ValueError("mode must be limited or unlimited")
        fields = instance.setdefault("state_fields", [])
        if not isinstance(fields, list) or set(fields) - {"robot", "world", "task"} or len(fields) != len(set(fields)):
            raise ValueError("Invalid privileged fields")
        if mode == "limited" and (fields or config.get("enable_privileged", False)):
            raise ValueError("limited instances cannot enable privileged access")
        if mode == "unlimited" and not config.get("enable_privileged", False):
            raise ValueError("unlimited requires enable_privileged")
        if instance.setdefault("evaluation", "task_success") not in {"task_success", "pipeline_smoke"}:
            raise ValueError("Invalid evaluation")
        if instance.get("fixture") not in {None, "cube_transfer", "cube_pick_place"}:
            raise ValueError("Unknown test fixture")
        if instance.get("fixture") and config["task_id"] != instance["fixture"]:
            raise ValueError("Fixture/task mismatch")
    # Reject nonfinite numbers and YAML-only objects before generating files.
    json.dumps(value, allow_nan=False)
    return value


def resolve_instances(config):
    """Read the existing literal catalog without importing simulator dependencies.

    This is the SAME source catalog, not a runner-maintained task/variation list.
    Preflight compares its SHA with the installed copy inside the shared image.
    """
    source = Path(__file__).resolve().parents[1] / "topogym/config/variation_records.py"
    content = source.read_bytes()
    tree = ast.parse(content)
    records = next(ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == "RECORDS" for n in node.targets))
    digest = hashlib.sha256(content).hexdigest()
    for instance in config["instances"]:
        if instance.get("fixture"):
            continue
        settings = instance["simulator"]
        task, requested = settings["task_id"], settings.get("variation_id", "base")
        record = next((row for row in records if row["task_id"] == task and
            (requested == row["variation_id"] or requested in row["aliases"])), None)
        if record is None or record["status"] != "integrated":
            raise ValueError(f"Unknown or unavailable task/variation: {task}/{requested}")
        settings["variation_id"] = record["variation_id"]
        instance["catalog"] = {k: record[k] for k in ("variation_id", "difficulty", "model_revision", "validation")}
        instance["catalog"]["sha256"] = digest
    return config


def expand(config, *, task=None, difficulties=None, seeds=None):
    """Optional CLI sweep; each seed becomes a task, attempts remain Harbor's job field."""
    if task or difficulties:
        template = copy.deepcopy(config["instances"][0])
        if task and task != template["simulator"]["task_id"]:
            raise ValueError("Select the target task's rollout preset before expanding a sweep")
        templates = []
        for variation in difficulties or [template["simulator"].get("variation_id", "base")]:
            item = copy.deepcopy(template)
            item["simulator"]["variation_id"] = variation
            templates.append(item)
    else:
        templates = config["instances"]
    expanded = []
    for template in templates:
        for seed in seeds if seeds is not None else [template["simulator"].get("seed", 0)]:
            item = copy.deepcopy(template)
            settings = item["simulator"]
            settings["seed"] = seed
            item["name"] = f"{settings['task_id']}-{settings.get('variation_id', 'base')}-seed{seed}"
            expanded.append(item)
    config["instances"] = expanded
    return config
