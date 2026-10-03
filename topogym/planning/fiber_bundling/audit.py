"""Re-evaluate a saved, continuous fiber episode without stepping physics."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from topogym.config.registry import task_definition
from topogym.config.scene import load_scene_config
from topogym.robot.description import describe_robot
from topogym.simulator.config import SimulatorConfig
from topogym.utils.grasp import bilateral_contact_rows, relative_error, relative_pose, rotation
from topogym.utils.io import write_json_atomic


def evidence_open(path, mode="rt"):
    path = Path(path)
    return path.open(mode) if path.exists() else gzip.open(path.with_suffix(path.suffix + ".gz"), mode)


def evidence_digest(path):
    digest = hashlib.sha256()
    size = 0
    with evidence_open(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def rows(path):
    with evidence_open(path) as stream:
        for line in stream:
            yield json.loads(line)


def audit_run(run, output):
    """Use the run's frozen Task implementation; the CLI selects its sys.path.

    Coverage is the saved per-substep contact summary plus sampled world poses.
    This does not certify continuous collision detection or unseen seeds.
    """
    run, output = Path(run).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cfg = SimulatorConfig(**json.loads((run / "config.json").read_text()))
    scene = load_scene_config(cfg)
    group = describe_robot(scene.robot_control).groups[0]
    metadata = json.loads((run / "private/static_model.json").read_text())["episode"]
    task = task_definition("fiber_bundling", cfg.variation_id)(cfg.task_parameters, seed=metadata["seed"])
    ledger = json.loads((run / "report.json").read_text())
    failures = []

    def require(ok, reason, tick=None):
        if not ok and len(failures) < 100:
            failures.append(dict(reason=reason, tick=tick))

    manifest = json.loads((run / "run_source_manifest.json").read_text())
    require(all(hashlib.sha256((run / "source_snapshot" / name).read_bytes()).hexdigest() == value
                for name, value in manifest.items()), "source_snapshot_changed")
    require(ledger["status"] == "complete", "unsealed_episode")
    segments = [row["result"] for row in ledger["segments"]]
    require(all(row and row["evidence_complete"] and row["physics_tick_complete"] for row in segments),
            "incomplete_segment_evidence")
    require(all(a["end_state_ref"] == b["start_state_ref"] for a, b in zip(segments, segments[1:])),
            "discontinuous_segments")
    for segment in segments:
        for name, artifact in segment["logs"].items():
            path = run / "segments" / f"segment_{segment['segment_id']}" / (name + ".jsonl")
            digest, size = evidence_digest(path)
            require(digest == artifact["sha256"] and size == artifact["size_bytes"],
                    "segment_evidence_changed_" + str(segment["segment_id"]) + "_" + name)
    require(not any(row.get("kind") == "rewind" for row in rows(run / "private/history_events.jsonl")),
            "rewound_episode")
    target = next(t for t in cfg.grasp_assist.targets if t.entity == "fiber_bundle")
    previous = None
    initial = None
    acquired = set()
    held_started = False
    maximum_bend = maximum_grasp_translation = maximum_grasp_rotation = 0.
    minimum_joint_margin = float("inf")
    checked = 0
    with tempfile.TemporaryDirectory(prefix="fiber-audit-") as folder:
        table = scene.env.world.table
        task.declare(Path(folder), float(table.pos[2] + table.size[2] / 2))
        generated = {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in Path(folder).rglob("*") if p.is_file()}
        expected = json.loads((run / "asset_manifest.json").read_text())
        require(all(generated.get(name) == value for name, value in expected.items()), "asset_identity_changed")
        for row in rows(run / "private/physics_states.jsonl"):
            state, world = row["state"], row["world"]
            tick = state["physics_step"]
            checked += 1
            if initial is None:
                initial = row
                require(tick == 0 and state["branch_id"] == 0, "not_episode_birth", tick)
                require(np.allclose(row["robot"]["arm"]["joint_position_rad"], group.home[:7], atol=1e-6, rtol=0),
                        "not_robot_home", tick)
                names = {f"{entity}/{name}": index for entity, articulation in world["articulations"].items()
                         for name, index in zip(articulation["links"], world["bodies"][entity]["link_indices"])}
                fingers = [names[f"robot/{name}"] for name in group.grasp.finger_links]
                task.initialize(world)
            else:
                require(state["episode_id"] == initial["state"]["episode_id"] and state["branch_id"] == 0
                        and tick == previous["physics_step"] + 1 and state["parent_state_id"] == previous["state_id"],
                        "discontinuous_tick_history", tick)
                require(not task.result.terminated, "physics_after_task_termination", tick)
                task.update(world, cfg.physics_dt_s)
            previous = state
            require(task.instance_id == row["task"]["instance_id"], "instance_identity_changed", tick)
            for key in ("task_success", "terminated"):
                require(getattr(task.result, key) == row["task"]["result"][key], "task_result_mismatch_" + key, tick)
            require(abs(task.stable_time_s - row["task"]["stable_time_s"]) < 1e-9, "stable_window_mismatch", tick)
            hits, covered = task._contact_evidence(world)
            require(covered and not hits, "gripper_strand_contact_or_missing_coverage", tick)
            maximum_bend = max(maximum_bend, task.result.metrics.get("maximum_bend_deg", 0.))
            q = np.asarray(row["robot"]["arm"]["joint_position_rad"])
            limits = np.asarray(group.arm_limits_rad)
            margin = float(np.minimum(q - limits[:, 0], limits[:, 1] - q).min())
            minimum_joint_margin = min(minimum_joint_margin, margin)
            require(margin >= -1e-6, "robot_joint_limit", tick)
            for entity, link in (("fiber_bundle", "fixed_terminal"), ("bundling_ring", None)):
                body = world["articulations"][entity]["links"][link] if link else world["bodies"][entity]
                first = (initial["world"]["articulations"][entity]["links"][link] if link
                         else initial["world"]["bodies"][entity])
                require(np.allclose(body["position_m"], first["position_m"], atol=1e-8, rtol=0)
                        and np.allclose(body["quaternion_wxyz"], first["quaternion_wxyz"], atol=1e-8, rtol=0),
                        "fixed_fixture_moved_" + entity, tick)
            hand = world["grasp"]["hands"]["arm"]
            binding = hand["binding"]
            require(not held_started or hand["phase"] == "holding", "sheath_grasp_lost", tick)
            if binding is not None:
                held_started = True
                evidence = binding["acquisition_evidence"]
                birth_tick = evidence["physics_step"]
                child = world["articulations"]["fiber_bundle"]["links"][target.link]
                if birth_tick not in acquired:
                    acquired.add(birth_tick)
                    require(birth_tick == tick and binding["target"] == ["fiber_bundle", target.link],
                            "invalid_grasp_target_or_acquisition_tick", tick)
                    center = np.asarray(child["position_m"]) + rotation(child["quaternion_wxyz"]).apply(target.center_m)
                    contacts = {name: [entry[field] for entry in evidence["rows"]] for name, field in
                                (("link_a", "link_a"), ("link_b", "link_b"),
                                 ("position", "position_m"), ("penetration", "penetration_m"))}
                    require(bool(bilateral_contact_rows(contacts, fingers, names[f"fiber_bundle/{target.link}"],
                        center_m=center, radius_m=target.radius_m, max_penetration_m=cfg.grasp_assist.max_penetration_m)),
                        "missing_bilateral_sheath_contacts", tick)

                    def array(value):
                        if isinstance(value, dict) and "array_file" in value:
                            with np.load(run / "private" / value["array_file"], allow_pickle=False) as chunk:
                                return chunk[value["key"]]
                        return np.asarray(value)

                    native = {key: array(value) for key, value in world["contacts"].items()}
                    for entry in evidence["rows"]:
                        require(any(a == entry["link_a"] and b == entry["link_b"] and d == entry["penetration_m"]
                                    and np.array_equal(f, entry["force_n"])
                                    and (p is None or np.array_equal(p, entry["position_m"]))
                                    for a, b, d, f, p in zip(native["link_a"], native["link_b"], native["penetration"],
                                        native["force"], native.get("position", [None] * len(native["link_a"])))),
                                "grasp_evidence_not_in_native_contacts", tick)
                parent = world["articulations"]["robot"]["links"][group.hand_link]
                actual = relative_pose(parent["position_m"], parent["quaternion_wxyz"],
                                       child["position_m"], child["quaternion_wxyz"])
                translation, angle = relative_error(binding["relative_pose"], actual)
                maximum_grasp_translation = max(maximum_grasp_translation, translation)
                maximum_grasp_rotation = max(maximum_grasp_rotation, angle)
                require(translation <= cfg.grasp_assist.max_translation_error_m
                        and angle <= cfg.grasp_assist.max_rotation_error_rad, "unhealthy_sheath_grasp", tick)
        require(checked > 1 and task.result.task_success, "native_success_not_reproduced")
        require(len(acquired) == 1, "expected_one_continuous_sheath_grasp")
    result = dict(passed=not failures, failures=failures, instance_id=task.instance_id,
        checked_physics_ticks=checked, native_task_success=task.result.task_success,
        final_metrics=dict(task.result.metrics), stable_time_s=task.stable_time_s,
        acquisition_ticks=sorted(acquired), maximum_sampled_bend_deg=maximum_bend,
        maximum_grasp_translation_error_m=maximum_grasp_translation,
        maximum_grasp_rotation_error_rad=maximum_grasp_rotation, minimum_arm_joint_margin_rad=minimum_joint_margin,
        contact_coverage="saved native substep summaries; no continuous-time CCD claim",
        assist_model=cfg.grasp_assist.model,
        physics_states_sha256=evidence_digest(run / "private/physics_states.jsonl")[0],
        auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write_json_atomic(output / "audit.json", result)
    return result
