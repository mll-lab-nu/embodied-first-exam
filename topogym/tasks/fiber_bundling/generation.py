"""Seeded, replayable fiber instances shared by future runners and demo tools.

This module generates and validates instances, never episodes, videos or HDF5.
The three families remain density classes, not three certified motion strategies.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil

from omegaconf import OmegaConf

from topogym.generation.episode_spec import EpisodeKey, EpisodeSpec, ExecutionProfile, ScenePreset, TaskVariant
from topogym.generation.variant_rng import VARIANT_RNG_VERSION
from .variants import ROOT, RULES, candidate_config, generate_candidate, inspect_candidate, rules, sample_parameters, validate_parameters

INSTANCE_VERSION = "fiber_instance_v1"
INSTRUCTION = "只抓粗电缆护套，使所有细线和至少 30 mm 前端护套从分叉端穿过固定环；不得用夹爪接触细线。"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configuration(cfg):
    """Resolved scene/control configuration; output location is not identity."""
    result = OmegaConf.to_container(cfg, resolve=True)
    result.get("run", {}).pop("output", None)
    return result


def generator_sources():
    paths = [RULES, Path(__file__), Path(__file__).with_name("variants.py"),
             Path(__file__).with_name("geometry.py"), Path(__file__).with_name("anchored_geometry.py"),
             Path(__file__).with_name("ring_mount.py"), ROOT / "topogym/generation/variant_rng.py"]
    paths += [Path(__file__).with_name("run_config.py"), ROOT / "topogym/tasks/_rigid_geometry.py"]
    return {str(p.relative_to(ROOT)): file_sha(p) for p in paths}


class GenerationRejected(ValueError):
    def __init__(self, attempts):
        self.attempts = attempts
        super().__init__(f"No valid instance after {len(attempts)} attempts: {attempts[-1]['reason']}")


def build_episode(seed, *, family_id=None, mode="parameterized", max_attempts=3):
    """Return (resolved cfg, common EpisodeSpec), without writing files.

    fixed: choose one of three predetermined density prototypes, R=13.5 mm.
    parameterized: sample wire count within the family and the independent radius.
    Family selection remains seed % 3, including on retries; v1 draws are kept.
    Geometry success is explicitly separate from IK/physical qualification.
    """
    if mode not in ("fixed", "parameterized"):
        raise ValueError("mode must be fixed or parameterized")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 20:
        raise ValueError("max_attempts must be an integer in [1, 20]")
    # Validate seed/family outside the rejection loop: a malformed request is not
    # a geometric rejection and must not be silently resampled.
    first = sample_parameters(seed, family_id)
    family_id = first["family_id"]
    attempts = []
    for retry in range(1 if mode == "fixed" else max_attempts):
        params = sample_parameters(seed, family_id, retry=retry)
        if mode == "fixed":
            params.update(fiber_count=rules()["families"][family_id]["representative_count"],
                          ring_inner_radius_m=.0135)
        validate_parameters(params)
        cfg = candidate_config(params)
        cfg.run.record_video = False
        cfg.run.viewer = False
        try:
            geometry = inspect_candidate(cfg)
            if not geometry["geometry_checks_passed"]:
                raise ValueError(str({k: v for k, v in geometry["checks"].items() if not v}))
        except ValueError as error:
            attempts.append(dict(attempt=retry, parameters=params, reason=str(error)))
            continue
        break
    else:
        raise GenerationRejected(attempts)
    snapshot = configuration(cfg)
    sources = generator_sources()
    dependencies = {name: version(name) for name in ("numpy", "scipy", "trimesh", "omegaconf")}
    # Seeds selecting the same fixed prototype share geometry/config identity,
    # while EpisodeKey still distinguishes requests. Neither depends on folders.
    config_hash = digest(snapshot)
    identity = digest(dict(instance_version=INSTANCE_VERSION, mode=mode, family_id=family_id,
                           config_sha256=config_hash, source_sha256=sources, dependencies=dependencies))
    key = EpisodeKey(task_id="fiber_bundling", seed=seed,
                     preset_id=str(cfg.env.preset.id),
                     variant_id=f"{INSTANCE_VERSION}_{family_id}_{mode}_{identity[:16]}")
    status = dict(geometry="passed", kinematics="not_run", loading_stability="not_run",
                  full_physics="not_run", timestep_convergence="not_run", dataset_ready=False)
    spec = EpisodeSpec(key=key, preset=ScenePreset(preset_id=key.preset_id,
        description="Fixed terminal, thin copper rod ring support and passive branched cable."),
        variant=TaskVariant(key=key, difficulty="unclassified", instruction=INSTRUCTION,
            parameters=dict(**params, sampling_mode=mode, accepted_attempt=retry,
                            prototype_id=f"{family_id}_axial_outward_shape7",
                            family_semantics="density_only_not_motion_family"),
            notes="Geometry candidate; success of a representative does not qualify a random instance."),
        execution_profile=ExecutionProfile(profile_id="panda_robotiq_contact_assisted_bundle_ik_v1",
            parameters=dict(policy="greedy_hybrid", only_trunk_actuation=True,
                            contact_triggered_grasp_assistance=True, forbidden_fine_contact=True)),
        resolved_config=dict(schema_version=1, instance_version=INSTANCE_VERSION,
            instance_sha256=identity, config_sha256=config_hash, configuration=snapshot,
            source_sha256=sources, dependencies=dependencies, rules=rules(), variant_rng_version=VARIANT_RNG_VERSION,
            units=dict(length="m", angle="degrees_in_configuration"),
            coordinate_frame="Genesis world; working cable geometry uses trunk-local +x axis",
            validation=status, geometry_report=geometry, rejected_attempts=attempts))
    return cfg, spec


def save_instance(folder, seed, *, family_id=None, mode="parameterized", max_attempts=3):
    """Write an independent instance bundle consumable by variant_demo --stage physics."""
    cfg, spec = build_episode(seed, family_id=family_id, mode=mode, max_attempts=max_attempts)
    folder = Path(folder).resolve()
    if folder.is_relative_to(ROOT / "demos"):
        raise ValueError("Instance metadata/assets belong in runs/, not the MP4 delivery tree")
    params = {k: v for k, v in spec.variant.parameters.items()
              if k not in ("sampling_mode", "accepted_attempt", "prototype_id", "family_semantics")}
    generate_candidate(folder, params)
    cfg.run.output = str(folder)
    OmegaConf.save(cfg, folder / "config.yaml", resolve=True)
    for relative in spec.resolved_config["source_sha256"]:
        target = folder / "generator_source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (folder / "episode_spec.json").write_text(json.dumps(asdict(spec), ensure_ascii=False, indent=2) + "\n")
    files = {str(p.relative_to(folder)): file_sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}
    (folder / "instance_manifest.json").write_text(json.dumps(dict(schema_version=1,
        task_id=spec.task_id, episode_id=spec.stable_id(), instance_sha256=spec.resolved_config["instance_sha256"],
        files_sha256=files, validation=spec.resolved_config["validation"]), indent=2) + "\n")
    return spec


def load_instance(folder):
    """Load exact saved config/Spec and verify bytes; never rerun the sampler."""
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "instance_manifest.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("task_id") != "fiber_bundling":
        raise ValueError("Unsupported fiber instance manifest")
    for rel, expected in manifest["files_sha256"].items():
        path = (folder / rel).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or file_sha(path) != expected:
            raise ValueError(f"Instance artifact changed or missing: {rel}")
    data = json.loads((folder / "episode_spec.json").read_text())
    key = EpisodeKey(**data["key"])
    variant = dict(data["variant"])
    if variant.pop("key") != data["key"]:
        raise ValueError("Episode and variant identity disagree")
    spec = EpisodeSpec(key=key, preset=ScenePreset(**data["preset"]), variant=TaskVariant(key=key, **variant),
        execution_profile=ExecutionProfile(**data["execution_profile"]), resolved_config=data["resolved_config"])
    cfg = OmegaConf.load(folder / "config.yaml")
    if configuration(cfg) != spec.resolved_config["configuration"] or digest(configuration(cfg)) != spec.resolved_config["config_sha256"]:
        raise ValueError("Saved configuration differs from the episode snapshot")
    if spec.stable_id() != manifest["episode_id"] or spec.resolved_config["instance_sha256"] != manifest["instance_sha256"]:
        raise ValueError("Instance identity mismatch")
    if spec.resolved_config["validation"] != manifest["validation"]:
        raise ValueError("Validation status mismatch")
    # Update only the destination for a relocated bundle. Scene/control stay exact.
    cfg.run.output = str(folder)
    return cfg, spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", choices=tuple(rules()["families"]))
    parser.add_argument("--mode", choices=("fixed", "parameterized"), default="parameterized")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = save_instance(args.output, args.seed, family_id=args.family, mode=args.mode)
    _, reloaded = load_instance(args.output)
    assert spec == reloaded
    print(json.dumps(dict(episode_id=spec.stable_id(), output=str(args.output.resolve()),
                         validation=spec.resolved_config["validation"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
