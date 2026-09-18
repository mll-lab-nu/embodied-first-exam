"""Validate, render, archive, or sample the Keyhole family space reproducibly."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from .family_variants import OUTPUT, TITLES, build
from .inverse_variants import save, sha
from .robot_motion import ROOT
from .variant_assets import require_variant


def command(folder, name, module, arguments):
    folder = Path(folder); logs = folder / "pipeline_logs"; logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYOPENGL_PLATFORM="egl")
    print(f"START {folder.name} {name}", flush=True)
    with (logs / (name + ".log")).open("w") as log:
        result = subprocess.run([sys.executable, "-m", "topogym.tasks.cast_keyhole." + module,
                                 *map(str, arguments)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{folder.name} {name}: {(logs / (name+'.log')).read_text()[-1800:]}")
    print(f"PASS {folder.name} {name}", flush=True)


def geometry(folder):
    command(folder, "geometry", "family_variants", ["qualify", "--root", folder.parent,
            "--style", json.loads((folder / "proposal.json").read_text())["appearance_style"], "--instance-id", folder.name])


def physics(folder, half):
    output = folder / ("robot_physics_half" if half else "robot_physics")
    args = ["--motion", folder / "robot_motion.json", "--geometry", folder / "geometry.json",
            "--output", output, "--backend", "cpu"]
    if half:
        args += ["--dt", ".0005"]
    command(folder, "physics_half" if half else "physics", "robot_execution", args)


def audit(folder, half):
    command(folder, "audit_half" if half else "audit", "physical_audit",
            ["--folder", folder / ("robot_physics_half" if half else "robot_physics"),
             "--geometry", folder / "geometry.json"])


def qualify_physics(folder):
    record, certificate = require_variant(folder / "geometry.json", json.loads((folder / "robot_motion.json").read_text()))
    evidence = {}
    for sub in ("robot_physics", "robot_physics_half"):
        p = folder / sub
        physical = json.loads((p / "report.json").read_text())
        check = json.loads((p / "audit.json").read_text())
        if (not physical["passed"] or not check["passed"] or physical["pose_writes_after_reset"]
                or physical["geometry_sha256"] != sha(folder / "geometry.json")
                or physical["motion_sha256"] != sha(folder / "robot_motion.json")):
            raise ValueError("Missing or stale physical execution")
        for name, digest in check["source_sha256"].items():
            if sha(p / name) != digest:
                raise ValueError("Physical audit inputs changed")
        evidence[sub] = dict(dt=physical["dt"], minimum_gap_m=check["minimum_sampled_gap_m"],
            final_separation_m=check["final_separation_lower_bound_m"],
            report_sha256=sha(p / "report.json"), audit_sha256=sha(p / "audit.json"),
            trajectory_sha256=sha(p / "trajectory.json"))
    if abs(evidence["robot_physics_half"]["dt"] * 2 - evidence["robot_physics"]["dt"]) > 1e-12:
        raise ValueError("Two time steps are required")
    proposal = json.loads((folder / "proposal.json").read_text())
    extra = {}
    if record["family"] == "F3":
        from .turnback_archive import verify_maneuver
        extra = {sub: verify_maneuver(folder / sub, proposal) for sub in evidence}
    result = dict(passed=True, status="physics_verified", family=record["family"], instance_id=folder.name,
                  style=record["appearance_style"], appearance_parameters=record["appearance_parameters"],
                  random_seed=proposal["random_seed"], geometry_sha256=sha(folder / "geometry.json"),
                  solution_sha256=sha(folder / "robot_motion.json"), certificate_sha256=sha(folder / "certificate.json"),
                  negative_controls=certificate["negative_controls"], physics=evidence, maneuver_checks=extra,
                  pregrasp_start=True, assisted_weld_grasp=True, held_at_end=True,
                  friction_only_grasp_verified=False, unique_solution_proven=False)
    save(folder / "qualification.json", result)
    return result


def parallel(jobs, workers):
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fn, *args): label for label, fn, args in jobs}
        for future in as_completed(future_map):
            try:
                future.result()
            except Exception as error:
                errors.append(dict(job=future_map[future], error=str(error)))
                print(f"FAIL {future_map[future]}: {error}", flush=True)
    return errors


def validate(folders, workers=6, skip_geometry=False):
    errors = []
    if not skip_geometry:
        errors = parallel([(f.name, geometry, (f,)) for f in folders], workers)
    usable = [f for f in folders if (f / "design_result.json").exists()]
    errors += parallel([(f"{f.name}/{half}", physics, (f, half)) for f in usable for half in (False, True)], workers)
    jobs = []
    for f in usable:
        for half in (False, True):
            p = f / ("robot_physics_half" if half else "robot_physics") / "report.json"
            if p.exists() and json.loads(p.read_text())["passed"]:
                jobs.append((f"{f.name}/{half}", audit, (f, half)))
    errors += parallel(jobs, workers)
    accepted = []
    for f in usable:
        try:
            accepted.append(qualify_physics(f))
        except Exception as error:
            errors.append(dict(job=f.name, error=str(error)))
    save(folders[0].parent / "validation_batch.json", dict(passed=not errors and len(accepted) == len(folders),
         accepted=accepted, errors=errors))
    if errors or len(accepted) != len(folders):
        raise RuntimeError(f"Validation incomplete; {len(accepted)}/{len(folders)} accepted, {len(errors)} errors")


def render(folder):
    qualify_physics(folder)
    command(folder, "select_recording", "physical_recording", ["--folder", folder / "robot_physics",
            "--reference", folder / "robot_motion.json", "--output", folder / "full_demo"])
    command(folder, "render", "aloha_demo", ["--output", folder / "full_demo", "--geometry", folder / "geometry.json"])


def sampled_family_seed(root, family, rng, attempt):
    destination = root / "sampled_ik" / f"{family}_{attempt:03d}"
    if family == "F1":
        theta = dict(factor=float(rng.uniform(1.10, 1.35)))
        module, args = "long_stroke", ["--factor", theta["factor"]]
    elif family == "F2":
        theta = dict(offset_mm=float(rng.uniform(1.5, 3.)))
        module, args = "eccentric_window", ["--offset-mm", theta["offset_mm"]]
    else:
        theta = dict(angle_deg=float(rng.uniform(20., 30.)), forward_y_mm=float(rng.uniform(-20., -16.)), return_y_mm=-9.5)
        module, args = "turnback", ["--angle-deg", theta["angle_deg"], "--forward-y-mm", theta["forward_y_mm"],
                                   "--return-y-mm", theta["return_y_mm"]]
    command(destination, "family_ik", module, ["--output", destination, *args])
    return destination, theta


def sample(root, seed, count, family=None, vary_ik=False, max_attempts=12):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    if (root / "samples.json").exists():
        raise ValueError("Use a new output directory for each sample batch")
    rng = np.random.default_rng(seed); accepted = []; rejected = []
    families = [family] if family else ["F1", "F2", "F3"]
    for attempt in range(max_attempts):
        if len(accepted) == count:
            break
        # Cycle mechanisms so rejection cannot silently remove a difficult family.
        f = families[len(accepted) % len(families)]
        style = f + "_" + str(rng.choice(list("ABC")))
        child_seed = int(rng.integers(0, 2**31))
        instance = f"sample_{seed}_{attempt:03d}_{style}"
        try:
            source, theta = sampled_family_seed(root, f, rng, attempt) if vary_ik else (None, {"frozen_family_seed": True})
            folder = build(style, root, instance, child_seed, source)
            geometry(folder)
            failures = parallel([(str(half), physics, (folder, half)) for half in (False, True)], 2)
            if failures:
                raise RuntimeError(failures)
            failures = parallel([(str(half), audit, (folder, half)) for half in (False, True)], 2)
            if failures:
                raise RuntimeError(failures)
            result = qualify_physics(folder)
            accepted.append(dict(instance_id=instance, family=f, ik_parameters=theta,
                                 qualification_sha256=sha(folder / "qualification.json"), **{"result": result}))
        except Exception as error:
            rejected.append(dict(attempt=attempt, family=f, instance_id=instance, error=str(error)))
        save(root / "samples.json", dict(passed=len(accepted) == count, seed=seed, requested=count,
             vary_ik=vary_ik, accepted=accepted, rejected=rejected, max_attempts=max_attempts))
    if len(accepted) != count:
        raise RuntimeError(f"Only {len(accepted)}/{count} samples passed; see samples.json")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("validate", "render", "archive", "sample"))
    p.add_argument("--root", type=Path, default=OUTPUT); p.add_argument("--instances", nargs="+")
    p.add_argument("--jobs", type=int, default=6); p.add_argument("--skip-geometry", action="store_true")
    p.add_argument("--seed", type=int, default=42); p.add_argument("--count", type=int, default=1)
    p.add_argument("--family", choices=("F1", "F2", "F3")); p.add_argument("--vary-ik", action="store_true")
    p.add_argument("--max-attempts", type=int, default=12)
    a = p.parse_args(); folders = [a.root / n for n in (a.instances or TITLES)]
    if a.command == "validate":
        validate(folders, a.jobs, a.skip_geometry)
    elif a.command == "render":
        for f in folders:
            render(f)
    elif a.command == "archive":
        from .family_variants_archive import archive_one
        for f in folders:
            archive_one(f)
    else:
        if a.root == OUTPUT:
            p.error("sample requires a distinct --root output directory")
        sample(a.root, a.seed, a.count, a.family, a.vary_ik, a.max_attempts)


if __name__ == "__main__":
    main()
