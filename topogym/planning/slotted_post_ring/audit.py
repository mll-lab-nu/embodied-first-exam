"""Read-only diagnostics for local v15 Session evidence; never changes evaluation rules.

Robot/fixture samples are diagnostic measurements, not an extra failure rule or
a proof of continuous nonpenetration. Harbor qualification requires its verifier.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

SIDES = ("left", "right")
FIXTURES = ("base", "post", "stand_left", "stand_right")
SAMPLES_PER_GEOM = 200


def export_robot_geometry(env, output):
    """Robot collision surfaces in their link frames, for the per-tick clearance audit."""
    from topogym.utils.arrays import to_numpy
    from topogym.utils.io import write_json_atomic
    arrays, links = {}, []
    for link in env._robot.entity.links:
        p = to_numpy(link.get_pos()).reshape(3)
        r = Rotation.from_quat(to_numpy(link.get_quat()).reshape(4)[[1, 2, 3, 0]])
        keys = []
        for geom in link.geoms:
            key = f"geom_{len(arrays)//2}"
            arrays[key+"_vertices"] = r.inv().apply(to_numpy(geom.get_verts()).reshape(-1, 3)-p)
            arrays[key+"_faces"] = np.asarray(geom.init_faces)
            keys.append(key)
        links.append(dict(name=link.name, index=int(link.idx), local_index=int(link.idx_local), geoms=keys))
    output = Path(output)
    np.savez_compressed(output/"robot_geometry.npz", **arrays)
    write_json_atomic(output/"robot_geometry.json", dict(
        links=links, sha256=hashlib.sha256((output/"robot_geometry.npz").read_bytes()).hexdigest(),
        frame="Genesis authored link frames", source="imported robot collision surfaces"))


def rebuild_task(variation, seed, directory, *, parameters=None):
    """Declare and finalize the instance (assets, goal region) exactly as an episode does, without physics."""
    from topogym.config.registry import task_definition
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    config = SimulatorConfig(task_id="slotted_post_ring", variation_id=variation, enable_rgb=False,
                             compute_backend="cpu", task_parameters=parameters or {})
    scene = load_scene_config(config)
    task = task_definition("slotted_post_ring", variation.removeprefix("slotted_post_ring_"))(parameters or {}, seed=seed)
    table = scene.env.world.table
    spec = task.declare(directory, float(table.pos[2]+table.size[2]/2))
    spec = task.finalize_spec(spec, asset_dir=directory, scene_config=scene)
    return task, spec


class FixtureSolids:
    """Fixture bounds with the post slot removed; optional stands use conservative boxes."""

    def __init__(self, task):
        layout = task.layout
        self.origin = np.array([*task.config["center_xy_m"], task.table_height_m], float)
        self.boxes = {name: (np.min(task.placement_vertices[name], axis=0)+self.origin,
                             np.max(task.placement_vertices[name], axis=0)+self.origin) for name in FIXTURES if name in task.placement_vertices}
        self.slot_half = layout.slot_width_m/2
        self.slot_z = (self.origin[2]+layout.slot_bottom_m+self.slot_half,
                       self.origin[2]+layout.slot_top_m-self.slot_half)

    def depth(self, points):
        """name -> deepest intrusion (m) of points into each solid (0 when clear)."""
        out = {}
        for name, (lo, hi) in self.boxes.items():
            d = np.minimum(points-lo, hi-points).min(axis=1)
            if name == "post":
                # Inside the stadium-shaped slot (any y across the post) is free space.
                dx = np.abs(points[:, 0]-self.origin[0])
                dz = np.clip(points[:, 2], *self.slot_z)-points[:, 2]
                free = np.hypot(dx, dz) < self.slot_half
                d = np.where(free, -1., d)
            out[name] = float(max(0., d.max()))
        return out


def robot_samples(run):
    descriptor = json.loads((run/"robot_geometry.json").read_text())
    payload = run/"robot_geometry.npz"
    if hashlib.sha256(payload.read_bytes()).hexdigest() != descriptor["sha256"]:
        raise ValueError("Robot geometry checksum mismatch")
    samples = {}
    with np.load(payload) as arrays:
        for link in descriptor["links"]:
            if link["local_index"] == 0:
                continue  # the mounting base sits on the table by design
            points = [arrays[key+"_vertices"] for key in link["geoms"]]
            points = np.vstack([v[np.linspace(0, len(v)-1, min(SAMPLES_PER_GEOM, len(v))).astype(int)]
                                for v in points if len(v)]) if points else np.zeros((0, 3))
            if len(points):
                samples[link["name"]] = points
    return samples


def audit_execution(run, output, *, require_native_success=False):
    from topogym.utils.io import to_jsonable
    from .runtime import PROFILE, build_config, tooling

    run, output = Path(run), Path(output)
    config = json.loads((run / "config.json").read_text())
    episode = json.loads((run / "private/static_model.json").read_text())["episode"]
    report = json.loads((run / "run_report.json").read_text())
    if report.get("format") != "slotted_session_v1" or report.get("profile") != PROFILE:
        raise ValueError("Expected local release Session evidence, not the external v12 run")
    if report["status"] not in {"native_success_pending_verifier", "development_prefix", "not_passed"}:
        raise ValueError("Execution did not seal complete Session evidence")
    expected = build_config(report["variant"], report["seed"])
    for key in ("task_id", "variation_id", "robot_id", "seed", "compute_backend", "precision",
                "physics_dt_s", "solver_substeps", "control_decimation", "reset_physics_steps",
                "ipc_settled_state", "ipc_options", "rigid_options", "task_parameters", "grasp_assist",
                "terminal_contract_version"):
        if config[key] != expected[key]:
            raise ValueError(f"Configuration differs from the local release: {key}")
    local = tooling()
    if report["tooling_sha256"] != hashlib.sha256(Path(local.__file__).read_bytes()).hexdigest():
        raise ValueError("Recorded Session tooling differs from the audit source")
    dt = float(config["physics_dt_s"])
    rules = report["rules"]
    soft_rule = dict(local.SOFT_RULE, window_ticks=local.rule_window_ticks(dt, local.SOFT_RULE["window_s"]))
    if rules["revision"] != local.RULES_REVISION or rules["soft"] != soft_rule:
        raise ValueError("Recorded soft-body rules differ from the local release")
    for when in ("initial", "final"):
        if report["evaluation"][when]["rules"] != rules:
            raise ValueError("Session rules changed during the run")
    result = report["result"]
    if not result["evidence_complete"] or not result["physics_tick_complete"]:
        raise ValueError("Incomplete Session trajectory")
    task, _ = rebuild_task(episode["variation_id"], episode["seed"], output / "assets",
                           parameters=config["task_parameters"])
    if episode["model_revision"] != task.model_revision or episode["instance_id"] != task.instance_id:
        raise ValueError("Recorded instance or model revision differs from the local source")
    if episode["terminal"]["goal_region"] != to_jsonable(asdict(task.goal_region)):
        raise ValueError("Goal region changed")
    solids, samples = FixtureSolids(task), robot_samples(run)
    failures, chunks, counts = [], {}, {}
    count, streak_start, success_tick, last_state = 0, None, None, None
    worst = dict(robot_fixture_m=0., cord_min_volume=None, attachment_m=0.)
    evidence = hashlib.sha256()
    window = float(task.config["stable_duration_s"])
    initial = report["initial_state"]
    if initial["physics_step"] != 0 or initial["episode_id"] != episode["episode_id"]:
        raise ValueError("Run did not start at the current episode's initial tick")

    def fail(reason, tick):
        if len(failures) < 40:
            failures.append(dict(reason=reason, tick=tick))

    def materialize(value):
        if isinstance(value, dict):
            if "array_file" in value:
                path = (run / "private" / value["array_file"]).resolve()
                if not path.is_relative_to((run / "private/arrays").resolve()):
                    raise ValueError("Array reference is outside the evidence directory")
                if path not in chunks:
                    chunks.clear()
                    with np.load(path, allow_pickle=False) as archive:
                        chunks[path] = {key: archive[key] for key in archive.files}
                return chunks[path][value["key"]]
            return {key: materialize(child) for key, child in value.items()}
        if isinstance(value, list):
            return [materialize(child) for child in value]
        return value

    with (run / "private/physics_states.jsonl").open("rb") as stream:
        for line in stream:
            evidence.update(line)
            row = json.loads(line)
            state, world = row["state"], materialize(row["world"])
            tick = state["physics_step"]
            if (tick != count or state["episode_id"] != initial["episode_id"]
                    or state["branch_id"] != initial["branch_id"]):
                raise ValueError("Tick gap, cross-episode state or rewind in the recorded path")
            if abs(state["sim_time_s"] - tick * dt) > 1e-8:
                raise ValueError("Physical time differs from tick count")
            count += 1
            ipc = world["ipc"]
            volume = float(ipc["volume_ratio"]["cord"]["minimum"])
            maximum = float(ipc["volume_ratio"]["cord"]["maximum"])
            residuals = {name: float(ipc["attachment_residual_m"][name])
                         for name in task.placement_attachment_names}
            if not np.isfinite([volume, maximum, *residuals.values()]).all():
                raise ValueError("Nonfinite IPC diagnostics")
            if maximum < volume or min(residuals.values()) < 0:
                raise ValueError("Inconsistent IPC diagnostics")
            worst["cord_min_volume"] = volume if worst["cord_min_volume"] is None else min(worst["cord_min_volume"], volume)
            worst["attachment_m"] = max(worst["attachment_m"], *residuals.values())
            # Initial tick is preparation. v15 counts failures only on committed physics advances.
            if tick:
                counts = local.soft_rule_tick(counts, {"cord": volume}, residuals,
                                              residual_m=soft_rule["residual_m"])
            age = max((age for group in counts.values() for age in group.values()), default=0)
            if not ipc["native_valid"] or age >= soft_rule["window_ticks"]:
                fail("cord_or_ipc_invalid_under_local_rules", tick)
            if world["assist_active"]:
                fail("unexpected_grasp_assist", tick)
            if tick % int(config["control_decimation"]) == 0:
                links = world["articulations"]["robot"]["links"]
                for name, points in samples.items():
                    pose = links[name]
                    points = Rotation.from_quat(np.asarray(pose["quaternion_wxyz"])[[1, 2, 3, 0]]).apply(points) + pose["position_m"]
                    worst["robot_fixture_m"] = max(worst["robot_fixture_m"], *solids.depth(points).values())
            # A transient inversion is not yet a v15 failure, but cannot count towards goal stability.
            reached, _, _ = task.evaluate_goal_region(world, task.goal_region)
            if tick == 0 or not reached:
                streak_start = None
            elif streak_start is None:
                streak_start = tick
            if tick and reached and (tick - streak_start) * dt >= window - 1e-12 and success_tick is None:
                success_tick = tick
            last_state = state
    if last_state is None or last_state != report["final_state"] or count != report["evidence"]["tick_records"]:
        raise ValueError("Recorded ticks do not cover the reported end of execution")
    native = report["task_result"]
    if require_native_success and (report.get("stop_after") is not None or not native["task_success"]
            or not native["terminated"] or success_tick != last_state["physics_step"]):
        fail("missing_complete_native_and_recomputed_success", last_state["physics_step"])
    return dict(passed=not failures, qualification="unqualified", harbor_qualified=False,
                profile=PROFILE, instance_id=task.instance_id, model_revision=task.model_revision,
                ticks=count, evidence_sha256=evidence.hexdigest(), independent_success_tick=success_tick,
                native=native, worst=worst, failures=failures, rules=rules,
                notes=["Local v15 persistence rules are used; external per-tick failure thresholds are not imported",
                       "Robot/fixture depths are sampled diagnostics, not a new failure threshold",
                       "This read-only audit does not certify actuator forces, continuous collision or Harbor replay"])
