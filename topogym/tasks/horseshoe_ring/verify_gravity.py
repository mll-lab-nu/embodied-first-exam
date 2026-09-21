"""Check recorded gravity dynamics against free fall, zero gravity and half dt."""
import argparse
import json
from pathlib import Path

import numpy as np

from .gravity_demo import sha


def verify(folder):
    folder = Path(folder)
    reports, traces = {}, {}
    for name in ("hold", "half_dt", "zero_gravity", "free_fall"):
        source = folder / name
        report = json.loads((source / "result.json").read_text())
        path = source / "physical_states.jsonl"
        if sha(path) != report["physical_states_sha256"]:
            raise ValueError(f"Changed physical states: {name}")
        if not report["complete"] or report["failure"] or report["pose_writes_after_reset"]:
            raise ValueError(f"Not a completed unconstrained-ring check: {name}")
        if report["ring_initial_assistance"] or report["chain_assistance"]:
            raise ValueError("Gravity checks must leave the target and chain rings unassisted")
        frames = [json.loads(line) for line in path.read_text().splitlines()]
        if len(frames) != report["physical_frame_count"]:
            raise ValueError("Missing physical snapshots")
        initial_constraints = frames[0]["active_welds"]
        for frame in frames:
            if frame["active_welds"] != initial_constraints or len(initial_constraints) != 2:
                raise ValueError("The hold check changed its two declared shoe grasps")
            if frame["chain_link_numbers"] is not None and any(abs(v) != 1 for v in frame["chain_link_numbers"]):
                raise ValueError("A chain connection was lost")
        reports[name], traces[name] = report, frames
    a, b, zero, free = [reports[n] for n in ("hold", "half_dt", "zero_gravity", "free_fall")]
    for report in (a, b, free):
        if report["gravity_m_s2"] != [0., 0., -9.81]:
            raise ValueError("Normal gravity was not used")
    if zero["gravity_m_s2"] != [0., 0., 0.]:
        raise ValueError("Invalid negative control")
    if not np.isclose(a["dt"], b["dt"]*2) or a["simulated_seconds"] != b["simulated_seconds"]:
        raise ValueError("Invalid half-timestep comparison")
    zero_drift = max(np.linalg.norm(np.asarray(f["bodies"]["target_ring"]["pos"])-traces["zero_gravity"][0]["bodies"]["target_ring"]["pos"]) for f in traces["zero_gravity"])
    if zero_drift > 1e-6:
        raise ValueError("Ring moved in the no-force, zero-gravity control")
    t = free["simulated_seconds"]
    analytic_drop, analytic_vz = .5*9.81*t*t, -9.81*t
    error = abs(free["ring_downward_displacement_m"]-analytic_drop)
    # Semi-implicit integration has a bounded first-order position offset.
    allowed = 9.81*t*free["dt"]/free["substeps"] + 1e-7
    if free["ring_first_contact"] is not None or error > allowed:
        raise ValueError("Unsupported ring does not match free fall")
    if abs(free["ring_final_velocity_m_s"][2]-analytic_vz) > 1e-5:
        raise ValueError("Wrong free-fall acceleration")
    dz = abs(a["ring_final_height_m"]-b["ring_final_height_m"])
    if dz > .001:
        raise ValueError("Gravity-held position is timestep sensitive by more than 1 mm")
    for name in ("hold", "half_dt"):
        report, frames = reports[name], traces[name]
        if not .04 < report["ring_downward_displacement_m"] < .07:
            raise ValueError("The baseline target did not fall to its chain support")
        if report["maximum_puzzle_penetration_m"] > .001:
            raise ValueError("Excessive contact penetration in gravity hold")
        if np.linalg.norm(report["ring_final_velocity_m_s"]) > .01:
            raise ValueError("The target did not settle")
        if not set(frames[-1]["ring_contact_bodies"]) & {"chain_upper_1", "chain_lower_1"}:
            raise ValueError("No physical chain support at the final ring pose")
    result = dict(passed=True, scope="Gravity and initial chain-supported hold only; not extraction success",
        hold_drop_mm=a["ring_downward_displacement_m"]*1000,
        half_dt_drop_mm=b["ring_downward_displacement_m"]*1000,
        half_dt_final_height_difference_mm=dz*1000, zero_gravity_drift_m=float(zero_drift),
        free_fall_position_error_m=error, free_fall_analytic_drop_m=analytic_drop,
        free_fall_actual_drop_m=free["ring_downward_displacement_m"],
        maximum_hold_penetration_m=max(a["maximum_puzzle_penetration_m"], b["maximum_puzzle_penetration_m"]),
        report_sha256={n: sha(folder/n/"result.json") for n in reports})
    (folder / "validation.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    print(json.dumps(verify(parser.parse_args().folder), indent=2))
