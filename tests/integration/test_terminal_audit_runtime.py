"""Native terminal audit probes. No successful robot policy qualification."""
from pathlib import Path
import json
import os
import traceback

import numpy as np
import pytest

from runtime_evidence import RuntimeEvidence
from topogym.config import SimulatorConfig
from topogym.config.registry import task_definition
from topogym.simulator.env import Env
from topogym.utils.io import to_jsonable

pytestmark = [pytest.mark.genesis, pytest.mark.render]


def setup(name, task_id, variation="base", **kwargs):
    root = Path(os.environ["TOPOGYM_TEST_OUTPUT"])
    cfg = SimulatorConfig(task_id=task_id, variation_id=variation, compute_backend="cuda",
        precision="64", enable_rgb=True, enable_privileged=True,
        work_dir=root/name/"episodes", **kwargs)
    evidence = RuntimeEvidence(root/name, task_id, cfg)
    evidence.report["scope"] = "Terminal audit mechanism, not a complete robot solution"
    evidence.save()
    return Env(cfg), evidence


@pytest.mark.parametrize("level", ("easy", "medium", "hard"))
def test_claws_native_reset_uses_finalized_coordinates(level):
    class Capture(task_definition("interlocked_claws", level)):
        def finalize_spec(self, spec, **kwargs):
            self.audit_original = spec
            final = super().finalize_spec(spec, **kwargs)
            self.audit_final = final
            return final

    env, evidence = setup("claws_"+level, "interlocked_claws", level)
    env._task_class = Capture
    error = None
    try:
        with evidence.stage("native_reset_pose_comparison") as row:
            obs, info = env.reset(seed=0)
            evidence.sample(env, obs, info, label="initial")
            state = env._world.read_state()
            differences = {}
            originals = {e.name: e for e in env._task.audit_original.entities}
            for entity in env._task.audit_final.entities:
                if entity.name == "goal_region":
                    continue
                actual = state["bodies"][entity.name]
                error_final = np.linalg.norm(actual["position_m"]-entity.position_m)
                error_original = np.linalg.norm(actual["position_m"]-originals[entity.name].position_m)
                assert error_final < 1e-8 and error_original > .1
                q = np.asarray(actual["quaternion_wxyz"])
                expected = np.asarray(entity.quaternion_wxyz)
                assert min(np.linalg.norm(q-expected), np.linalg.norm(q+expected)) < 1e-8
                differences[entity.name] = dict(finalized_error_m=error_final,
                    original_error_m=error_original, native_position_m=actual["position_m"])
            row["pose_comparison"] = to_jsonable(differences)
            assert env._task.evaluate_state(state)[:2] == (False, None)
        with evidence.stage("short_native_hold"):
            for _ in range(4):
                obs, _, done, truncated, info = env.step({})
                evidence.sample(env, obs, info)
                assert not done and not truncated
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        try:
            evidence.close(error)
        finally:
            env.close()


