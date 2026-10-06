#!/usr/bin/env python3
"""Deterministic difficulty sampling and immutable, private run manifests (no physics).

The difficulty_eval module owns preparation and Harbor execution. This module owns the
stable numbered task catalog, seed selection and the source/configuration identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TASK_IDS = (
    "interlocked_claws", "rope_threading", "lock_picking", "hedgehog_in_cage",
    "fiber_bundling", "horseshoe_ring", "knot_untying", "cast_coil", "cast_keyhole",
    "buzz_wire_3d", "blanket_flatten", "slotted_post_ring", "orbits",
)
TASK_MAPPING_VERSION = 1
DIFFICULTIES = ("easy", "medium", "hard")
MODES = ("unlimited", "limited")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.replace(path)


def select_tasks(selector):
    fields = [s.strip() for s in selector.split(",")]
    if fields == ["all"]:
        return list(TASK_IDS)
    if not all(fields) or "all" in fields:
        raise ValueError("--tasks needs all, or nonempty comma-separated IDs/ranges/names")
    chosen = set()
    for field in fields:
        if field in TASK_IDS:
            chosen.add(field)
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", field)
        if not match:
            raise ValueError(f"unknown task selector: {field!r}")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= len(TASK_IDS):
            raise ValueError(f"task range must ascend within 1..13: {field}")
        chosen.update(TASK_IDS[first - 1:last])
    return [task for task in TASK_IDS if task in chosen]


def sample_seeds(task, difficulty, sampling_seed, count):
    from topogym.utils.variant_rng import VariantRng
    tier = DIFFICULTIES.index(difficulty)
    stream = VariantRng(sampling_seed).stream(f"difficulty_eval/{task}/{difficulty}/scene_seed")
    seen = set()
    upper = (2**32 - 1 - tier) // 3
    while len(seen) < count:
        q = int(stream.integers(0, upper + 1))
        if q not in seen:
            seen.add(q)
            yield 3 * q + tier


def sample_instances(settings, source=ROOT):
    sys.path.insert(0, str(source))
    from topogym.config.registry import task_definition, variation_registration
    from topogym.tasks.scene_variation import SCENE_VARIATION_VERSION, draw
    from topogym.utils.io import to_jsonable
    from topogym.utils.variant_rng import VARIANT_RNG_VERSION
    sys.path.insert(0, str(source / "harbor_templates/topogym/common"))
    from rcb_topogym import simulator_config
    from topogym.tasks.release_profile import environment_inputs, PROFILE
    from topogym_versions import identity
    selected_release = identity(source)
    rows = []
    for task in settings["task_ids"]:
        for difficulty in settings.get("difficulties", DIFFICULTIES):
            fixed = settings.get("instance_selection") == "oracle_reference"
            seeds = [settings["reference_seeds"][task][difficulty]] if fixed else sample_seeds(task, difficulty, settings["sampling_seed"], settings["samples_per_difficulty"])
            variation = difficulty if fixed else "seeded"
            for index, seed in enumerate(seeds):
                reg = variation_registration(task, variation, seed)
                cls = task_definition(task, variation, seed)
                draws = {} if fixed else draw(cls, seed)
                params, overrides, _ = environment_inputs(task, difficulty, variation=variation, seed=seed, parameters=draws)
                if task == "blanket_flatten":
                    # The controller plans arbitrary seeds without a physics stack.
                    # Initial state resources are created in prepare_blanket inside
                    # the selected runtime, never chosen from the controller's stack.
                    from topogym.tasks.base import merge_parameters
                    effective = merge_parameters(cls.defaults, params)
                    goal_complete = cls.goal_complete
                else:
                    instance = cls(params, seed=seed)
                    effective, goal_complete = instance.config, instance.goal_complete
                cfg = simulator_config(task, variation_id=variation, seed=seed, task_parameters=params, simulator_overrides=overrides)
                slug = f"topogym-{task.replace('_', '-')}-{difficulty}-{'o' if fixed else 's'}{index:02d}"
                row = dict(task_id=task, task_number=TASK_IDS.index(task) + 1, difficulty=difficulty,
                           sample_id=f"s{index:02d}", slug=slug, variation_id=variation, scene_seed=seed,
                           resolved_variation_id=reg["variation_id"], variant_rng_version=VARIANT_RNG_VERSION,
                           scene_variation_version=SCENE_VARIATION_VERSION, draws=draws, simulator=cfg,
                           task_parameters=params, simulator_overrides=overrides, environment_profile=PROFILE,
                           tooling_version=selected_release["tooling_version"], release_definition_sha256=selected_release["definition_sha256"],
                           effective_task_parameters=to_jsonable(effective),
                           initial_state_pending=task == "blanket_flatten",
                           evaluable_for_task_success=bool(goal_complete))
                row["sample_sha256"] = digest(row)
                rows.append(row)
    return rows


def snapshot_source(output, root=None):
    """Copy current dirty source, not HEAD. Never copy credentials or old run data."""
    from difficulty_release import load_build_info, source_files
    root = Path(root or ROOT)
    files = source_files(root)
    release = load_build_info(root)
    if release and files != release["files"]:
        raise ValueError("release source differs from build-info")
    dest = output / "source"
    if dest.exists():
        raise ValueError("partial source snapshot exists; preserve it and use a new run-id")
    for rel, sha in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
        if file_hash(target) != sha:
            raise ValueError(f"source changed while freezing {rel}; use a new run-id")
    head = None
    if not release and (root / ".git").exists() and shutil.which("git"):
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
        if result.returncode == 0:
            head = result.stdout.strip()
    identity = dict(git_head=head, files=files, sha256=digest(files), snapshot=str(dest))
    if release:
        identity["release_id"] = release["release_id"]
    return identity


def verify_source(output):
    identity = json.loads((output / "source_identity.json").read_text())
    for rel, sha in identity["files"].items():
        if file_hash(output / "source" / rel) != sha:
            raise ValueError(f"frozen source was modified: {rel}")
    if digest(identity["files"]) != identity["sha256"]:
        raise ValueError("source identity hash mismatch")
    return identity


def add_sampling_arguments(parser):
    """Shared CLI names; None means the setting (or frozen run) supplies the value."""
    parser.add_argument("--setting", type=Path, help="default: configs/sweeps/difficulty_eval.yaml")
    parser.add_argument("--tasks", help="default: all 13; IDs, ascending ranges or names")
    parser.add_argument("--difficulties", help="comma-separated subset of easy,medium,hard; default from setting")
    parser.add_argument("--sampling-seed", type=int, help="default: 20260929")
    parser.add_argument("--samples-per-difficulty", type=int, help="default: 1 per easy/medium/hard")
    parser.add_argument("--agent-wall-clock-s", type=int, help="default 21600; maximum 43200 seconds")
    parser.add_argument("--concurrency", type=int, help="currently only 1")
    parser.add_argument("--resume", action="store_true", help="validate and reuse the immutable manifest")


def prepare_manifest(output, *, setting=None, tasks=None, difficulties=None, sampling_seed=None,
                     samples_per_difficulty=None, agent_wall_clock_s=None, concurrency=None, resume=False,
                     source_root=None):
    """Create or validate a run and return its manifest, without starting a simulator."""
    import yaml
    output = Path(output).resolve()
    source_root = Path(source_root or ROOT)
    old = None
    lock = output / "manifest.lock.json"
    if lock.exists():
        if not resume:
            raise ValueError("run already exists; use --resume or a new run-id")
        old = json.loads(lock.read_text())
    setting = setting or (None if old else source_root / "configs/sweeps/difficulty_eval.yaml")
    cfg = yaml.safe_load(Path(setting).read_text()) if setting else dict(old["settings"])
    if not isinstance(cfg, dict):
        raise ValueError("setting must be a mapping")
    allowed = {"schema_version", "task_ids", "difficulties", "modes", "samples_per_difficulty", "sampling_seed", "agent_wall_clock_s", "concurrency", "instance_selection", "reference_seeds", "reference_notes", "native_batch"}
    if set(cfg) - allowed:
        raise ValueError(f"unknown setting keys: {sorted(set(cfg) - allowed)}")
    selector = tasks if tasks is not None else ",".join(cfg["task_ids"])
    cfg["task_ids"] = select_tasks(selector)
    if difficulties is not None:
        cfg["difficulties"] = [value.strip() for value in difficulties.split(',')]
    overrides = dict(sampling_seed=sampling_seed, samples_per_difficulty=samples_per_difficulty,
                     agent_wall_clock_s=agent_wall_clock_s, concurrency=concurrency)
    for key, value in overrides.items():
        if value is not None:
            cfg[key] = value
        if type(cfg.get(key)) is not int:
            raise ValueError(f"{key} must be an integer")
    tiers=cfg.get("difficulties", [])
    if (cfg.get("schema_version") != 1 or not isinstance(tiers,list) or not tiers
            or any(t not in DIFFICULTIES for t in tiers) or len(set(tiers))!=len(tiers)
            or tuple(cfg.get("modes", [])) != MODES):
        raise ValueError("select unique easy/medium/hard difficulties and unlimited/limited modes")
    cfg["difficulties"]=[t for t in DIFFICULTIES if t in tiers]
    if cfg["samples_per_difficulty"] < 1 or cfg["samples_per_difficulty"] > 10000:
        raise ValueError("samples_per_difficulty must be in 1..10000")
    if not 0 <= cfg["sampling_seed"] < 2**32 or not 0 < cfg["agent_wall_clock_s"] <= 43200 or cfg["concurrency"] != 1:
        raise ValueError("seed must be uint32; budget 1..43200; concurrency currently 1")
    if 'native_batch' in cfg:
        batch=cfg['native_batch']
        if (not isinstance(batch,dict) or set(batch)!={'repetitions','agent','model','effort','token_budget'}
                or type(batch['repetitions']) is not int or not 1<=batch['repetitions']<=10000
                or batch['agent']!='codex' or not re.fullmatch(r'openai/[A-Za-z0-9_.-]+',batch['model'])
                or batch['effort'] not in ('none','minimal','low','medium','high','xhigh','max')):
            raise ValueError('invalid native_batch preset')
        # Retain existing sweep preset validation without importing the retired
        # batch runner. This metadata does not launch or configure the runner.
        budget=batch['token_budget']
        if (not isinstance(budget,dict) or set(budget)!={'input_tokens','output_tokens','enforcement'}
                or budget['enforcement']!='post_run_score'
                or any(type(budget[k]) is not int or budget[k]<=0 for k in ('input_tokens','output_tokens'))):
            raise ValueError('token budget needs positive input/output counts and post_run_score enforcement')
    if cfg.get("instance_selection", "sampled") not in ("sampled", "oracle_reference"):
        raise ValueError("unknown instance selection")
    if cfg.get("instance_selection") == "oracle_reference":
        if cfg["samples_per_difficulty"] != 1:
            raise ValueError("oracle_reference fixes one instance per tier; repeat with Harbor K")
        for task in cfg["task_ids"]:
            seeds = cfg.get("reference_seeds", {}).get(task, {})
            if set(seeds) != set(DIFFICULTIES) or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds.values()):
                raise ValueError("missing/invalid oracle reference seed: " + task)
    if old:
        if old["settings"] != cfg or old["manifest_sha256"] != digest({k: v for k, v in old.items() if k != "manifest_sha256"}):
            raise ValueError("immutable manifest differs; use a new run-id")
        if verify_source(output)["sha256"] != old["source_sha256"]:
            raise ValueError("source identity differs from manifest")
        manifest = old
    else:
        output.mkdir(parents=True, exist_ok=True)
        source = snapshot_source(output, source_root)
        rows = sample_instances(cfg, output / "source")
        # Sampling and freezing must refer to the same source bytes.
        for rel, sha in source["files"].items():
            if file_hash(source_root / rel) != sha:
                raise ValueError("source changed during plan; use a new run-id")
        atomic_json(output / "source_identity.json", source)
        from topogym_versions import identity
        selected_release = identity(output / "source")
        manifest = dict(schema_version=1, task_mapping_version=TASK_MAPPING_VERSION, release=selected_release,
                        task_selector=selector, settings=cfg, source_sha256=source["sha256"],
                        instances=rows, instance_count=len(rows), trial_count=2 * len(rows))
        manifest["manifest_sha256"] = digest(manifest)
        atomic_json(lock, manifest)
        (output / "setting.effective.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    # Reconstruct disposable queues from the locked manifest; never trust a stale queue.
    instances, trials = [], []
    for row in manifest["instances"]:
        instances.append("\t".join(str(row[k]) for k in ("task_id", "difficulty", "sample_id", "scene_seed", "slug")))
        for mode in MODES:
            slug = row["slug"] + ("-limited" if mode == "limited" else "")
            job = f"d{row['task_number']:02d}-{row['difficulty']}-{row['sample_id']}-{mode}"
            trials.append("\t".join((row["task_id"], row["difficulty"], row["sample_id"], mode, slug, job)))
    (output / "instance_queue.tsv").write_text("\n".join(instances) + "\n")
    (output / "trial_queue.tsv").write_text("\n".join(trials) + "\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--output", type=Path)
    add_sampling_arguments(parser)
    args = parser.parse_args(argv)
    if args.list_tasks:
        for i, task in enumerate(TASK_IDS, 1):
            print(f"{i:2d}\t{task}")
        return
    if args.output is None:
        parser.error("--output is required")
    options = vars(args).copy()
    del options["list_tasks"]
    manifest = prepare_manifest(**options)
    print(f"{manifest['instance_count']} instances, {manifest['trial_count']} trials; {args.output.resolve() / 'manifest.lock.json'}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(str(error))
