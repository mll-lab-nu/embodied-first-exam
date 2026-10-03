#!/usr/bin/env python3
"""Run the feedback Horseshoe oracle from home and independently audit it.

The recipe is data: a simulator configuration and hash-bound planning inputs.
Execution always uses the formal folding/transfer stage factory, ordinary
joint actions, and proof mode (no rewind). No development tools are loaded.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
FACTORY = "topogym.planning.horseshoe_ring.stages:gravity_release_table_pickup_stages"


def prepare_recipe(recipe_path, output, variant, seed):
    from topogym.utils.io import sha256_file, write_json_atomic
    recipe = json.loads(recipe_path.read_text())
    if recipe["variant"] != variant or recipe["seed"] != seed:
        raise ValueError("Recipe variant/seed differs from the requested instance")
    config, selection = recipe["config"], recipe["selection"]
    if (config["task_id"] != "horseshoe_ring" or config["variation_id"] != variant
            or config["control_mode"] != "JOINT_ABS" or config["enable_rgb"]):
        raise ValueError("Expected an explicit no-RGB Horseshoe JOINT_ABS recipe")
    if selection[0]["step"] != "prefix" or set(selection[0]["parameters"]) != {
            "grasps", "reference", "fold", "support", "approach"}:
        raise ValueError("Recipe requires five checked planning inputs; action replay is not supported")
    inputs = output / "recipe_inputs"
    inputs.mkdir()
    for name, item in selection[0]["parameters"].items():
        source = (recipe_path.parent / item["path"]).resolve()
        if sha256_file(source) != item["sha256"]:
            raise ValueError("Changed planning input: " + name)
        target = inputs / (name + ".json")
        target.write_bytes(source.read_bytes())
        item["path"] = str(target)
    for entry in selection:
        entry.pop("parameters_sha256", None)
    write_json_atomic(output / "requested_config.json", config)
    write_json_atomic(output / "requested_selection.json", selection)
    write_json_atomic(output / "recipe.json", recipe)


def worker(args):
    from topogym.config.registry import task_definition
    from topogym.planning.horseshoe_ring.audit import audit_run
    from topogym.utils.io import write_json_atomic
    from scripts.oracle_runners.run_solvability_workflow import worker as execute_workflow
    recipe = json.loads((args.output / "recipe.json").read_text())
    config = recipe["config"]
    task = task_definition("horseshoe_ring", args.variant)(config.get("task_parameters"), seed=args.seed)
    if (task.resource_hashes != recipe["resource_sha256"]
            or task.model_revision != recipe["model_revision"]
            or task.terminal_revision != recipe["terminal_revision"]):
        raise ValueError("Installed model or terminal differs from the recipe")
    result = execute_workflow(SimpleNamespace(output=args.output, seed=args.seed, smoke=False,
        config=args.output / "requested_config.json", stage_factory=FACTORY,
        selection=args.output / "requested_selection.json", mode="proof"))
    if result:
        return result
    audit = audit_run(args.output)
    write_json_atomic(args.output / "independent_audit.json", audit)
    accepted = bool(audit["accepted_proof"] and audit["identity"]["instance_id"] == recipe["instance_id"])
    write_json_atomic(args.output / "oracle_result.json", dict(accepted_proof=accepted,
        native_task_success=audit["native_task_success"], expected_instance_id=recipe["instance_id"],
        actual_instance_id=audit["identity"]["instance_id"], variant=args.variant, seed=args.seed,
        scope=audit["scope"], audit="independent_audit.json"))
    return 0 if accepted else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("easy", "medium", "hard"), required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, help="Explicit data recipe; defaults to the accepted proof index")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker:
        return worker(args)
    if args.recipe is None:
        index = json.loads((ROOT / "solvability_proof/horseshoe_ring/recipes.json").read_text())
        args.recipe = ROOT / index[args.variant]
    args.recipe = args.recipe.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    prepare_recipe(args.recipe, args.output, args.variant, args.seed)
    from scripts.test_policy_cube_transfer import snapshot
    from topogym.utils.process_limits import run_guarded
    source = snapshot(args.output)
    (args.output / "source_manifest.json").rename(args.output / "run_source_manifest.json")
    command = [sys.executable, str(source / "scripts/oracle_runners/run_horseshoe_oracle.py"),
               "--worker", "--variant", args.variant, "--seed", str(args.seed), "--output", str(args.output)]
    (args.output / "invocation.json").write_text(json.dumps(dict(command=command), indent=2)+"\n")
    environment = dict(os.environ, PYTHONPATH=str(source), OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       OPENBLAS_NUM_THREADS="1", QD_NUM_THREADS="1", PYTHONUNBUFFERED="1",
                       TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT / ".external/nyx-assets"))
    code = run_guarded(command, args.output, cwd=source, env=environment)
    print(f"exit={code}; {args.output}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