@pytest.mark.parametrize("dt", (.0025, .00125), ids=("default_dt", "half_dt"))
@pytest.mark.fem
@pytest.mark.ipc
def test_rope_native_aperture_boundary_with_continuous_endpoint_drive(dt):
    from types import SimpleNamespace
    from topogym.tasks.rope_threading.common import RopeThreadingTask
    from topogym.tasks.base import TaskSpec, EntitySpec
    from topogym.assets.geometry.rope_threading import ring_mesh
    from topogym.assets.materials import rope_ipc_parameters
    from topogym.utils.grasp import GraspAssistConfig, SoftGraspTarget
    from topogym.utils.arrays import to_numpy
    from scipy.spatial.transform import Rotation
    import trimesh

    class ApertureProbe(RopeThreadingTask):
        def declare(self, asset_dir, table_height_m):
            self.table_height_m = table_height_m
            ring = dict(name="R1", center_m=[0,-.3,.035], normal=[1,0,0],
                basis_u=[0,1,0], basis_v=[0,0,1], radius_m=.020, tube_radius_m=.004, segments=64)
            self.layout = SimpleNamespace(rope_radius_m=.002, rings=lambda:[ring],
                required_crossings=lambda:[("R1",1)])
            line = np.c_[np.linspace(-.080,-.015,20), np.full(20,-.3), np.full(20,.035)]
            rope, self.centerline_map, self.audit_skin = rope_entity(asset_dir, line, .002, table_height_m)
            mesh = ring_mesh(ring)
            path = Path(asset_dir)/"R1.glb"
            mesh.export(path)
            rim = EntitySpec("R1", "mesh", path, (0,0,table_height_m), fixed=True,
                material={"coup_type":"ipc_only"}, surface={"color":(.3,.55,.8)},
                morph_options={"convexify":False,"decimate":False,"file_meshes_are_zup":True})
            return TaskSpec((rope,rim), {"fem":{},"ipc":rope_ipc_parameters()},
                dict(probe="single ring, owner-driven soft endpoint constraints; not robot actions"))

    cfg = GraspAssistConfig(model="ipc_soft_band_v1", targets=(SoftGraspTarget("rope"),))
    env, evidence = setup("rope_"+str(dt), "rope_threading", physics_dt_s=dt,
        control_decimation=round(.025/dt), grasp_assist=cfg)
    env._task_class = ApertureProbe
    error = None
    try:
        with evidence.stage("nonintersecting_native_birth") as row:
            obs, info = env.reset(seed=0)
            evidence.sample(env, obs, info, label="initial")
            state = env._world.read_state()
            query = NativeSurfaceQuery(env, ("R1",))
            skin = env._task.audit_skin
            initial = query.measure(state["fem"]["rope"]["position_m"], skin)
            assert not initial["surface_intersection"] and initial["surface_clearance_m"] > 0
            assert not env._task.evaluate_state(state)[0]
            row["independent_geometry"] = initial
        with evidence.stage("continuous_native_endpoint_drive") as row:
            coupler = env._world.scene.sim.coupler
            rope = env._world.entities["rope"]
            material = np.asarray(rope.material_coordinates)[:,0]
            indices = np.flatnonzero((material-material.min() <= .004) | (material.max()-material <= .004))
            birth = state["fem"]["rope"]["position_m"].copy()
            schedule = np.array([[0,0,0],[.10,0,0],[.45,.04,0],[.70,.04,.021],
                                 [.95,.04,.021],[1.20,.04,0],[1.80,.04,0]])

            class Driver:
                hold_all = None

                def update_entity_targets(self, entity, geometry):
                    import uipc
                    t = (coupler._ipc_world.frame()+1)*dt/env.config.solver_substeps
                    displacement = [np.interp(t,schedule[:,0],schedule[:,1]),
                                    np.interp(t,schedule[:,0],schedule[:,2]),0.]
                    flags = uipc.view(geometry.vertices().find("is_constrained")).reshape(-1)
                    targets = uipc.view(geometry.vertices().find("aim_position")).reshape(-1,3)
                    flags[:] = 0
                    flags[indices] = 1
                    targets[indices] = birth[indices]+displacement
                    if self.hold_all is not None:
                        flags[:] = 1
                        targets[:] = self.hold_all

            driver = Driver()
            coupler.grasp_backend = driver
            row.update(intervention="Continuous external native SPC targets on two 4 mm endpoint bands; no robot grasp claim",
                schedule_time_x_y=schedule.tolist(), constrained_vertices=len(indices),
                production_material_parameters=True, production_v13_mesh=True)
            measurements = []
            for _ in range(72):
                obs, _, done, truncated, info = env.step({})
                evidence.sample(env, obs, info)
                state = env._world.read_state()
                raw = env._task.evaluate_state(state)
                points = state["fem"]["rope"]["position_m"]
                exact = query.measure(points,skin)
                depth = 0.
                if exact["surface_intersection"]:
                    # Quantitative lower bound from vertices inside the actual
                    # collision solid, independent of the three plane tests.
                    for _, geom in query.geoms:
                        q = to_numpy(geom.get_quat(relative=False))
                        vertices = Rotation.from_quat(q[[1,2,3,0]]).apply(geom.init_verts)+to_numpy(geom.get_pos(relative=False))
                        mesh = trimesh.Trimesh(vertices,geom.init_faces,process=False)
                        depth = max(depth, float(trimesh.proximity.signed_distance(mesh, points[np.unique(skin)]).max()))
                measurements.append(dict(physics_step=state["physics_step"],raw=raw, independent=exact,
                    vertex_penetration_lower_bound_m=depth, ipc=state["ipc"],
                    false_positive_over_1mm=bool(raw[0] and depth > .001)))
                row.update(measurements=to_jsonable(measurements),
                    runtime_false_positive_observed=any(x["false_positive_over_1mm"] for x in measurements),
                    minimum_surface_clearance_m=min(x["independent"]["surface_clearance_m"] for x in measurements),
                    raw_candidate_samples=sum(bool(x["raw"][0]) for x in measurements))
                evidence.save()
                assert not done and not truncated and raw[1] is None
            assert row["minimum_surface_clearance_m"] < .001, "The probe did not reach the aperture boundary"
        with evidence.stage("native_quiet_positive_control") as row:
            # The free interior can keep oscillating after endpoint motion.
            # For this separate admission control, native springs hold the
            # attained, nonintersecting shape; positions/velocities are never
            # overwritten. This is explicitly external support, not release
            # qualification or a robot manipulation success demonstration.
            driver.hold_all = env._world.read_state()["fem"]["rope"]["position_m"].copy()
            row["intervention"] = "Native SPC targets now hold all attained material positions; no state overwrite"
            row["constrained_vertices"] = len(driver.hold_all)
            positive = []
            for _ in range(12):
                obs, _, done, truncated, info = env.step({})
                evidence.sample(env, obs, info, label="externally_supported_positive_control")
                state = env._world.read_state()
                raw = env._task.evaluate_state(state)
                exact = query.measure(state["fem"]["rope"]["position_m"], skin)
                positive.append(dict(physics_step=state["physics_step"],raw=raw,independent=exact,ipc=state["ipc"]))
                row["measurements"] = to_jsonable(positive)
                row["raw_candidate_samples"] = sum(bool(x["raw"][0]) for x in positive)
                evidence.save()
                assert not done and not truncated and raw[1] is None and not exact["surface_intersection"]
            assert row["raw_candidate_samples"] > 0, "A stationary native positive control was not obtained"
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        try:
            evidence.close(error)
        finally:
            env.close()


