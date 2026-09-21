"""Prepare once; load the same resolved presets for every agent and repeat."""
import hashlib
import importlib
import json
from pathlib import Path
import random
import re

from topogym.agent_bridge.session import write_json

ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def resolve(reference):
    module, name = reference.split(":", 1)
    return getattr(importlib.import_module(module), name)


def prepare(output, tasks, *, variants=1, seed=0, options=None):
    """tasks maps task IDs to prepare(seed, options) functions.

    A preparer returns factory, kwargs (fully resolved JSON), knowledge, and
    sources (path -> sha256). No generator is called from the rollout worker.
    """
    if type(variants) is not int or variants < 1:
        raise ValueError("variants must be positive")
    if not tasks:
        raise ValueError("At least one task is required")
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    entries = []
    for task, preparer in tasks.items():
        identifier(task)
        rng = random.Random(f"{seed}:{task}")
        for index, scene_seed in enumerate(rng.sample(range(2**31), variants), 1):
            preset = resolve(preparer)(scene_seed, dict(options or {}))
            for key in ("factory", "kwargs", "knowledge", "sources"):
                if key not in preset:
                    raise ValueError(f"Preparer omitted {key}")
            preset.update(task_id=task, variant_id=f"rollout_{index}", scene_seed=scene_seed)
            preset["sha256"] = digest(preset)
            path = root / task / f"rollout_{index}.json"
            path.parent.mkdir(exist_ok=True)
            write_json(path, preset)
            entries.append(dict(task_id=task, variant_id=preset["variant_id"],
                                path=path.relative_to(root).as_posix(), sha256=preset["sha256"]))
    suite = dict(schema="topogym.frozen_suite.v1", seed=seed, variants_per_task=variants,
                 variants=entries)
    suite["sha256"] = digest(suite)
    write_json(root / "suite.json", suite)
    return root / "suite.json"


def load_suite(path):
    path = Path(path).resolve()
    suite = json.loads(path.read_text())
    unsigned = {k: v for k, v in suite.items() if k != "sha256"}
    if suite.get("schema") != "topogym.frozen_suite.v1" or digest(unsigned) != suite.get("sha256"):
        raise ValueError("Suite content hash/schema mismatch")
    seen = set()
    for entry in suite["variants"]:
        key = (identifier(entry["task_id"]), identifier(entry["variant_id"]))
        if key in seen:
            raise ValueError("Duplicate variant")
        seen.add(key)
        target = (path.parent / entry["path"]).resolve()
        if not target.is_relative_to(path.parent):
            raise ValueError("Preset outside suite")
        preset = load_preset(target)
        if (preset["sha256"] != entry["sha256"] or
                (preset["task_id"], preset["variant_id"]) != key):
            raise ValueError("Suite/preset identity mismatch")
    return suite


def load_preset(path):
    preset = json.loads(Path(path).read_text())
    if digest({k: v for k, v in preset.items() if k != "sha256"}) != preset.get("sha256"):
        raise ValueError("Preset content hash mismatch")
    for source, expected in preset["sources"].items():
        if file_hash(source) != expected:
            raise ValueError(f"Scene dependency changed after preparation: {source}")
    return preset


def source_hashes(task_id):
    # Freeze implementation identity as well as resolved parameters. Abort on
    # edits; silently mixing simulator implementations invalidates comparisons.
    # Other tasks may be developed concurrently; they do not define this scene.
    packages = ("agent_rollout", "agent_bridge", "world", "core", "robot", "utils", f"tasks/{task_id}")
    paths = sorted({path for package in packages for path in (ROOT / "topogym" / package).rglob("*.py")})
    paths.append(ROOT / "topogym/tasks/_rigid_geometry.py")
    return {str(path): file_hash(path) for path in paths}


def prepare_counter(seed, options):
    start = random.Random(seed).uniform(-2, 0)
    return dict(factory="topogym.agent_rollout.suite:create_counter", kwargs=dict(start=start),
                knowledge=dict(construction="Three RGB views of a synthetic marker; no physics.", start=start),
                sources={str(Path(__file__).resolve()): file_hash(__file__)})


def create_counter(asset_dir, *, start):
    from topogym.agent_bridge.adapters import CounterTask

    class ThreeViewCounter(CounterTask):
        def describe(self):
            return dict(super().describe(), cameras=["front", "top", "side"])

        def render(self):
            views = super().render()
            return dict(views, side=views["front"])

        def evaluate(self):
            return dict(status="succeeded" if self.x >= 3 else "failed" if self.x < -10 else "running")

    task = ThreeViewCounter()
    task.x = start
    task.simulator_spec = dict(state_fields=["marker"], pose_entities=["marker"],
        coordinate_frame="world", position_units="metres", quaternion_order="wxyz", coverage="synthetic marker only")
    task.get_pose = lambda entity: dict(position=[task.x, 0, 0], quaternion_wxyz=[1, 0, 0, 0], frame="world")
    task.get_state = lambda fields: {name: task.get_pose("marker") for name in fields}
    return task


def prepare_cast_coil(seed, options):
    """Small tabletop layout variations; geometry/IK qualification is separate."""
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from topogym.world.aloha_cameras import configure_aloha_rig

    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base=None):
        cfg = compose(config_name="cast_coil_aloha")
    rng = random.Random(seed)
    cfg.task.center_xy_m = [-.1356786 + rng.uniform(-.015, .015), .05 + rng.uniform(-.015, .015)]
    cfg.task.yaw_deg = 90 + rng.uniform(-5, 5)
    cfg.task.seed = seed
    cfg.task.objective = options.get("objective", "assemble")
    if cfg.task.objective not in ("assemble", "disassemble"):
        raise ValueError("Unknown Cast Coil objective")
    cfg.env.genesis.backend = options.get("backend", "cpu")
    cfg.env.renderer.type = options.get("renderer", "rasterizer")
    cfg.run.include_robot, cfg.run.viewer = True, False
    configure_aloha_rig(cfg, keep=(), resolution=options.get("resolution", [320, 180]), low_pitch_offset_deg=20)
    template = json.loads((ROOT / "assets/tasks/cast_coil/photo_reference_v1/template.json").read_text())
    OmegaConf.update(cfg, "task.template", template, force_add=True)
    resolved = OmegaConf.to_container(cfg, resolve=True)
    # Paths to robot assets are pinned by hashes below; task geometry is inline.
    sources = source_hashes("cast_coil")
    for folder in (ROOT / "assets/robots/aloha",):
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                sources[str(path)] = file_hash(path)
    scene_source = (ROOT / "topogym/tasks/cast_coil/scene.py").read_text()
    return dict(factory="topogym.tasks.cast_coil.agent_adapter:create",
                kwargs=dict(resolved_config=resolved), sources=sources,
                initial_rgb_tolerance=dict(mean_absolute=0.01, max_channel=32, changed_fraction=0.001),
                knowledge=dict(resolved_config=resolved, genesis_scene_source=scene_source,
                    note="Frozen construction knowledge, not a demonstration or solution."),
                qualification=dict(physics_qualified=False,
                    variation="center +/-15 mm, yaw +/-5 degrees; no solvability claim"))
