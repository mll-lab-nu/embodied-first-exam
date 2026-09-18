"""Combine completed native-physics probes without promoting partial evidence."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from topogym.tasks.knot_untying.diagnostics import LIMITS


REQUIRED = ("free_baseline", "free_halfdt", "ring_contact", "ring_halfdt", "ring_refined", "robot_prefix")
COMPARISONS = (("free_baseline", "free_halfdt"), ("ring_contact", "ring_halfdt"),
               ("ring_contact", "ring_refined"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def physical_profile(cfg):
    """The recording renderer does not alter the qualified physical profile."""
    data = OmegaConf.to_container(cfg, resolve=True)
    return dict(sim=data["env"]["sim"], task=data["task"], robot=data["robot_control"],
                table=data["env"]["world"]["table"], mount=data["env"]["robot_mount"])


def paired_material_samples(a, b):
    with np.load(a/"trajectory.npz") as data:
        ta, ca = data["times"], data["centerlines"]
    with np.load(b/"trajectory.npz") as data:
        tb, cb = data["times"], data["centerlines"]
    # Subdivision changes preserve each original material interval; sample
    # both meshes at the original 81 material vertices before comparing.
    ca = ca[:, np.rint(np.linspace(0, ca.shape[1]-1, 81)).astype(int)]
    cb = cb[:, np.rint(np.linspace(0, cb.shape[1]-1, 81)).astype(int)]
    # Both probes record every 20 ms. Match those actual saved timestamps;
    # interpolating onto a coarser grid can smear the initial contact peak.
    clock, ia, ib = np.intersect1d(np.rint(ta*1e9).astype(np.int64), np.rint(tb*1e9).astype(np.int64),
                                 return_indices=True)
    return clock*1e-9, ca[ia].astype(float), cb[ib].astype(float)


def compare_trajectories(a, b):
    times, aa, bb = paired_material_samples(a, b)
    if not len(times):
        return dict(passed=False, reason="No common observed physical interval")
    distances = np.linalg.norm(aa-bb, axis=2)
    rms = np.sqrt(np.mean(distances**2, axis=1))
    return dict(passed=bool(rms.max() < LIMITS.comparison_rms_m and distances.max() < LIMITS.comparison_max_m),
        maximum_frame_rms_m=float(rms.max()), maximum_point_distance_m=float(distances.max()),
        maximum_rms_time_s=float(times[int(np.argmax(rms))]),
        maximum_point_time_s=float(times[int(np.unravel_index(np.argmax(distances), distances.shape)[0])]),
        sampled_seconds=float(times[-1]), comparison_samples=len(times),
        material_nodes=81, sampling="matching saved native timestamps; no time interpolation",
        source="newly simulated native FEM centerlines")


def summarize(folder):
    folder = Path(folder).resolve()
    mapping = json.loads((folder/"cases.json").read_text()) if (folder/"cases.json").exists() else {}
    roots = {name: (folder/mapping.get(name, name)).resolve() for name in REQUIRED}
    if any(not root.is_relative_to(folder) for root in roots.values()):
        raise ValueError("Case evidence must remain within the suite folder")
    cases, comparisons = {}, {}
    for name in REQUIRED:
        root = roots[name]
        report_path = root/"report.json"
        if not report_path.exists():
            cases[name] = dict(passed=False, status="missing_or_incomplete")
            continue
        report = json.loads(report_path.read_text())
        files = [root/p for p in ("report.json", "validation_spec.json", "config.yaml", "trajectory.npz")]
        expected_mode = "free_settle" if name.startswith("free_") else "reference_prefix" if name == "robot_prefix" else "ring_contact"
        cases[name] = dict(passed=bool(report.get("passed") and report.get("mode") == expected_mode
                                     and all(p.is_file() for p in files)),
            status="passed" if report.get("passed") else "failed", error=report.get("error"),
            files={str(p.relative_to(folder)): digest(p) for p in files if p.is_file()},
            failed_checks=[key for key, passed in report.get("checks", {}).items() if not passed],
            failed_action_checks=[key for key, passed in report.get("actuation", {}).get("checks", {}).items() if not passed])
    for a, b in COMPARISONS:
        name = f"{a}__{b}"
        if all((roots[case]/"trajectory.npz").exists() for case in (a, b)):
            comparison = compare_trajectories(roots[a], roots[b])
            complete = cases[a]["passed"] and cases[b]["passed"]
            comparison.update(numerical_difference_within_limits=comparison["passed"],
                both_runs_completed_and_passed=complete,
                scope="complete trajectories" if complete else "observed common prefix; at least one run is incomplete or failed")
            comparison["passed"] = bool(comparison["passed"] and complete)
            comparisons[name] = comparison
        else:
            comparisons[name] = dict(passed=False, reason="No paired physical trajectories available")
    configuration_checks = {}
    base_path = roots["free_baseline"]/"config.yaml"
    if base_path.is_file():
        baseline = physical_profile(OmegaConf.load(base_path))
        for name, root in roots.items():
            path = root/"config.yaml"
            expected = copy.deepcopy(baseline)
            if "halfdt" in name:
                expected["sim"]["dt"] /= 2
            if name == "ring_refined":
                expected["task"]["geometry"].update(rope_subdivisions=6, radial_segments=16)
                expected["task"]["rope"]["mesh"]["maxvolume"] = 1.e-8
            configuration_checks[name] = bool(path.is_file() and physical_profile(OmegaConf.load(path)) == expected)
    passed = (all(case["passed"] for case in cases.values()) and all(c["passed"] for c in comparisons.values())
              and len(configuration_checks) == len(REQUIRED) and all(configuration_checks.values()))
    result = dict(scope="numerical scene/contact/grasp qualification; no hardware or full elastic-energy validation",
        passed=passed, cases=cases, comparisons=comparisons, full_demo=False,
        configuration_checks=configuration_checks,
        case_directories={name: str(root.relative_to(folder)) for name, root in roots.items()})
    if cases["robot_prefix"]["passed"]:
        cfg = OmegaConf.load(roots["robot_prefix"]/"config.yaml")
        report = json.loads((roots["robot_prefix"]/"report.json").read_text())
        spec = json.loads((roots["robot_prefix"]/"validation_spec.json").read_text())
        result.update(profile=physical_profile(cfg), reference_speed=report["reference_speed"],
            reference_sha256=spec["actuation"]["reference_sha256"],
            source_sha256=spec["source_sha256"])
    return result


def verify_for_execution(path, cfg, reference_speed, reference):
    path = Path(path).resolve()
    saved = json.loads(path.read_text())
    actual = summarize(path.parent)
    if not saved.get("passed") or not actual["passed"] or saved != actual:
        raise ValueError("Qualification is incomplete, failed, or no longer matches its evidence")
    if actual["profile"] != physical_profile(cfg) or actual["reference_speed"] != reference_speed:
        raise ValueError("Execution physics or motion speed differs from the qualified robot prefix")
    if any(digest(Path(reference)/name) != value for name, value in actual["reference_sha256"].items()):
        raise ValueError("Motion reference differs from the qualified robot prefix")
    project = Path(__file__).resolve().parents[3]
    runtime_names = {"geometry.py", "scene.py", "diagnostics.py", "reference_actions.py", "rigid_diagnostics.py",
                     "ipc_compat.py", "robot_probe.py", "control.py", "assets.py", "aloha.py",
                     "genesis_ipc_vertex_constraints.py", "fem_ipc.py", "fem_attachment.py"}
    if any(digest(project/name) != value for name, value in actual["source_sha256"].items()
           if Path(name).name in runtime_names):
        raise ValueError("Physical implementation differs from the qualified robot prefix")
    return dict(path=str(path), sha256=digest(path), passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = summarize(args.folder)
    (args.folder/"qualification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