def rope_entity(folder, line, radius, height):
    """Use the production v13 material volume and constitutive parameters."""
    from topogym.tasks.base import EntitySpec
    from topogym.assets.geometry.rope_volume import write_rope_volume
    from topogym.assets.materials import rope_fem_parameters
    from topogym.utils.geometry.rope import load_centerline_map, make_elastic_tube_mesh, write_obj
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    volume = write_rope_volume(folder/"rope_volume.npz", line, radius)
    vertices, faces = make_elastic_tube_mesh(line, radius=radius, radial_segments=24)
    write_obj(folder/"rope.obj", vertices, faces)
    with np.load(volume) as data:
        skin = data["surface_faces"].copy()
    entity = EntitySpec("rope", "mesh", folder/"rope.obj", (0,0,height),
        physics_model="fem_elastic", volume_path=volume, material=rope_fem_parameters(),
        surface={"color":(.85,.4,.08)}, morph_options={"convexify":False,"decimate":False})
    return entity, load_centerline_map(volume), skin


class NativeSurfaceQuery:
    """FCL triangle BVH from loaded collision meshes, independent of AABBs."""
    def __init__(self, env, entity_names):
        import trimesh
        self.trimesh = trimesh
        self.manager = trimesh.collision.CollisionManager()
        self.geoms = []
        self.solver = env._world.scene.sim.rigid_solver
        for name in entity_names:
            for link in env._world.entities[name].links:
                for geom in link.geoms:
                    key = f"{name}/{link.name}/{geom.idx}"
                    mesh = trimesh.Trimesh(np.asarray(geom.init_verts), np.asarray(geom.init_faces), process=False)
                    if not mesh.is_watertight and geom.is_convex:
                        mesh = mesh.convex_hull
                    self.manager.add_object(key, mesh)
                    self.geoms.append((key, geom))

    def measure(self, vertices, faces):
        from scipy.spatial.transform import Rotation
        from topogym.utils.arrays import to_numpy
        indices = [geom.idx for _, geom in self.geoms]
        positions = to_numpy(self.solver.get_geoms_pos(indices, relative=False)).reshape(-1,3)
        quaternions = to_numpy(self.solver.get_geoms_quat(indices, relative=False)).reshape(-1,4)
        rotations = Rotation.from_quat(quaternions[:,[1,2,3,0]]).as_matrix()
        for (key, geom), position, rotation in zip(self.geoms, positions, rotations, strict=True):
            transform = np.eye(4)
            transform[:3,:3] = rotation
            transform[:3,3] = position
            self.manager.set_transform(key, transform)
        mesh = self.trimesh.Trimesh(vertices, faces, process=False)
        collision = self.manager.in_collision_single(mesh)
        distance, names = self.manager.min_distance_single(mesh, return_name=True)
        return dict(surface_intersection=bool(collision), surface_clearance_m=float(distance), nearest=names)

    def actual_surface_intersects_target_box(self, vertices):
        box = self.trimesh.creation.box(extents=np.ptp(vertices,axis=0))
        box.apply_translation((np.min(vertices,axis=0)+np.max(vertices,axis=0))/2)
        return bool(self.manager.in_collision_single(box))


