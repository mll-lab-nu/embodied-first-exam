"""Wang-layout relay recipes supplied with the 2026-10-03 IK source export."""
import json
from pathlib import Path

VARIATIONS = ("easy", "medium", "hard")
ASSIGNMENT = {"A": "right", "B": "left"}
HOLD_STEP_M = .01
REFERENCE_DIR = Path(__file__).with_name("reference_relays")


def reference_samples(variation):
    """Resolve a byte-identical reference backed by complete native goal evidence."""
    import hashlib
    variation = normalize_variation(variation)
    manifest = json.loads((REFERENCE_DIR/"manifest.json").read_text())
    item = manifest["variants"].get(variation)
    if item is None:
        raise ValueError(f"No native-success reference is recorded for {variation}")
    path = REFERENCE_DIR/item["samples"]
    evidence = json.loads((REFERENCE_DIR/item["evidence"]).read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["samples_sha256"] or digest != evidence["samples_sha256"]:
        raise ValueError("Reference samples differ from the executed artifact")
    segments = evidence.get("segments", [])
    if (evidence.get("variant") != variation or evidence.get("seed") != 0
            or evidence.get("status") != "task_success" or evidence.get("task_success") is not True
            or evidence.get("plan_complete") is not True
            or evidence.get("from_default_home") is not True or evidence.get("robot_execution_verified") is not True
            or not segments or segments[0].get("start_state_ref", {}).get("state_id") != 0
            or segments[-1].get("reason") != "env_terminal"
            or not all(row.get("evidence_complete") and row.get("physics_tick_complete")
                       and row.get("control_step_complete")
                       and row.get("uncheckpointed_physics_steps") == 0 for row in segments)):
        raise ValueError("Reference has no complete native goal evidence from home")
    return path


def normalize_variation(value):
    value = value.removeprefix("rope_threading_")
    if value not in VARIATIONS:
        raise ValueError(f"No Wang relay profile for {value!r}")
    return value


def candidate_plans(variation):
    """Relay plans over abstract hands A/B (A = right, B = left by default).

    Verified on medium under the Wang placement (2026-10-01): A grasps the tip
    on the table and pushes R1; B receives beyond R1 and pulls 190 mm; B
    releases, regrasps 200 mm behind the tip and pushes the tip through R2 into
    R3 (no hand fits between R2 and R3); A receives beyond the last ring and
    pulls the overhang towards its own side. Later entries are fallbacks.
    """
    variation = normalize_variation(variation)
    if variation == "hard":
        return json.loads(Path(__file__).with_name("hard_plans.json").read_text())
    ring_count = 2 if variation == "easy" else 3
    A, B = "A", "B"
    def e(k, pusher, station, receiver, pull, poke=.05, rs=.02):
        return dict(ring=k, pusher=pusher, pusher_station_m=station, poke_m=poke, receiver=receiver,
                    receiver_station_m=rs if receiver else station, pull_m=pull,
                    pusher_orientation=None, receiver_orientation=None)
    def solo(k, hand, station, poke, rs=.01):
        return dict(ring=k, pusher=hand, pusher_station_m=station, poke_m=poke, receiver=None,
                    receiver_station_m=rs, pull_m=.12, pusher_orientation=None, receiver_orientation=None)
    if ring_count == 2:
        return [
            ("A10_B_pull19_B20_recvA", [e(0, A, .10, B, .19), e(1, B, .20, A, .12, poke=.06, rs=.01)]),
            ("A10_B_pull19_B20_solo", [e(0, A, .10, B, .19), solo(1, B, .20, .06)]),
            ("A10_B_pull12_B10_recvA", [e(0, A, .10, B, .12), e(1, B, .10, A, .12, poke=.06, rs=.01)]),
        ]
    return [
        # The 24 cm regrasp keeps the sender clear of R3 during receiver
        # acquisition and release; rechecked from the continuous hard relay.
        candidate_plans("hard")[0],
        ("A10_B_pull19_B20_keep_recvA6", [e(0, A, .10, B, .19), e(1, B, .20, None, 0.), e(2, B, .20, A, .12, poke=.06, rs=.01)]),
        ("A10_B_pull19_B20_keep_solo6", [e(0, A, .10, B, .19), e(1, B, .20, None, 0.), solo(2, B, .20, .06)]),
        ("A10_B_pull19_B20_keep_recvA5", [e(0, A, .10, B, .19), e(1, B, .20, None, 0.), e(2, B, .20, A, .12, poke=.05, rs=.0)]),
    ]


def contact_relaxed_profile(variation):
    """Reproducible development candidate; qualification belongs to each run.

    Keeps the native ring count, aperture and signed crossing target. Geometry,
    material and contact changes are explicit task parameters, not live edits.
    """
    variation = normalize_variation(variation)
    task = dict(rope_mesh=dict(spacing=.0055, sides=12), rope_material=dict(E=5e6),
                rope_reference_shape="initial", rope_robot_contact="fingers",
                aperture_contact_allowance_m=.001, aperture_check_profile="round_ring",
                terminal=dict(maximum_speed_m_s=.01))
    task["geometry"] = dict(ring_yaw_deg=dict(R2=53.13010235415598),
                            ring_offsets_m=dict(R2=[-.035, -.05, 0.]))
    if variation != "easy":
        task["geometry"]["ring_offsets_m"]["R3"] = [0., .06, 0.]
        task["geometry"]["ring_mount_sides"] = dict(R3=-1)
    def leg(index, pusher, receiver, pull, poke=.05):
        return dict(ring=index, pusher=pusher, pusher_station_m=.1, poke_m=poke,
                    receiver=receiver, receiver_station_m=.02 if receiver else .1, pull_m=pull,
                    pusher_orientation=None, receiver_orientation=None)
    relay = [leg(0, "A", "B", .12)]
    if variation == "easy":
        relay.append(leg(1, "B", None, 0.))
        name, overhang = "easy_aligned_finish_held", .05
    else:
        relay += [leg(1, "B", "A", .1), leg(2, "B", None, 0.)]
        name, overhang = "three_ring_finish_held", .05
    return dict(name="contact_relaxed_v16", variation=variation, qualification="development",
        simulator_overrides=dict(physics_dt_s=.04, control_decimation=1, solver_substeps=1, reset_physics_steps=0,
            ipc_options=dict(newton_tolerance=.003, linear_system_tolerance=.00003,
                             collision_detection_method="linear_bvh"),
            grasp_assist=dict(model="ipc_soft_band_v1", max_translation_error_m=.025, max_penetration_m=.006,
                targets=[dict(entity="rope", max_strain_ratio=2., strength=1000., require_exposed_patch=False)])),
        task_parameters=task, route=dict(tip_overhang_m=overhang), relay=relay, plans=[[name, relay]],
        ik_args=["--material-tangent", "--material-tangent-delay", ".2", "--material-tangent-min-lead", ".05",
                 "--material-axis-tolerance-deg", "15", "--support-regrasps", "--support-separation", ".2",
                 "--fixture-margin-mm", "0", "--rope-margin-mm", "0", "--inter-arm-mm", "0", "--max-penetration-mm", "3"],
        execution_args=["--no-rgb", "--tooling-ipc", "--physics-dt", ".04", "--control-decimation", "1",
            "--speed", ".12", "--free-speed", ".25", "--grasp-max-strain", "2", "--grasp-strength", "1000",
            "--grasp-follow-error", ".025", "--grasp-max-penetration", ".006", "--feedback-joint-limit", "1.2",
            "--material-feedback", "--ipc-tolerance-scale", "3", "--settle-seconds", "30",
            "--measured-keeper", "--normalize-keeper", "--allow-covered-grasp", "--measured-regrasps"])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export an explicit Rope Threading development profile (no success claim)")
    parser.add_argument("--variation", choices=VARIATIONS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--execute-samples", type=Path,
                        help="Export the profile and execute a matching complete relay with its saved runtime options")
    execution.add_argument("--execute-reference", action="store_true",
                           help="Execute the packaged seed-0 reference for this development profile")
    args = parser.parse_args()
    profile = contact_relaxed_profile(args.variation)
    if args.execute_reference:
        args.execute_samples = reference_samples(args.variation)
    metadata = None
    if args.execute_samples is not None:
        from .relay_artifact import load_plan
        _, metadata = load_plan(args.execute_samples, variant=args.variation)
        if (not metadata.get("complete_relay", True)
                or metadata["identity"].get("task_parameters") != profile["task_parameters"]):
            parser.error("Execution requires a complete artifact certified for this profile's task parameters")
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("profile", profile), ("task_parameters", profile["task_parameters"]),
                        ("route", profile["route"]), ("relay", profile["relay"]), ("plans", profile["plans"])):
        (args.output/(name+".json")).write_text(json.dumps(value, indent=2)+"\n")
    print(args.output.resolve())
    if metadata is not None:
        import subprocess
        import sys
        runner = Path(__file__).resolve().parents[3]/"scripts/oracle_runners/run_rope_threading_relay.py"
        command = [sys.executable, str(runner), "--output", str(args.output.resolve()/"execution"),
                   "--samples", str(args.execute_samples.resolve()), "--variant", args.variation,
                   "--seed", str(metadata["identity"]["seed"]), *profile["execution_args"]]
        (args.output/"execution_request.json").write_text(json.dumps(command, indent=2)+"\n")
        raise SystemExit(subprocess.run(command).returncode)
