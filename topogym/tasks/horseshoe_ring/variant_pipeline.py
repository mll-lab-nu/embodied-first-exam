"""Bounded, fail-closed variant qualification; no video or dataset dependency."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from omegaconf import OmegaConf

from .variant_generator import ROOT, VERSION, create_instance, validate_instance, file_hash
from .robot_motion import Kinematics
from .family_routes import ROUTES
from .verify_physical import verify_run, compare_runs

FAMILY_RELEASE = ROOT/"assets/tasks/horseshoe_ring/family_space_v2/route_references.json"


def corridor_frames(frames, report, family):
    """The designed entry corridor ends at its waypoint; final wrist alignment
    adapts to the observed free ring and is not used as the family fingerprint.

    Early v2 trials labeled both segments alike. Recover their exact boundary
    from the saved planner's first-segment frame count, not by hand trimming.
    """
    prefix = "family_"+family
    rows = [f for f in frames if f["stage"] == prefix+"_corridor"]
    if rows:
        return rows
    event = next((e["family_route"] for e in report["events"] if e.get("family_route", {}).get("family_id") == family), None)
    if event is None:
        return []
    return [f for f in frames if f["stage"] == prefix+"_ring_approach"][:event["segments"][0]["frames"]]


def family_gate(points, params):
    """Keep new routes within their reviewed family and apart from other ones."""
    from scipy.spatial.transform import Rotation
    from .family_space import route_distance
    if not FAMILY_RELEASE.exists():
        return dict(passed=False, reason="Three physical family routes have not been released")
    release = json.loads(FAMILY_RELEASE.read_text())
    if release["generator_version"] != VERSION or not release["passed"] or not release["visual_review_passed"]:
        return dict(passed=False, reason="Family release is incomplete")
    canonical = Rotation.from_euler("z", -params["yaw_deg"], degrees=True).apply(
        np.asarray(points)-[0, .05, .2]-np.asarray(params["translation_m"]))/params["scale_ratio"]
    comparisons = {family: route_distance(canonical, np.asarray(route), 50.)
        for family, route in release["routes_m"].items()}
    own = comparisons[params["family_id"]]
    separated = all(m["directed_p95_max_mm"] >= 50. and m["maximum_directed_fraction_above_threshold"] >= .2
        for family, m in comparisons.items() if family != params["family_id"])
    return dict(passed=bool(own["directed_p95_max_mm"] < 50. and separated), comparisons=comparisons,
        reference_sha256=file_hash(FAMILY_RELEASE), scope="Normalized sampled TCP route; camera-independent geometric signature")


def qualify(folder, *, half_step=None, require_family_release=True):
    folder = Path(folder)
    instance = validate_instance(json.loads((folder/"instance.json").read_text()), check_sources=False)
    physical = verify_run(folder)
    cfg = OmegaConf.load(folder/"config.yaml")
    report = json.loads((folder/"result.json").read_text())
    params = instance["parameters"]
    frames = [json.loads(l) for l in (folder/"physical_states.jsonl").read_text().splitlines()]
    route = corridor_frames(frames, report, params["family_id"])
    kin = Kinematics(cfg.robot_control)
    points = []
    for row in route:
        kin.q = np.asarray(row["qpos"])
        points.append(kin.pose("left")[0])
    requested = np.asarray(ROUTES[params["family_id"]]["waypoint_m"])+params["route_offset_m"]
    waypoint_error = float(np.linalg.norm(np.array(points)-requested, axis=1).min()) if points else float("inf")
    checks = dict(physical=physical["passed"],
        instance_identity=report.get("instance_id") == instance["instance_id"] and
            report.get("instance_sha256") == file_hash(folder/"instance.json"),
        same_template=json.loads((folder/"input_template.json").read_text()) == instance["template"],
        same_task_parameters=OmegaConf.to_container(cfg.task.generation.parameters) == params,
        scale=float(cfg.task.scale) == 2*params["scale_ratio"],
        controller=OmegaConf.to_container(cfg.robot_control) == instance["resolved_config"]["robot_control"],
        measured_family_waypoint=waypoint_error < .005,
        declared_route_event=any(e.get("family_route", {}).get("family_id") == params["family_id"] for e in report["events"]),
        generator_sources=all(file_hash(folder/name) == instance["source_sha256"]["topogym/tasks/horseshoe_ring/"+name]
            for name in ("family_routes.py", "variant_generator.py")))
    execution_sources = {name: sha for name, sha in instance["source_sha256"].items()
        if name.startswith("topogym/tasks/horseshoe_ring/") and Path(name).name not in ("variant_generator.py", "family_routes.py", "geometry.py")}
    if execution_sources:
        checks["execution_sources"] = all(file_hash(folder/("execution_source.py" if Path(name).name == "physical_motion.py" else Path(name).name)) == sha
            for name, sha in execution_sources.items())
    route_gate = family_gate(points, params) if points else dict(passed=False, reason="No family route recorded")
    if require_family_release:
        checks["released_family_signature"] = route_gate["passed"]
    half = None
    if half_step is not None:
        half_step = Path(half_step)
        half = dict(comparison=compare_runs(folder, half_step),
            qualification=qualify(half_step, require_family_release=require_family_release))
        checks["half_timestep"] = bool(half["comparison"]["passed"] and half["qualification"]["accepted"]
            and file_hash(folder/"instance.json") == file_hash(half_step/"instance.json")
            and all(file_hash(folder/name) == file_hash(half_step/name) for name in ("family_routes.py", "variant_generator.py")))
    return dict(schema_version=2, instance_id=instance["instance_id"], accepted=bool(all(checks.values())),
        checks={k: bool(v) for k, v in checks.items()}, physical=physical, half_timestep=half,
        measured_waypoint_error_m=waypoint_error if np.isfinite(waypoint_error) else None,
        family_id=params["family_id"], family_signature=route_gate, family_release_required=require_family_release,
        family_signature_scope="designed entry corridor up to its waypoint; final wrist alignment may replan",
        execution_sources_bound_in_request=bool(execution_sources), qualifier_sha256=file_hash(__file__),
        scope="This exact instance only; no continuous parameter-box or pure-friction guarantee",
        result_sha256=file_hash(folder/"result.json"), states_sha256=file_hash(folder/"physical_states.jsonl"))


def execute_instance(instance_file, output, dt):
    """Fresh process per execution isolates Genesis/OMPL state from batch order."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYOPENGL_PLATFORM="egl", LIBGL_ALWAYS_SOFTWARE="1",
        OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    with Path(str(output)+".log").open("x") as log:
        result = subprocess.run([sys.executable, "-m", "topogym.tasks.horseshoe_ring.physical_demo",
            "--instance", str(Path(instance_file).resolve()), "--output", str(Path(output).resolve()),
            "--dt", str(dt)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        saved = Path(output)/"result.json"
        error = json.loads(saved.read_text()).get("failure") if saved.exists() else "initialization failed"
        raise RuntimeError(f"Physical candidate rejected: {error}; see {output}.log")


def generate_validated(output, seed, *, family=None, jitter=True, max_attempts=3, half_step=True):
    """Return accepted instance+evidence, or raise after explicit same-family retries.

    This is the future dataset runner's input boundary. It does not construct a
    dataset or an H5, and does not require MP4 rendering to decide success.
    """
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if not FAMILY_RELEASE.exists() or not json.loads(FAMILY_RELEASE.read_text()).get("visual_review_passed"):
        raise ValueError("Release all three physical/visual family references before generating accepted variants")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    attempts = []
    for attempt in range(max_attempts):
        instance = create_instance(seed, family=family, jitter=jitter, attempt=attempt)
        family = instance["parameters"]["family_id"]
        path = output/f"attempt_{attempt:02d}.json"
        path.write_text(json.dumps(instance, ensure_ascii=False, indent=2))
        baseline, half = output/f"attempt_{attempt:02d}", output/f"attempt_{attempt:02d}_half"
        row = dict(attempt=attempt, instance_id=instance["instance_id"], family_id=family,
            accepted=False, candidate=path.name)
        try:
            execute_instance(path, baseline, .002)
            if half_step:
                execute_instance(path, half, .001)
            proof = qualify(baseline, half_step=half if half_step else None)
            (baseline/"qualification.json").write_text(json.dumps(proof, indent=2))
            if not proof["accepted"]:
                raise RuntimeError("Failed qualification gates: "+str([k for k, v in proof["checks"].items() if not v]))
            row.update(accepted=True, evidence=str((baseline/"qualification.json").relative_to(output)))
        except (ValueError, RuntimeError) as error:
            row["rejection"] = str(error)
        attempts.append(row)
        ledger = dict(seed=seed, family_id=family, accepted=row["accepted"], attempts=attempts,
            dataset_written=False, h5_written=False)
        (output/"attempts.json").write_text(json.dumps(ledger, indent=2))
        if row["accepted"]:
            (output/"accepted_instance.json").write_text(json.dumps(instance, ensure_ascii=False, indent=2))
            return dict(instance=instance, qualification=proof, directory=str(baseline), attempts=attempts)
    raise RuntimeError(f"No qualified {family} instance after {max_attempts} attempts; see {output/'attempts.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--family", choices=tuple(ROUTES))
    parser.add_argument("--anchor", action="store_true")
    parser.add_argument("--single-dt", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = generate_validated(args.output, args.seed, family=args.family, jitter=not args.anchor,
        max_attempts=args.max_attempts, half_step=not args.single_dt)
    print(json.dumps(dict(instance_id=result["instance"]["instance_id"], accepted=True,
        evidence_directory=result["directory"]), indent=2))


if __name__ == "__main__":
    main()
