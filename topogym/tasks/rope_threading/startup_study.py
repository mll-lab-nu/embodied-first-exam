"""Serial, controlled startup experiments, separate from full qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from .qualification import compare_trajectories


VARIANTS = {
    "baseline": [],
    "soft50": ["--young-modulus", "50000"],
    "soft20": ["--young-modulus", "20000"],
    "gap12": ["--initial-rope-lift", ".0009"],
    "contact02": ["--contact-distance", ".0002"],
    "gap12_soft50": ["--initial-rope-lift", ".0009", "--young-modulus", "50000"],
}
SHORT_CHECKS = ("finite_no_inversion", "nondegenerate", "initial_surface_intersection_free",
                "every_substep_surface_ccd", "table_clearance", "total_length", "local_axial_strain")


def summarize(root):
    plan = json.loads((root/"plan.json").read_text())
    cases = {}
    for name in plan["cases"]:
        p = root/name
        if not (p/"report.json").exists():
            continue
        r = json.loads((p/"report.json").read_text())
        short_ok = all(r.get("checks", {}).get(k, False) for k in SHORT_CHECKS)
        complete = abs(r.get("simulated_seconds", 0.)-plan["seconds"]) < 1e-9
        cases[name] = dict(completed=complete,
            short_checks_passed=bool(short_ok and complete and r.get("error") is None
                                    and r.get("solver", {}).get("convergence_verified", False)),
            full_physics_qualified=False, error=r.get("error"),
            startup=r.get("startup"), extrema=r.get("extrema"), min_J=r.get("min_J"),
            solver=r.get("solver"), failed_checks=[k for k,v in r.get("checks", {}).items() if not v],
            source_sha256={f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in
                ("trajectory.npz", "mesh.npz", "report.json", "config.yaml", "startup_trace.json") if (p/f).exists()})
    comparisons = {}
    for variant in plan["variants"]:
        a, b = root/(variant+"_dt"), root/(variant+"_halfdt")
        if all((p/"trajectory.npz").exists() for p in (a,b)):
            comparisons[variant] = compare_trajectories(a,b)
    meshes = {}
    base = root/"baseline_dt"/"mesh.npz"
    if base.exists():
        with np.load(base) as original:
            for name in cases:
                file = root/name/"mesh.npz"
                if not file.exists():
                    continue
                with np.load(file) as mesh:
                    equal = (np.array_equal(original["elements"],mesh["elements"])
                             and np.array_equal(original["material_rings"],mesh["material_rings"]))
                    expected_shift = .0009 if name.startswith("gap12") else 0.
                    error = (float(np.max(np.abs(mesh["initial_nodes"]-original["initial_nodes"]-[0,0,expected_shift])))
                             if equal else None)
                    meshes[name] = dict(identical_connectivity_and_material_indices=equal,
                        expected_vertical_translation_m=expected_shift, maximum_vertex_residual_m=error)
    result = dict(scope="startup parameter sensitivity; not full physical qualification or a robot demo",
                  full_physics_qualified=False, seconds=plan["seconds"], cases=cases,
                  timestep_comparisons=comparisons, controlled_mesh_checks=meshes)
    (root/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--variants", nargs="+", choices=VARIANTS,
                   default=["baseline", "soft50", "soft20", "gap12", "contact02"])
    p.add_argument("--seconds", type=float, default=.2)
    args = p.parse_args()
    root = args.folder.resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Choose a new study directory; evidence is never overwritten")
    if not np.isfinite(args.seconds) or args.seconds <= 0 or abs(args.seconds/.005-round(args.seconds/.005)) > 1e-9:
        p.error("seconds must be a positive multiple of 0.005")
    root.mkdir(parents=True, exist_ok=True)
    cases = [(variant+suffix, [*VARIANTS[variant], "--dt", str(dt)])
             for variant in args.variants for suffix,dt in (("_dt",.005),("_halfdt",.0025))]
    (root/"plan.json").write_text(json.dumps(dict(variants=args.variants, cases=dict(cases),
        seconds=args.seconds, scope="startup diagnostics; settling gates remain unchanged"),indent=2)+"\n")
    for name, flags in cases:
        if (root/"STOP").exists():
            raise SystemExit("Stopped; incomplete study preserved")
        target = root/name
        target.mkdir()
        cmd = [sys.executable,"-m","topogym.tasks.rope_threading.physics_probe","--output",str(target),
               "--seconds",str(args.seconds),"--sample-interval",".005","--startup-diagnostics",*flags]
        print(json.dumps(dict(case=name,status="starting",command=cmd)),flush=True)
        with (target/"process.log").open("w") as log:
            done = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        (target/"exit.json").write_text(json.dumps(dict(returncode=done.returncode))+"\n")
        result = summarize(root)
        case = result["cases"].get(name, {})
        print(json.dumps(dict(case=name,returncode=done.returncode,
            short_checks_passed=case.get("short_checks_passed"),startup=case.get("startup"))),flush=True)
        # A short probe intentionally fails the unchanged two-second settling
        # gate. Any setup, convergence, collision or strain failure stops work.
        if not case.get("short_checks_passed"):
            raise SystemExit(f"{name}: startup mechanical/runtime failure; inspect before continuing")


if __name__ == "__main__":
    main()
