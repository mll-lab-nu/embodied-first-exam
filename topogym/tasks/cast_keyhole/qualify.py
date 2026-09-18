"""Fail-closed qualification of contact benches at two adjacent time steps.

This gate never qualifies an official solution or a robot recording. It checks
the complete probe suite and compares the final *relative* poses after release.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .physics_probe import evidence_fingerprint, specifications


def compare_reports(coarse, fine, current_fingerprint=None):
    current = evidence_fingerprint() if current_fingerprint is None else current_fingerprint
    errors = []
    expected = {c["name"] for c in specifications()}
    for label, report in (("coarse", coarse), ("fine", fine)):
        cases = report.get("cases", [])
        names = [c.get("name") for c in cases]
        if set(names) != expected or len(names) != len(expected):
            errors.append(f"{label}: incomplete or duplicate case set")
        if report.get("fingerprint") != current or report.get("source_changed_during_run") is not False:
            errors.append(f"{label}: stale or changing source")
        if report.get("passed") is not True or not all(c.get("passed") is True for c in cases):
            errors.append(f"{label}: failed contact probe")
        if report.get("pose_writes_after_reset") is not False:
            errors.append(f"{label}: pose writes are not excluded")
        if report.get("simulated_seconds", 0) < 5 or report.get("sat_sample_interval_s", 1) > .005:
            errors.append(f"{label}: insufficient observation")
        for case in cases:
            # Independently reapply the absolute contact/rest limits.
            values = np.array([case.get("max_contact_penetration_m", np.inf),
                case.get("min_sampled_sat_gap_m", -np.inf),
                case.get("tail_linear_speed_m_s", np.inf),
                case.get("tail_angular_speed_rad_s", np.inf)])
            if (not np.isfinite(values).all() or values[0] >= .0005 or values[1] <= -.0005
                    or values[2] >= .01 or values[3] >= .1):
                errors.append(f"{label}/{case.get('name')}: contact or rest limit violated")
    a, b = deepcopy(coarse.get("config", {})), deepcopy(fine.get("config", {}))
    adt, bdt = a.pop("dt", None), b.pop("dt", None)
    if a != b or coarse.get("thresholds") != fine.get("thresholds"):
        errors.append("probe configuration differs beyond dt")
    if not (isinstance(adt, (float, int)) and isinstance(bdt, (float, int))
            and 0 < bdt <= .0005 and np.isclose(adt, 2*bdt, atol=1e-12, rtol=0)):
        errors.append("require positive coarse dt = 2 * fine dt, coarse dt <= 1 ms")
    if coarse.get("genesis_version") != fine.get("genesis_version"):
        errors.append("different simulator versions")
    comparison = []
    fine_by_name = {c["name"]: c for c in fine.get("cases", [])}
    for x in coarse.get("cases", []):
        y = fine_by_name.get(x["name"])
        if y is None:
            continue
        try:
            t = np.asarray(x["final_relative_translation_m"])-np.asarray(y["final_relative_translation_m"])
            q = [np.asarray(c["final_relative_quaternion_xyzw"], dtype=float) for c in (x, y)]
            if t.shape != (3,) or not np.isfinite(t).all() or any(
                    p.shape != (4,) or not np.isfinite(p).all() or abs(np.linalg.norm(p)-1) > 1e-5 for p in q):
                raise ValueError("invalid final pose")
            distance = float(np.linalg.norm(t))
            angle = float((Rotation.from_quat(q[0]).inv()*Rotation.from_quat(q[1])).magnitude())
            passed = distance < .001 and angle < .02
            comparison.append(dict(name=x["name"],translation_difference_m=distance,
                                   rotation_difference_rad=angle,passed=passed))
            if not passed:
                errors.append(f"{x['name']}: time-step final pose sensitivity exceeds 1 mm / 0.02 rad")
        except (KeyError, ValueError, TypeError):
            errors.append(f"{x['name']}: invalid or missing final relative pose")
    return dict(scope="five-second contact bench only",contact_bench_qualified=not errors,
        qualifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        errors=errors,coarse_dt=adt,fine_dt=bdt,
        convergence_limits=dict(translation_m=.001,rotation_rad=.02),comparison=comparison,
        fingerprint=current,official_route_verified=False,robot_grasp_verified=False,
        formal_demo_qualified=False)


def qualify(coarse_path, fine_path, output):
    paths = [Path(coarse_path), Path(fine_path)]
    result = compare_reports(*(json.loads(p.read_text()) for p in paths))
    result["evidence"] = [dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coarse",type=Path,required=True)
    parser.add_argument("--fine",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = qualify(args.coarse,args.fine,args.output)
    print(json.dumps(result,indent=2))
    if not result["contact_bench_qualified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
