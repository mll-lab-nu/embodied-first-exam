#!/usr/bin/env python3
"""Prepare explicit v15 merge inputs and image-backed build commands; no success claims.

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
    params, overrides, changes = environment_inputs(family, tier,
        variation=instance["variation_id"], seed=instance["seed"], parameters=params)
    cfg = tooling.simulator_config(family, variation_id=instance["variation_id"], seed=instance["seed"],
                                  task_parameters=params, simulator_overrides=overrides)
    # Base timing comes from v14 tooling. Missing historical option dictionaries
    # normalize to current empty defaults; old settled IPC paths are rebuilt.
    differences = {k: dict(v14=instance["simulator"].get(k), candidate=v) for k, v in cfg.items()
                   if instance["simulator"].get(k) != v}
    return params, overrides, cfg, changes, differences


def prepare(output, families=(), tiers=("easy", "medium", "hard"), *, image=None, gpu="0"):
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

    for task in sorted((ROOT / "tasks").glob("topogym-*-privileged")):
        meta = tomllib.loads((task / "task.toml").read_text())["metadata"]
        family, tier = meta.get("family"), meta.get("difficulty")
        if meta.get("tooling_version") != "14" or tier not in tiers or (families and family not in families):
            continue
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
        params, overrides, cfg, changes, differences = candidate_inputs(family, tier, inst, baseline / "instance.json")
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
        python = str(ROOT / ".venv-gs121-nyx/bin/python")
        render = [python, str(snapshot / "scripts/topogym_mk_task.py"), family, "--instance", str(folder / "instance.json"),
                  "--tasks-root", str(output / "tasks"), "--build-root", str(output / "build"),
                  "--slug", slug, "--image", image]
        twin = [python, str(snapshot / "scripts/topogym_mk_limited.py"), family, "-", "--tasks-root", str(output / "tasks"),
                "--build-root", str(output / "build"), "--unlimited-task", str(output / "tasks" / task.name)]
        rows.append(dict(family=family, tier=tier, source=str(source),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), changes=changes,
            configuration_differences=differences, commands=[dict(argv=c, env={}) for c in commands]
                + [dict(argv=render, env=env), dict(argv=twin, env=env)],
            physics_qualified=False, harbor_qualified=False))
    if not rows:
        raise ValueError("No v14 three-tier instances selected")
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
    parser.add_argument("--tiers", nargs="+", choices=("easy", "medium", "hard"), default=("easy", "medium", "hard"))
    parser.add_argument("--image")
    parser.add_argument("--gpu", default="0")
    args = parser.parse_args()
    result = prepare(args.output, args.families, args.tiers, image=args.image, gpu=args.gpu)
    print(json.dumps(dict(output=str(args.output.resolve()), instances=len(result["instances"]), status=result["status"])))