@pytest.mark.parametrize("case", ("outside", "empty_interior", "near"))
@pytest.mark.fem
@pytest.mark.ipc
def test_knot_native_released_arc_clearance(case):
    from types import SimpleNamespace
    from topogym.tasks.knot_untying.common import KnotUntyingTask
    from topogym.tasks.base import TaskSpec
    from topogym.assets.materials import rope_ipc_parameters
    from topogym.evaluation.terminal import evaluate_settling
    # The default ALOHA's real left mounting foot occupies an empty portion of
    # the arc's AABB. No robot teleport or joint-pose intervention is needed.
    centers = {"outside":(-.10,-.40), "empty_interior":(-.6046786,-.019), "near":(-.6046786,-.019)}
    bend_radius = .115 if case == "near" else .130
    arc_angle = np.pi/4

    class ArcProbe(KnotUntyingTask):
        # This reduced fixture alone enables success to check the full Env
        # termination chain. Registered production Knot remains disabled.
        goal_complete = True
        audit_callback = None

        def evaluate_state(self, state):
            result = super().evaluate_state(state)
            if self.audit_callback is not None:
                self.audit_callback(state, result)
            return result

        def declare(self, asset_dir, table_height_m):
            self.table_height_m = table_height_m
            radius = .002
            theta = np.linspace(0, arc_angle, 100)
            line = np.c_[np.asarray(centers[case]) + bend_radius*np.c_[np.cos(theta),np.sin(theta)],
                         np.full(len(theta), radius+.001)]
            entity, self.centerline_map, self.audit_skin = rope_entity(asset_dir, line, radius, table_height_m)
            self.layout = SimpleNamespace(rope_radius_m=radius)
            return TaskSpec((entity,), {"fem":{},"ipc":rope_ipc_parameters()},
                dict(probe="released 45-degree arc; no attachments or external forces", case=case,
                     goal_evaluation_complete=bool(self.goal_complete)))

    env, evidence = setup("knot_"+case, "knot_untying")
    env._task_class = ArcProbe
    error = None
    try:
        with evidence.stage("native_released_arc_birth") as row:
            obs, info = env.reset(seed=0)
            evidence.sample(env, obs, info, label="initial")
            initial_geometry = env._world.read_state()["release_geometry"]
            assert initial_geometry["schema_version"] == 2
            (evidence.folder/"release_geometry_initial.json").write_text(
                json.dumps(to_jsonable(initial_geometry), indent=2)+"\n")
            row["goal_complete_override_scope"] = "isolated ArcProbe test subclass only"
            query = NativeSurfaceQuery(env, ("robot",))
            birth_surface = query.measure(env._world.read_state()["fem"]["rope"]["position_m"], env._task.audit_skin)
            box_intersection = query.actual_surface_intersects_target_box(env._world.read_state()["fem"]["rope"]["position_m"])
            row["geometry"] = dict(center_xy_m=centers[case], bend_radius_m=bend_radius, angle_rad=arc_angle,
                rope_radius_m=.002, material_profile="v13_material_mesh", robot="aloha", birth_surface=birth_surface)
            row["actual_robot_surface_intersects_whole_rope_aabb"] = box_intersection
            assert box_intersection == (case != "outside")
            assert not birth_surface["surface_intersection"]
            if case == "near":
                assert 0. < birth_surface["surface_clearance_m"] < .005
            else:
                assert birth_surface["surface_clearance_m"] > .005
        with evidence.stage("independent_surface_and_full_window_measurement") as row:
            measurements = []
            window = dict(reference=None, start=None, longest=0., positive_start=None, positive_longest=0.,
                negative_start=None, negative_longest=0.)

            def measure_tick(state, raw):
                _, metrics, _ = evaluate_settling(state, env._task.final_settling_spec())
                points = state["fem"]["rope"]["position_m"]
                exact = query.measure(points, env._task.audit_skin)
                tick = state["physics_step"]
                quiet_released = bool(raw[0] and metrics["assist_released"] and metrics["quiet"] and
                    metrics["evaluation_status"] == "available")
                qualifies = bool(quiet_released and
                    exact["surface_clearance_m"] > .005 and not exact["surface_intersection"])
                drift = 0. if window["reference"] is None else float(np.linalg.norm(points-window["reference"],axis=1).max())
                if not quiet_released or drift > .001:
                    window.update(reference=None, start=None, positive_start=None, negative_start=None)
                if quiet_released and window["reference"] is None:
                    window["reference"] = points.copy()
                near = quiet_released and 0. < exact["surface_clearance_m"] < .005 and not metrics["robot_clear"]
                if near:
                    if window["negative_start"] is None:
                        window["negative_start"] = tick
                    window["negative_longest"] = max(window["negative_longest"], (tick-window["negative_start"])*env.config.physics_dt_s)
                else:
                    window["negative_start"] = None
                if not qualifies:
                    window.update(start=None, positive_start=None)
                if qualifies:
                    if not metrics["robot_clear"]:
                        if window["start"] is None:
                            window["start"] = tick
                        window["longest"] = max(window["longest"], (tick-window["start"])*env.config.physics_dt_s)
                        window["positive_start"] = None
                    else:
                        if window["positive_start"] is None:
                            window["positive_start"] = tick
                        window["positive_longest"] = max(window["positive_longest"], (tick-window["positive_start"])*env.config.physics_dt_s)
                        window["start"] = None
                measurements.append(dict(physics_step=tick, raw=raw, settling=metrics,
                    independent=exact, independently_measured_window_drift_m=drift))

            env._task.audit_callback = measure_tick
            for step in range(80):
                obs, _, done, truncated, info = env.step({})
                evidence.sample(env, obs, info)
                row.update(measurements=to_jsonable(measurements),
                    measurement_scope="every native physics tick, independent triangle surfaces and per-vertex window drift",
                    longest_mismatch_window_s=window["longest"], longest_positive_window_s=window["positive_longest"],
                    longest_near_negative_window_s=window["negative_longest"],
                    reproduced_full_window_false_negative=window["longest"]+1e-9 >= .5)
                evidence.save()
                assert not truncated and measurements[-1]["raw"][1] is None
                if done:
                    assert case != "near" and env._task.result.task_success
                if max(window["longest"],window["positive_longest"],window["negative_longest"]) >= .5:
                    break
            from topogym.simulator.interaction import public_info
            public = public_info(info)
            row["final_public_feedback"] = to_jsonable(public)
            assert window["longest"] == 0., "A clear, quiet native volume was still rejected"
            if case == "near":
                assert window["negative_longest"]+1e-9 >= .5
                assert not done and not env._task.result.task_success
                assert env._task.result.metrics["stable_time_s"] == 0.
            else:
                assert window["positive_longest"]+1e-9 >= .5
                assert done and env._task.result.task_success and public["task_success"] is True
                assert env._task.result.metrics["stable_time_s"]+1e-9 >= .5
            assert not KnotUntyingTask().goal_complete
    except BaseException:
        error = traceback.format_exc()
        raise
    finally:
        try:
            evidence.close(error)
        finally:
            env.close()
