"""Compare fixed-terminal load tests without claiming an untested contact path."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .geometry import shape_in_root_frame
from .validation import LIMITS


def assess(folder):
    reports = {n: json.loads((folder/n/"report.json").read_text()) for n in ("baseline", "half_step")}
    data = {n: np.load(folder/n/"states.npz") for n in reports}
    if not np.allclose(data["baseline"]["time"], data["half_step"]["time"], atol=1e-8):
        raise ValueError("Compare measurements at the same physical times")
    local = {n: np.asarray([shape_in_root_frame(p) for p in d["fibers"]]) for n, d in data.items()}
    error = np.linalg.norm(local["baseline"]-local["half_step"], axis=-1)
    world = np.linalg.norm(data["baseline"]["fibers"]-data["half_step"]["fibers"], axis=-1)
    coarse = np.linalg.norm(data["baseline"]["coarse"]-data["half_step"]["coarse"], axis=-1)
    hashes = {n: hashlib.sha256((folder/n/"assets/bundle.xml").read_bytes()).hexdigest() for n in reports}
    specs = {n: dict(r["spec"]) for n, r in reports.items()}
    # Earlier probes used Genesis' explicit API default: float32.
    for spec in specs.values():
        spec.setdefault("precision", "32")
        spec.setdefault("constraint_solver", "Newton")
    dt = {n: s.pop("dt") for n, s in specs.items()}
    checks = dict(baseline_bounds=reports["baseline"]["passed"], half_step_bounds=reports["half_step"]["passed"],
        fixed_terminal_no_pose_writes=all(r["terminal_fixed"] and r["pose_writes"] == 0 for r in reports.values()),
        same_anchored_asset=len(set(hashes.values())) == 1, same_loading=specs["baseline"] == specs["half_step"],
        same_explicit_fixture_layout=bool(specs["baseline"].get("anchor")) and specs["baseline"].get("anchor") == specs["half_step"].get("anchor"),
        same_contact_model=specs["baseline"].get("contact_model", "genesis_default") == specs["half_step"].get("contact_model", "genesis_default"),
        timestep_halved=bool(np.isclose(dt["baseline"], 2*dt["half_step"])),
        final_local_max=float(error[-1].max()) < LIMITS["timestep_max_shape_difference_m"],
        final_local_rms=float(np.sqrt(np.mean(error[-1]**2))) < LIMITS["timestep_rms_shape_difference_m"],
        whole_trace_local_max=float(error.max()) < LIMITS["timestep_max_shape_difference_m"],
        whole_trace_world_max=float(max(world.max(), coarse.max())) < LIMITS["timestep_max_shape_difference_m"])
    result = dict(variant="anchored_terminal_v2", scope="initial_hold_and_gentle_coarse_load_numerical_gate",
        stability_passed=all(checks.values()), checks=checks, thresholds=LIMITS,
        final_local_max_shape_difference_m=float(error[-1].max()),
        final_local_rms_shape_difference_m=float(np.sqrt(np.mean(error[-1]**2))),
        whole_trace_local_max_shape_difference_m=float(error.max()),
        final_world_max_shape_difference_m=float(world[-1].max()),
        free_release_settled=all(r["final_link_speed_m_s"] < .0001 for r in reports.values()),
        runs=reports, asset_sha256=hashes["baseline"], anchor=specs["baseline"].get("anchor"),
        contact_model=specs["baseline"].get("contact_model", "genesis_default"),
        precision=specs["baseline"]["precision"],
        constraint_solver=specs["baseline"]["constraint_solver"],
        ring_fixture=specs["baseline"].get("ring_fixture"),
        full_robot_contact_sequence_qualified=False,
        limits="One seed, fixed terminal, initial hold and gentle coarse loading only. Neutral-gravity cable continues moving after release. Grasp/contact stability and full sequence require separate live checks and timestep replay.")
    (folder/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    result = assess(parser.parse_args().folder)
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))
    if not result["stability_passed"]:
        raise SystemExit(1)
