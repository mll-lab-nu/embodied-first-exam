"""Isolated native contact regression; intentionally overlapping test capsules."""
import argparse
import json
from pathlib import Path

import numpy as np


def main():
    import genesis as gs
    from .scene import as_numpy
    from .contact_precision import install_capsule_contact_fix, CONTACT_MODEL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patched", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    gs.init(backend=gs.cpu, logging_level="warning", performance_mode=True)
    if args.patched:
        install_capsule_contact_fix()
    scene = gs.Scene(show_viewer=False, sim_options=gs.options.SimOptions(dt=.002, substeps=1))
    bodies = []
    cases = [("perpendicular", 90., 0., .002, .0004),
             ("parallel_offset", 0., .006, .002, .0004),
             ("separated", 90., 0., .003, 0.),
             ("oblique", 45., 0., .002, .0004)]
    for fixed in (True, False):
        path = args.output/("fixed.xml" if fixed else "moving.xml")
        joint = "" if fixed else '<freejoint/>'
        path.write_text('<mujoco><worldbody><body name="capsule">'+joint+
            '<geom type="capsule" fromto="-0.004 0 0 0.004 0 0" size="0.0012" density="1100"/>'+
            '</body></worldbody></mujoco>')
    for i, (name, angle, x_shift, z_gap, expected) in enumerate(cases):
        a = scene.add_entity(gs.morphs.MJCF(file=str(args.output/"fixed.xml"),pos=[i*.05,0.,.1]),
                             material=gs.materials.Rigid(gravity_compensation=1.))
        b = scene.add_entity(gs.morphs.MJCF(file=str(args.output/"moving.xml"),pos=[i*.05+x_shift,0.,.1+z_gap],euler=[0.,0.,angle]),
                             material=gs.materials.Rigid(gravity_compensation=1.))
        bodies.append((a,b))
    scene.build()
    scene.step()
    results = []
    for (name, angle, x_shift, z_gap, expected), (a,b) in zip(cases,bodies):
        pen = as_numpy(a.get_contacts(with_entity=b)["penetration"])
        measured = float(pen.max(initial=0.))
        results.append(dict(case=name, expected_penetration_m=expected,
                            detected_penetration_m=measured, passed=abs(measured-expected)<1e-6))
    report = dict(scope="synthetic_native_capsule_contact_regression_not_task_demo",gs_epsilon=gs.EPS,
                  contact_model=CONTACT_MODEL if args.patched else "genesis_default",
                  checks=results, passed=all(r["passed"] for r in results))
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
