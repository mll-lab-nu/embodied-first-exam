"""Independent tick-evidence audit of a Blanket oracle run; never trusts the native flag alone.

The flatten predicate is recomputed from the recorded particle arrays with this
module's own code (projected-triangle union, material edge ratios, heights,
speeds), together with the release_settling final-settling gates declared in the
sealed static model (assist released, robot collision bounds clear of the cloth,
drift from the window start), and the 0.5 s hold is re-accumulated per 2.5 ms
physics tick.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

HOME = np.array([0., -.96, 1.16, 0., -.3, 0.])
SIDES = ("left", "right")


def archive_particles(manifest_path, *, field="pos"):
    """Particle positions or velocities in the frozen archive (entity order)."""
    if field not in {"pos", "vel"}:
        raise ValueError("Expected particle pos or vel")
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())

    def find(node, path=""):
        if isinstance(node, dict):
            if node.get("kind") in ("array", "tensor") and "key" in node:
                yield path, node["key"]
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    yield from find(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from find(value, f"{path}[{i}]")
    keys = [k for p, k in find(manifest["tree"]) if p.endswith("PBDSolver/particles/items/value/items/"+field)]
    if len(keys) != 1:
        raise ValueError("Archive particle positions not found uniquely")
    with np.load(manifest_path.with_name("arrays.npz")) as arrays:
        return arrays[keys[0]].reshape(-1, 3)


class Predicate:
    """Own implementation of the release_settling_v1 flatten gates."""
    def __init__(self, uv, config, table_z, layout):
        self.faces = Delaunay(uv).simplices
        edges = np.concatenate((self.faces[:, :2], self.faces[:, 1:], self.faces[:, [2, 0]]))
        self.edges = np.unique(np.sort(edges, axis=1), axis=0)
        self.rest = np.linalg.norm(uv[self.edges[:, 1]]-uv[self.edges[:, 0]], axis=1)
        self.config, self.table_z = config, table_z
        self.area = layout["length_m"]*layout["width_m"]
        self.particle = layout["particle_size_m"]

    def coverage(self, x):
        import shapely
        tri = x[self.faces, :2]
        cross = ((tri[:, 1, 0]-tri[:, 0, 0])*(tri[:, 2, 1]-tri[:, 0, 1])
                 - (tri[:, 1, 1]-tri[:, 0, 1])*(tri[:, 2, 0]-tri[:, 0, 0]))
        tri = tri[np.abs(cross) > 1e-12]
        try:
            area = shapely.area(shapely.union_all(shapely.polygons(tri)))
        except shapely.errors.GEOSException:
            area = shapely.area(shapely.union_all(shapely.polygons(tri), grid_size=1e-8))
        return float(area)/self.area

    def __call__(self, x, v):
        c = self.config
        h = x[:, 2]-self.table_z
        stretch = float((np.linalg.norm(x[self.edges[:, 1]]-x[self.edges[:, 0]], axis=1)/self.rest).max())
        speed = float(np.linalg.norm(v, axis=1).max())
        gates = dict(flat=float(h.max()) <= c["maximum_height_m"], above_table=float(h.min()) >= -self.particle,
                     material_intact=stretch <= c["maximum_stretch_ratio"], settled=speed <= c["maximum_speed_m_s"])
        metrics = dict(maximum_height_m=float(h.max()), minimum_height_m=float(h.min()),
                       maximum_stretch_ratio=stretch, maximum_speed_m_s=speed)
        if all(gates.values()):   # the union is the expensive gate; only needed when the others pass
            metrics["coverage_ratio"] = self.coverage(x)
            gates["covered"] = metrics["coverage_ratio"] >= c["minimum_coverage_ratio"]
        else:
            gates["covered"] = None
        return all(v is True for v in gates.values()), gates, metrics


def release_settled(world, x, v, reference, settling, array):
    """Own implementation of the final-settling gates on one recorded tick."""
    geometry = world.get("release_geometry")
    if world.get("assist_active") is not False or geometry is None or not geometry["complete"]:
        return False
    if not geometry["robot_present"]:
        raise ValueError("Release geometry lacks the robot")
    robot = np.asarray(array(geometry["robot_bounds_m"]), float).reshape(-1, 2, 3)
    pad = settling["particle_radius_m"]
    low, high = x.min(0)-pad, x.max(0)+pad
    gap = np.maximum(np.maximum(low-robot[:, 1], robot[:, 0]-high), 0.)
    clear = float(np.linalg.norm(gap, axis=1).min()) >= settling["clearance_m"]
    quiet = float(np.linalg.norm(v, axis=1).max()) <= settling["maximum_speed_m_s"]
    drift = 0. if reference is None else float(np.linalg.norm(x-reference, axis=1).max())
    return clear and quiet and drift <= settling["maximum_drift_m"]


def audit_execution(run, output, *, require_native_success=False):
    run, output = Path(run), Path(output)
    trail = run/"trail"
    config = json.loads((trail/"config.json").read_text())
    static = json.loads((trail/"private/static_model.json").read_text())
    episode = static["episode"]
    ledger = json.loads((trail/"report.json").read_text())
    oracle = json.loads((run/"oracle_report.json").read_text())
    material = np.load(run/"material_map.npz")
    failures = []

    def fail(reason, tick):
        if len(failures) < 40:
            failures.append(dict(reason=reason, tick=tick))
    if ledger["status"] != "complete":
        raise ValueError("Episode evidence is not sealed")
    segments = [row["result"] for row in ledger["segments"]]
    if any(not r["evidence_complete"] or not r["physics_tick_complete"] for r in segments):
        raise ValueError("Incomplete physical evidence")
    if any(a["end_state_ref"] != b["start_state_ref"] for a, b in zip(segments, segments[1:])):
        raise ValueError("Segment chain is discontinuous")
    scope = dict(task_id=config["task_id"], model=config["grasp_assist"]["model"], control=config["control_mode"],
                 backend=config["compute_backend"], precision=config["precision"], dt=config["physics_dt_s"],
                 substeps=config["solver_substeps"], decimation=config["control_decimation"])
    if scope != dict(task_id="blanket_flatten", model="pbd_local_patch_v1", control="JOINT_ABS", backend="cuda",
                     precision="64", dt=.0025, substeps=4, decimation=10):
        raise ValueError(f"Audit scope differs: {scope}")
    task_config, layout = oracle["task_config"], oracle["layout"]
    settling = episode["terminal"]["final_settling"]
    if settling["particle_targets"] != ["blanket"] or settling["rigid_targets"] or settling["fem_targets"]:
        raise ValueError(f"Audit covers the Blanket-only final-settling contract, not {settling}")
    guard = float(config["grasp_assist"]["targets"][0]["max_strain_ratio"])
    uv = np.asarray(material["uv"])
    if uv.shape != (len(uv), 2) or not np.allclose([uv.min(0), uv.max(0)],
            [[-layout["length_m"]/2, -layout["width_m"]/2], [layout["length_m"]/2, layout["width_m"]/2]], atol=1e-9):
        raise ValueError("Material coordinates do not span the declared rest sheet")
    predicate = Predicate(uv, task_config, oracle["table_height_m"], layout)
    manifest_path = Path(oracle["initial_state_manifest"])
    if "source_snapshot" in manifest_path.parts:   # resolve inside this run's own frozen snapshot (archived copies)
        manifest_path = run.joinpath(*manifest_path.parts[manifest_path.parts.index("source_snapshot"):])
    initial = archive_particles(manifest_path)
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != oracle["initial_state_sha256"]:
        raise ValueError("Frozen initial-state manifest hash differs")
    limits = {s: np.asarray(oracle["joint_limits_rad"][s]) for s in SIDES}
    robot_links = table_links = None
    dt = float(config["physics_dt_s"])
    count, stable, native_success_tick, independent_success_tick = 0, 0., None, None
    max_contact_force = max_joint_excess = 0.
    max_held_ratio, min_height = 0., np.inf
    acquired, released, lost = {s: 0 for s in SIDES}, {s: 0 for s in SIDES}, []
    last_sequence = -1
    last = reference = None
    evidence_hash = hashlib.sha256()
    chunks = {}

    def array(ref):
        path = trail/"private"/ref["array_file"]
        if path not in chunks:
            chunks.clear()
            chunks[path] = np.load(path)
        return chunks[path][ref["key"]]
    with (trail/"private/physics_states.jsonl").open("rb") as stream:
        for line in stream:
            evidence_hash.update(line)
            row = json.loads(line)
            state, world = row["state"], row["world"]
            tick = state["physics_step"]
            if tick != count or state["episode_id"] != episode["episode_id"] or state["branch_id"] != 0:
                raise ValueError("Tick gap, cross-episode state, or rewind in proof chain")
            if abs(state["sim_time_s"]-tick*dt) > 1e-8:
                raise ValueError("Physical time does not match tick count")
            cloth = world["particles"]["blanket"]
            x, v = array(cloth["position_m"]), array(cloth["velocity_m_s"])
            if not (np.isfinite(x).all() and np.isfinite(v).all()):
                fail("nonfinite_cloth", tick)
                continue
            if robot_links is None:
                robot_links = set(world["bodies"]["robot"]["link_indices"])
                table_links = set().union(*(b["link_indices"] for n, b in world["bodies"].items() if n.startswith("table")))
                mount = min(robot_links)
            if tick == 0:
                if np.max(np.abs(x-initial)) != 0. or world["assist_active"]:
                    raise ValueError("Cloth differs from the frozen initial state, or a grasp pre-exists")
                for side in SIDES:
                    if np.max(np.abs(np.asarray(row["robot"][side]["joint_position_rad"])-HOME)) > 1e-4:
                        raise ValueError("Proof did not start at the default home")
            min_height = min(min_height, float(x[:, 2].min())-oracle["table_height_m"])
            for side in SIDES:
                q = np.asarray(row["robot"][side]["joint_position_rad"])
                excess = float(np.max(np.maximum(limits[side][:, 0]-q, q-limits[side][:, 1])))
                max_joint_excess = max(max_joint_excess, excess)
                if excess > 1e-3:
                    fail(f"{side}_joint_limit", tick)
            contacts = world["contacts"]
            a, b = np.asarray(contacts["link_a"]).reshape(-1), np.asarray(contacts["link_b"]).reshape(-1)
            forces = np.asarray(contacts["force"], float).reshape(-1, 3)
            for p, q, force in zip(a, b, forces):
                if ({p, q} & (robot_links-{mount})) and ({p, q} & table_links):
                    value = float(np.linalg.norm(force))
                    max_contact_force = max(max_contact_force, value)
                    if value > .01:
                        fail("robot_table_contact", tick)
            grasp = world.get("grasp", {})
            for event in grasp.get("events", []):
                if event["sequence"] <= last_sequence:
                    continue
                last_sequence = event["sequence"]
                kind, hand = event.get("event"), event.get("hand")
                if kind == "acquired" and hand in SIDES:
                    acquired[hand] += 1
                elif kind == "released" and hand in SIDES:
                    released[hand] += 1
                elif kind == "lost":
                    lost.append(dict(tick=tick, event=event))
            health = grasp.get("health") or {}
            for side, values in health.items():
                if grasp.get("hands", {}).get(side, {}).get("binding"):
                    max_held_ratio = max(max_held_ratio, float(values.get("max_material_edge_ratio", 0.)))
            ok, _, _ = predicate(x, v)
            ok = ok and release_settled(world, x, v, reference, settling, array)
            # The drift reference is the first tick of the current confirmation window.
            reference = (x if reference is None else reference) if ok else None
            stable = stable+dt if ok and tick > 0 and last is not None and last[0] else 0.
            if independent_success_tick is None and ok and stable+1e-12 >= task_config["stable_duration_s"]:
                independent_success_tick = tick
            if native_success_tick is None and row["task"]["result"]["task_success"]:
                native_success_tick = tick
            last = (ok, row)
            count += 1
    if last is None:
        raise ValueError("Empty physical evidence")
    if count-1 != sum(segment["physics_steps"] for segment in segments):
        raise ValueError("Recorded tick count differs from the sealed segment ledger")
    ok, gates, metrics = predicate(np.asarray(array(last[1]["world"]["particles"]["blanket"]["position_m"])),
                                   np.asarray(array(last[1]["world"]["particles"]["blanket"]["velocity_m_s"])))
    # A corner stage may use only one hand. New reports declare the actual
    # stages, including measured fold/clearance corrections; old reports keep
    # their original two-hand route interpretation.
    declared = oracle["route"].get("stages", [dict(grasp_uv=dict.fromkeys(SIDES))])
    executed = oracle.get("stages", [])
    stages = executed if executed and all("grasp_uv" in s for s in executed) else declared
    expected = {side: sum(side in stage["grasp_uv"] for stage in stages) for side in SIDES}
    if acquired != expected:
        fail("expected_one_acquisition_per_hand_per_stage", count-1)
    if lost:
        fail("assisted_grasp_lost", lost[0]["tick"])
    if released != expected:
        fail("expected_one_release_per_hand_per_stage", count-1)
    if max_held_ratio > guard:
        fail("held_material_edge_ratio_above_assist_guard", count-1)
    if min_height < -predicate.particle:
        fail("cloth_below_table", count-1)
    native = bool(last[1]["task"]["result"]["task_success"])
    if require_native_success and not native:
        fail("native_task_success_missing", count-1)
    if independent_success_tick is None:
        fail("independent_predicate_hold_missing", count-1)
    elif native and independent_success_tick != native_success_tick:
        fail("independent_and_native_success_ticks_differ", count-1)
    return dict(status="passed" if not failures else "rejected", passed=not failures, failures=failures,
        native_task_success=native, accepted_proof=not failures and native,
        native_success_tick=native_success_tick, independent_success_tick=independent_success_tick,
        checked_states=count, physics_steps=count-1, physical_evidence_sha256=evidence_hash.hexdigest(),
        instance_id=episode["instance_id"], seed=episode["seed"], final_gates=gates, final_metrics=metrics,
        acquisitions=acquired, releases=released, lost_events=lost[:5],
        maximum_held_material_edge_ratio=max_held_ratio, declared_assist_strain_guard=guard,
        minimum_cloth_height_m=min_height,
        maximum_robot_table_contact_force_n=max_contact_force, maximum_joint_limit_excess_rad=max_joint_excess,
        scope=scope, assistance="pbd_local_patch_v1",
        limitations=["Finite seed/default-parameter frozen instance", "Assisted patch attachment admitted by bilateral "
                     "finger-surface proximity; not friction-only, no clamping force", "Tick-end evidence; no "
                     "continuous-time/all-substep qualification", "Robot-cloth contact is simulated but not audited "
                     "for penetration", "Release clearance uses the recorded robot collision bounding boxes",
                     "Robot mounting link contact with the table is excluded"])
