"""Compare independently executed whole-bundle policies at two time steps."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .geometry import shape_in_root_frame
from .validation import LIMITS


def comparable_plan(plan):
    # The gate's content hash remains part of the comparison. Its filesystem
    # location and the deliberately changed time step are the only exclusions.
    return {key: value for key, value in plan.items() if key not in ("dt", "stability_gate")}


def difference(a, b):
    world = np.linalg.norm(a-b, axis=-1)
    local = np.linalg.norm(shape_in_root_frame(a)-shape_in_root_frame(b), axis=-1)
    return dict(world_max_m=float(world.max()), local_max_m=float(local.max()),
                local_rms_m=float(np.sqrt(np.mean(local**2))))


def assess(baseline, half_step):
    folders = (baseline, half_step)
    reports = [json.loads((p/"report.json").read_text()) for p in folders]
    plans = [r["plan"] for r in reports]
    configs = [OmegaConf.to_container(OmegaConf.load(p/"config.yaml"), resolve=True) for p in folders]
    for cfg in configs:
        cfg["env"]["sim"]["dt"] = None
    sources = ["ik_search.py", "robot_sequence.py", "scene.py", "contact_precision.py",
               "contact_guard.py", "anchored_verifier.py"]
    # Historical runs predate the explicit fixture/config helper snapshots.
    # Rendering source is separate evidence and may exist only in the filmed run.
    sources += [name for name in ("numerics.py", "snapshot_trial.py", "refined_variant_trial.py", "variant_trial.py", "ring_mount.py", "run_config.py", "geometry.py",
        "anchored_geometry.py", "sequential.py", "validation.py")
        if any((folder/"source"/name).exists() for folder in folders)]
    for name in sources:
        if not all((folder/"source"/name).is_file() for folder in folders):
            raise ValueError(f"Controller source snapshot missing from one run: {name}")
    hashes = [{s: hashlib.sha256((p/"source"/s).read_bytes()).hexdigest() for s in sources} for p in folders]
    match = dict(configuration_except_dt=configs[0] == configs[1], controller_sources=hashes[0] == hashes[1],
        execution_plan_except_dt_and_gate_path=comparable_plan(plans[0]) == comparable_plan(plans[1]),
        cable_asset=reports[0]["assets_sha256"] == reports[1]["assets_sha256"],
        time_step_halved=bool(np.isclose(plans[0]["dt"], 2*plans[1]["dt"])),
        substeps=plans[0]["substeps"] == plans[1]["substeps"],
        policy_parameters=plans[0]["policy_parameters"] == plans[1]["policy_parameters"],
        contact_model=plans[0]["contact_model"] == plans[1]["contact_model"],
        grasp=all(plans[0][k] == plans[1][k] for k in
                  ("grasp_link", "grasp_point_local_m", "grasp_y_angle_deg", "grasp_assist")),
        success_contract=plans[0]["success_contract_revision"] == plans[1]["success_contract_revision"])
    if not all(match.values()):
        raise ValueError(f"Runs do not describe a matched timestep comparison: {match}")
    # NpzFile decompresses an entire array on every indexing operation. Keep
    # the arrays once; the per-frame comparison must not repeatedly unzip them.
    states = []
    for folder in folders:
        with np.load(folder/"trajectory.npz") as archive:
            states.append({key: archive[key] for key in ("time_s", "fibers")})
    phases = [json.loads((p/"phase_metrics.json").read_text()) for p in folders]
    paired = []
    for left, right in zip(*phases):
        if left["phase"] != right["phase"]:
            break
        indices = [int(np.abs(s["time_s"]-row["time_s"]).argmin()) for s, row in zip(states, (left, right))]
        paired.append(dict(phase=left["phase"], times_s=[left["time_s"], right["time_s"]],
            **difference(states[0]["fibers"][indices[0]], states[1]["fibers"][indices[1]])))
    sequence_matches = len(paired) == len(phases[0]) == len(phases[1])
    final = difference(states[0]["fibers"][-1], states[1]["fibers"][-1])
    # Compare at the same absolute simulation times, retaining timing drift.
    # Interpolation is for diagnostics only, never for rendered motion or
    # contact/success decisions. Ignore duplicate saved boundary timestamps.
    unique_t, unique_i = np.unique(states[1]["time_s"], return_index=True)
    other = states[1]["fibers"][unique_i].reshape(len(unique_i), -1)
    indices = np.flatnonzero(states[0]["time_s"] <= min(s["time_s"][-1] for s in states))
    query_t = states[0]["time_s"][indices]
    aligned = np.stack([np.interp(query_t, unique_t, column) for column in other.T], axis=-1)
    aligned = aligned.reshape((-1, *states[0]["fibers"].shape[1:]))
    trace = [difference(states[0]["fibers"][i], b) for i,b in zip(indices, aligned)]
    trace_max = {key: max(row[key] for row in trace) for key in final}
    def within(row):
        return (row["world_max_m"] <= LIMITS["timestep_max_shape_difference_m"]
                and row["local_max_m"] <= LIMITS["timestep_max_shape_difference_m"]
                and row["local_rms_m"] <= LIMITS["timestep_rms_shape_difference_m"])
    checks = dict(both_complete_physical_runs_passed=all(r["full_threading_verified"] for r in reports),
        same_completed_phase_sequence=sequence_matches,
        final_shape_difference_within_limits=within(final),
        phase_end_differences_within_limits=bool(paired) and all(within(row) for row in paired),
        shared_trace_differences_within_limits=within(trace_max))
    return dict(scope="independent full-policy timestep recheck; not material or spatial-discretization validation",
        baseline=str(baseline), half_step=str(half_step), passed=all(checks.values()),
        configuration_checks=match, checks=checks,
        limits_m=dict(max_shape=LIMITS["timestep_max_shape_difference_m"], rms_shape=LIMITS["timestep_rms_shape_difference_m"]),
        paired_phase_ends=paired, final_state_difference=final,
        common_trace_end_s=float(query_t[-1]), common_trace_max_difference=trace_max,
        failures=[r["failure"] for r in reports], source_hashes=hashes[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("half_step", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.baseline, args.half_step)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("paired_phase_ends", "source_hashes")}, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
