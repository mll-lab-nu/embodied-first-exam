"""Combine completed native-physics probes without promoting partial evidence."""
import argparse
import ast
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
RUNTIME_NAMES = {"geometry.py", "scene.py", "diagnostics.py", "reference_actions.py", "reference_ik.py", "rigid_diagnostics.py",
    "feedback_actions.py", "feedback_paths.py", "feedback_ik_plan.py", "reference_preflight.py", "ik_plan.py",
    "robot_mesh_guard.py",
    "deformation_damping.py", "runtime_memory.py", "fem_solver.py", "table_contact.py", "physics_probe.py",
    "mesh_resolution.py", "contact_probe.py", "ipc_compat.py", "robot_probe.py", "control.py", "assets.py",
    "aloha.py", "genesis_ipc_vertex_constraints.py", "fem_ipc.py", "fem_attachment.py"}


def runtime_sources(spec):
    return {name: value for name, value in spec.get('source_sha256', {}).items()
            if Path(name).name in RUNTIME_NAMES}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def implementation_equivalence(root, spec, reference_root, reference_spec):
    """Reuse nonrobot evidence only when changes are in unreachable robot code.

    Actual source hashes remain unmodified. Full execution still requires exact
    agreement with its newly qualified robot prefix, including this driver.
    """
    sources, reference = runtime_sources(spec), runtime_sources(reference_spec)
    if not sources or sources.keys() != reference.keys():
        return dict(passed=False, reason="Missing implementation inventory")
    changed = [name for name in sources if sources[name] != reference[name]]
    if not changed:
        return dict(passed=True, method="identical recorded source hashes")
    driver = "topogym/tasks/rope_threading/physics_probe.py"
    if changed != [driver] or spec.get("mode") not in ("free_settle", "ring_contact"):
        return dict(passed=False, reason="Physical implementation changed", changed=changed)

    class NonrobotDriver(ast.NodeTransformer):
        def visit_If(self, node):
            if isinstance(node.test, ast.Name) and node.test.id == "reference_mode":
                # The false branch still executes for these probes.
                return [self.visit(statement) for statement in node.orelse]
            return self.generic_visit(node)

    signatures = []
    for folder, hashes in ((root, sources), (reference_root, reference)):
        path = Path(folder)/"implementation"/driver
        if not path.is_file() or digest(path) != hashes[driver]:
            return dict(passed=False, reason="Archived implementation hash mismatch")
        tree = NonrobotDriver().visit(ast.parse(path.read_text()))
        signatures.append(hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest())
    return dict(passed=signatures[0] == signatures[1],
        method="identical AST outside reference_mode-only branches; mode is nonrobot",
        mode=spec["mode"], recorded_driver_sha256=sources[driver],
        reference_driver_sha256=reference[driver], nonrobot_driver_sha256=signatures)


def physical_profile(cfg):
    """Rendering and a longer final observation do not change physical targets."""
    data = OmegaConf.to_container(cfg, resolve=True)
    # This controls only when observation stops after all targets finish.
    # verify_for_execution separately forbids a shorter qualified observation.
    data['task'].get('validation', {}).pop('final_post_sequence_settle_s', None)
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
    endpoints = []
    for folder in (a, b):
        with np.load(Path(folder)/'trajectory.npz') as data:
            endpoints.append(float(data['times'][-1]))
    return dict(passed=bool(rms.max() < LIMITS.comparison_rms_m and distances.max() < LIMITS.comparison_max_m),
        maximum_frame_rms_m=float(rms.max()), maximum_point_distance_m=float(distances.max()),
        maximum_rms_time_s=float(times[int(np.argmax(rms))]),
        maximum_point_time_s=float(times[int(np.unravel_index(np.argmax(distances), distances.shape)[0])]),
        sampled_seconds=float(times[-1]), comparison_samples=len(times),
        trajectory_end_times_s=endpoints,
        unpaired_tail_seconds=[max(0., end-float(times[-1])) for end in endpoints],
        material_nodes=81, sampling="matching saved native timestamps; no time interpolation",
        source="newly simulated native FEM centerlines")


