#!/usr/bin/env python3
"""Prepare explicit merge inputs of the active release and image-backed build commands; no success claims.

The published v14 task tree is read-only. Outputs are manager build recipes, not
frozen instances: only make-instance in the candidate image can create those.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common")]
import rcb_topogym as tooling
from cuda_profiles import image_tag, build_args
from topogym_mk_task import TOOLING_VERSION
from topogym.utils.io import to_jsonable


def candidate_inputs(family, tier, instance, instance_path):
    """Keep v14 task overrides, with explicitly selected local development profiles."""
    params = deepcopy(instance["simulator"].get("task_parameters") or {})
    dependency = params.get("initial_state_path")
    if dependency:
        params["initial_state_path"] = str((Path(instance_path).parent / dependency).resolve())
    from topogym.tasks.release_profile import environment_inputs
    if tier in ("very_easy", "easier"):
        # New simple scenes use their own current Task defaults. Original-tier
        # geometry/contact overrides must never leak into these variants. Blanket and rope take the release's
        # environment profile (rope: the original tiers' environment without their ring layout).
        overrides, changes = {}, ["current below-easy Task defaults and current Harbor timing/grasp profile"]
        if family in ("blanket_flatten", "rope_threading"):
            params, overrides, changes = environment_inputs(family, tier,
                variation=instance["variation_id"], seed=instance["seed"], parameters=params)
    else:
        params, overrides, changes = environment_inputs(family, tier,
            variation=instance["variation_id"], seed=instance["seed"], parameters=params)
    cfg = tooling.simulator_config(family, variation_id=instance["variation_id"], seed=instance["seed"],
                                  task_parameters=params, simulator_overrides=overrides)
    # Base timing comes from v14 tooling. Missing historical option dictionaries
    # normalize to current empty defaults; old settled IPC paths are rebuilt.
    differences = {k: dict(v14=instance["simulator"].get(k), candidate=v) for k, v in cfg.items()
                   if instance["simulator"].get(k) != v}
    return params, overrides, cfg, changes, differences


# Goal thresholds that a packaged frozen state's scene identity records (topogym/world/initial_state.py scene_identity
# hashes every task parameter) although they change nothing in the state itself. A release profile that changes only these
# re-keys a copy of the packaged state (arrays byte-identical, an identity_rekey record) instead of preparing a new one,
# which would be another cloth (a GPU preparation run). v16: blanket_flatten's live coverage 0.90 -> 0.95 (the user's
# decision, 2026-10-03; done the same way for the local tooling-v15 instances). Anything else must still match the archive:
# make-instance's restore refuses a differing identity.
GOAL_ONLY_STATE_PARAMETERS = {"blanket_flatten": ("minimum_coverage_ratio",)}


def rekey_goal_parameters(family, tier, instance, instance_path, destination):
    """If the release profile changes goal-only parameters recorded in the instance's packaged frozen state: write a re-keyed
    copy to `destination` and return (a copy of the instance whose task parameters point at it, the record); else None.
    The source archive is only read."""
    params = deepcopy(instance["simulator"].get("task_parameters") or {})
    dependency, allowed = params.get("initial_state_path"), GOAL_ONLY_STATE_PARAMETERS.get(family, ())
    if not dependency or not allowed:
        return None
    from topogym.tasks.release_profile import environment_inputs, PROFILE
    from topogym.utils.io import canonical_hash
    target, _, _ = environment_inputs(family, tier, variation=instance["variation_id"], seed=instance["seed"],
                                      parameters=params)
    source = (Path(instance_path).parent / dependency).resolve()
    manifest = json.loads((source / "manifest.json" if source.is_dir() else source).read_text())
    folder = source if source.is_dir() else source.parent
    metadata = manifest["metadata"]
    recorded = metadata["identity"]["parameters"]
    changed = {k: [recorded[k], target[k]] for k in allowed if k in target and k in recorded and recorded[k] != target[k]}
    if not changed:
        return None
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if metadata["identity_sha256"] != canonical_hash(metadata["identity"]):
        raise ValueError(f"Packaged frozen state's identity hash does not match its identity: {folder}")
    if {p.name for p in folder.iterdir()} != {"manifest.json", "arrays.npz"} or digest(folder / "arrays.npz") != manifest["arrays"]["sha256"]:
        raise ValueError(f"Packaged frozen state is not a plain manifest + arrays archive: {folder}")
    if digest(folder / "manifest.json") != params.get("initial_state_sha256"):
        raise ValueError(f"Packaged frozen state differs from the instance's initial_state_sha256: {folder}")
    identity = deepcopy(metadata["identity"])
    for key, (_, value) in changed.items():
        identity["parameters"][key] = value
    record = dict(by=f"scripts/topogym_merge_candidate.py ({PROFILE})",
                  reason="the release profile changes goal-only parameters; the state, scene and backend are unchanged "
                         "(arrays.npz byte-identical)",
                  changed={f"identity.parameters.{k}": v for k, v in changed.items()},
                  previous_identity_sha256=metadata["identity_sha256"],
                  previous_manifest_sha256=digest(folder / "manifest.json"), arrays_sha256=manifest["arrays"]["sha256"])
    metadata.update(identity=identity, identity_sha256=canonical_hash(identity), identity_rekey=record)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(folder / "arrays.npz", destination / "arrays.npz")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False))
    if digest(destination / "arrays.npz") != manifest["arrays"]["sha256"]:
        raise ValueError("Re-keyed copy changed the state arrays")
    rekeyed = deepcopy(instance)
    rekeyed["simulator"]["task_parameters"] = dict(params, initial_state_path=str(destination / "manifest.json"),
                                                   initial_state_sha256=digest(destination / "manifest.json"))
    return rekeyed, dict(record, manifest_sha256=digest(destination / "manifest.json"), identity_sha256=metadata["identity_sha256"])


def prepare(output, families=(), tiers=("easy", "medium", "hard"), *, image=None, gpu="0",
            blanket_initial_states=None):
    from topogym.planning.harbor_bridge.catalog import TIERS
    if not tiers or set(tiers) - set(TIERS):
        raise ValueError("Select known difficulty tiers")
    blanket_initial_states = dict(blanket_initial_states or {})
    if set(blanket_initial_states) - (set(tiers) & {"very_easy", "easier"}):
        raise ValueError("Blanket initial-state inputs must name selected below-easy tiers")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    image = image or image_tag(ROOT)
    rows = []
    # Image, tooling and private callbacks use one copied source tree while
    # other development sessions continue editing the working checkout.
    snapshot = output / "source_snapshot"
    from difficulty_release import source_files
    for name in source_files(ROOT):
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    hashes = {p.relative_to(snapshot).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(snapshot.rglob("*")) if p.is_file()}
    (output / "source_manifest.json").write_text(json.dumps(hashes, indent=2) + "\n")
    tool = snapshot / "harbor_templates/topogym/common/rcb_topogym.py"
    build_image = ["docker", "build", "-t", image]
    for key, value in build_args(snapshot, "cu128").items():
        build_image += ["--build-arg", f"{key}={value}"]
    build_image += ["-f", str(snapshot / "images/topogym/Dockerfile"), str(snapshot)]
    (output / "build_image.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + shlex.join(build_image) + "\n")

    def container(args):
        return ["docker", "run", "--rm", "--runtime", "nvidia", "--gpus", "device=" + gpu,
                "-e", "NVIDIA_DRIVER_CAPABILITIES=all", "-e", "RCB_SESSION_LOG=",
                "-v", f"{output}:{output}", "-w", "/tmp", image,
                "python", str(tool), *map(str, args)]

    selected = []
    for task in sorted((ROOT / "tasks").glob("topogym-*-privileged")):
        meta = tomllib.loads((task / "task.toml").read_text())["metadata"]
        family, tier = meta.get("family"), meta.get("difficulty")
        if (meta.get("tooling_version") != "14" or tier not in tiers
                or tier in ("very_easy", "easier") or (families and family not in families)):
            continue
        selected.append((task, family, tier))
    from topogym.config.registry import variation_registration
    for family in families or tooling.TASKS:
        for tier in tiers:
            if tier not in ("very_easy", "easier"):
                continue
            variation_registration(family, tier, 0)
            slug = f"topogym-{family.replace('_', '-')}-{tier.replace('_', '-')}-i00"
            task = output / "seed_inputs" / (slug + "-privileged")
            (task / "environment").mkdir(parents=True)
            simulator = {}
            if family == "blanket_flatten" and tier in blanket_initial_states:
                from topogym.world.initial_state import load_numeric_archive, validate_initial_state_qualification
                from topogym.tasks.blanket_flatten.corner_folds import scene_parameters
                manifest = Path(blanket_initial_states[tier]).resolve()
                _, metadata = load_numeric_archive(manifest)
                validate_initial_state_qualification(metadata["qualification"], "scene_layout")
                identity = metadata["identity"]
                if (metadata["backend"]["codec"] != "rigid_pbd_numeric_v2"
                        or identity["task_id"] != family or identity["seed"] != 0
                        or identity["parameters"]["corner_fold_profile"] != scene_parameters(tier)["corner_fold_profile"]):
                    raise ValueError(f"Blanket initial state differs from {tier}/seed 0")
                asset = task / "environment/instance_assets/initial_state"
                asset.mkdir(parents=True)
                for name in ("manifest.json", "arrays.npz"):
                    shutil.copy2(manifest.with_name(name), asset / name)
                simulator["task_parameters"] = dict(initial_state_path="instance_assets/initial_state/manifest.json",
                    initial_state_sha256=hashlib.sha256((asset / "manifest.json").read_bytes()).hexdigest())
            # A build selection, not a frozen instance. make-instance in the
            # pinned image produces the independently bound physical instance.
            (task / "environment/instance.json").write_text(json.dumps(dict(
                variation_id=tier, seed=0, simulator=simulator, qualification="unbuilt selection"), indent=2) + "\n")
            selected.append((task, family, tier))
    for task, family, tier in selected:
        source = task / "environment/instance.json"
        inst = json.loads(source.read_text())
        slug = task.name.removesuffix("-privileged")
        folder = output / "inputs" / slug
        folder.mkdir(parents=True)
        baseline = folder / "baseline"
        baseline.mkdir()
        shutil.copy2(source, baseline / "instance.json")
        if (source.parent / "instance_assets").is_dir():
            shutil.copytree(source.parent / "instance_assets", baseline / "instance_assets")
        rekey = rekey_goal_parameters(family, tier, inst, baseline / "instance.json", folder / "initial_state_rekeyed")
        if rekey:
            inst, rekey = rekey
        params, overrides, cfg, changes, differences = candidate_inputs(family, tier, inst, baseline / "instance.json")
        if rekey:
            changes.append("packaged frozen state re-keyed for goal-only parameters " + ", ".join(rekey["changed"]))
        for name, value in (("task_parameters", params), ("simulator_overrides", overrides), ("expected_config", cfg)):
            (folder / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
        selection = ["--task", family, "--variation", inst["variation_id"], "--scene-seed", str(inst["seed"]),
                     "--task-parameters", str(folder / "task_parameters.json"),
                     "--simulator-overrides", str(folder / "simulator_overrides.json")]
        commands = []
        if family in {"knot_untying", "rope_threading", "orbits", "slotted_post_ring"}:
            commands.append(container(["export-ipc-state", *selection, "--out", folder / "ipc_state"]))
            selection += ["--ipc-settled-state", str(folder / "ipc_state/manifest.json")]
        commands.append(container(["make-instance", *selection, "--gripper-space",
            "width" if family == "knot_untying" else "native", "--out", folder / "instance.json"]))
        # Generators' run_tool executes describe in this same candidate image.
        env = {"TOPOGYM_TOOL_IMAGE": image, "TOPOGYM_RUN_ROOT": str(output),
               "TOPOGYM_RUN_ID": output.name, "TOPOGYM_GPU_UUID": gpu}
        python = sys.executable
        render = [python, str(snapshot / "scripts/topogym_mk_task.py"), family, "--instance", str(folder / "instance.json"),
                  "--tasks-root", str(output / "tasks"), "--build-root", str(output / "build"),
                  "--slug", slug, "--image", image]
        twin = [python, str(snapshot / "scripts/topogym_mk_limited.py"), family, "-", "--tasks-root", str(output / "tasks"),
                "--build-root", str(output / "build"), "--unlimited-task", str(output / "tasks" / task.name)]
        rows.append(dict(family=family, tier=tier, source=str(source),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), changes=changes, frozen_state_rekey=rekey,
            configuration_differences=differences, commands=[dict(argv=c, env={}) for c in commands]
                + [dict(argv=render, env=env), dict(argv=twin, env=env)],
            physics_qualified=False, harbor_qualified=False))
    if not rows:
        raise ValueError("No instances selected")
    manifest = dict(schema_version=1, tooling_version=TOOLING_VERSION, image=image,
        baseline=dict(tooling_version="14", image="ghcr.io/luigivamper/rcb-topogym:0.2.12-cu128"),
        source_snapshot=str(snapshot), source_manifest_sha256=hashlib.sha256((output / "source_manifest.json").read_bytes()).hexdigest(),
        input_hashes={p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted((output / "inputs").rglob("*")) if p.is_file()},
        build_image_command=build_image,
        status="prepared_inputs_only", instances=rows,
        source_policy="Build candidate image from this merged source; no planning code belongs in the image",
        development_only=["oracle material monkeypatches", "historical rigid integrator overrides", "read-only evidence audits"],
        qualification="No inherited success. Fresh instance, describe timing, replay and Harbor qualification required.")
    (output / "candidate.json").write_text(json.dumps(to_jsonable(manifest), indent=2) + "\n")
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", "# Build the candidate image before running these commands."]
    for row in rows:
        for command in row["commands"]:
            prefix = ["env", *(f"{k}={v}" for k, v in command["env"].items())] if command["env"] else []
            lines.append(shlex.join(prefix + command["argv"]))
    (output / "build_commands.sh").write_text("\n".join(lines) + "\n")
    pipeline = [python, str(ROOT / "scripts/topogym_candidate_pipeline.py"), "--candidate", str(output), "--phase", "all", "--gpu", gpu]
    (output / "build_candidates.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + shlex.join(pipeline) + ' "$@"\n')
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--families", nargs="*", choices=tuple(tooling.TASKS))
    parser.add_argument("--tiers", nargs="+", choices=("very_easy", "easier", "easy", "medium", "hard"), default=("easy", "medium", "hard"))
    parser.add_argument("--image")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--blanket-initial-state", action="append", default=[], metavar="TIER=MANIFEST",
                        help="Prepared below-easy Blanket state for the candidate image's GPU/software profile; repeat per tier")
    args = parser.parse_args()
    initial_states = {}
    for value in args.blanket_initial_state:
        tier, separator, path = value.partition("=")
        if not separator or not path or tier in initial_states:
            parser.error("Use one --blanket-initial-state TIER=MANIFEST per tier")
        initial_states[tier] = path
    result = prepare(args.output, args.families, args.tiers, image=args.image, gpu=args.gpu,
                     blanket_initial_states=initial_states)
    print(json.dumps(dict(output=str(args.output.resolve()), instances=len(result["instances"]), status=result["status"])))