def identical_input_mesh(a, b):
    """A timestep comparison must not also change its input mesh or state."""
    paths = [Path(folder)/"mesh.npz" for folder in (a, b)]
    if not all(path.is_file() for path in paths):
        return False
    with np.load(paths[0]) as aa, np.load(paths[1]) as bb:
        return set(aa.files) == set(bb.files) and all(
            np.array_equal(aa[name], bb[name]) for name in aa.files)


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
        files = [root/p for p in ("report.json", "validation_spec.json", "config.yaml", "trajectory.npz", "mesh.npz")]
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
            extra_tail = max(comparison.get('unpaired_tail_seconds', [0.])) > 1e-8
            comparison.update(numerical_difference_within_limits=comparison["passed"],
                both_runs_completed_and_passed=complete,
                scope=("complete shared time interval; additional settling tail is not numerically compared"
                       if extra_tail else "complete trajectories") if complete
                      else "observed common prefix; at least one run is incomplete or failed")
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
                from .mesh_resolution import refinement_settings
                finer = refinement_settings(baseline['task']['geometry'], baseline['task']['rope']['mesh'])
                expected["task"]["geometry"].update(rope_subdivisions=finer['rope_subdivisions'],
                                                   radial_segments=finer['radial_segments'])
                expected["task"]["rope"]["mesh"]["maxvolume"] = finer['maxvolume']
            configuration_checks[name] = bool(path.is_file() and physical_profile(OmegaConf.load(path)) == expected)
    protocol_checks = {}
    all_specs = {name: json.loads((root/"validation_spec.json").read_text())
                 for name, root in roots.items() if (root/"validation_spec.json").is_file()}
    specs = {name: spec['actuation'] for name, spec in all_specs.items() if name.startswith('ring_')}
    for name in ("ring_halfdt", "ring_refined"):
        protocol_checks[name] = bool("ring_contact" in specs and name in specs and specs["ring_contact"] == specs[name])
    mesh_checks = {f"{a}__{b}": identical_input_mesh(roots[a], roots[b])
                   for a, b in (COMPARISONS[0], COMPARISONS[1])}
    implementation_evidence = {name: implementation_equivalence(roots[name], all_specs.get(name, {}),
        roots['robot_prefix'], all_specs.get('robot_prefix', {})) for name in REQUIRED}
    implementation_checks = {name: evidence['passed'] for name, evidence in implementation_evidence.items()}
    passed = (all(case["passed"] for case in cases.values()) and all(c["passed"] for c in comparisons.values())
              and all(protocol_checks.values()) and all(mesh_checks.values())
              and all(implementation_checks.values())
              and len(configuration_checks) == len(REQUIRED) and all(configuration_checks.values()))
    result = dict(scope="numerical scene/contact/grasp qualification; no hardware or full elastic-energy validation",
        passed=passed, cases=cases, comparisons=comparisons, full_demo=False,
        configuration_checks=configuration_checks,
        timestep_input_mesh_checks=mesh_checks,
        runtime_implementation_checks=implementation_checks,
        runtime_implementation_evidence=implementation_evidence,
        loading_protocol_checks=protocol_checks,
        operating_limits=baseline["task"].get("validation") if base_path.is_file() else None,
        case_directories={name: str(root.relative_to(folder)) for name, root in roots.items()})
    if result["operating_limits"]:
        result["scope"] = "numerical qualification within the recorded controlled-release limits; not general free-drop validation"
        result["known_limitation"] = "An earlier undamped profile failed the 0.33 m unsupported-drop comparison; this demonstration does not qualify that regime"
    if cases["robot_prefix"]["passed"]:
        cfg = OmegaConf.load(roots["robot_prefix"]/"config.yaml")
        report = json.loads((roots["robot_prefix"]/"report.json").read_text())
        spec = json.loads((roots["robot_prefix"]/"validation_spec.json").read_text())
        result.update(profile=physical_profile(cfg), reference_speed=report["reference_speed"],
            minimum_robot_settling_s=spec['actuation']['minimum_post_release_s'],
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
    settling = float(cfg.task.get('validation', {}).get('final_post_sequence_settle_s', 5.))
    if not np.isfinite(settling) or settling < actual['minimum_robot_settling_s']:
        raise ValueError('Execution shortens the qualified final settling observation')
    if any(digest(Path(reference)/name) != value for name, value in actual["reference_sha256"].items()):
        raise ValueError("Motion reference differs from the qualified robot prefix")
    project = Path(__file__).resolve().parents[3]
    if any(digest(project/name) != value for name, value in runtime_sources(actual).items()):
        raise ValueError("Physical implementation differs from the qualified robot prefix")
    return dict(path=str(path), sha256=digest(path), passed=True,
                minimum_qualified_settling_s=actual['minimum_robot_settling_s'],
                execution_settling_s=settling)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = summarize(args.folder)
    (args.folder/"qualification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
