"""Offline bounded velocity preparation; World owns every physical advance.

Adapted from the historical material velocity projection. No position/rest/
topology/support writes, no pins, and no forced velocity reset on release.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import numpy as np
from scipy.spatial import cKDTree

from topogym.assets.geometry.blanket_gathered import preparation_target
from topogym.evaluation.cloth_metrics import measure, initial_gates, AcceptanceWindow
from topogym.utils.arrays import to_numpy


@dataclass(frozen=True)
class PreparationConfig:
    gather_seconds: float = 3.
    twist_seconds: float = 3.
    lower_seconds: float = 2.
    hold_seconds: float = .3
    controlled_settle_seconds: float = 5.
    settling_speed_limit_m_s: float = .04
    maximum_settle_seconds: float = 8.
    stable_window_seconds: float = .6
    maximum_speed_m_s: float = .12
    servo_gain_s: float = 12.
    projection_strength: float = 32.
    projection_correction_rate_s: float = 16.
    projection_maximum_iterations: int = 1000
    maximum_material_stretch: float = 1.15
    maximum_visual_stretch: float = 1.4
    settled_mean_speed_m_s: float = .005
    settled_p99_speed_m_s: float = .015
    settled_maximum_speed_m_s: float = .03
    maximum_drift_m: float = .002
    minimum_coverage_ratio: float = .08
    maximum_coverage_ratio: float = .82
    maximum_height_m: float = .10
    penetration_tolerance_m: float = .001

    def __post_init__(self):
        values = np.asarray(list(asdict(self).values()), dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Preparation parameters must be positive and finite")
        if not self.minimum_coverage_ratio < self.maximum_coverage_ratio < 1:
            raise ValueError("Preparation must leave a nonflat, nondegenerate blanket")
        if type(self.projection_maximum_iterations) is not int:
            raise ValueError("Projection iteration budget must be an integer")


class MaterialVelocityProjection:
    def __init__(self, edges, rest, uv, *, strength, correction, clearance, maximum_iterations=1000):
        self.edges, self.rest, self.uv = edges, rest, uv
        self.strength, self.correction, self.clearance = strength, correction, clearance
        self.maximum_iterations = maximum_iterations
        self.statistics = dict(calls=0, maximum_iterations_used=0, maximum_relative_residual=0.)

    def project(self, p, requested):
        from scipy.sparse import csr_matrix
        from scipy.sparse.linalg import LinearOperator, cg
        delta = p[self.edges[:, 1]]-p[self.edges[:, 0]]
        lengths = np.linalg.norm(delta, axis=1)
        unit = delta/np.maximum(lengths[:, None], 1e-12)
        error = self.correction*(lengths-self.rest)
        edges = self.edges
        pairs = cKDTree(p).query_pairs(self.clearance*1.4, output_type="ndarray")
        if len(pairs):
            pairs = pairs[np.linalg.norm(self.uv[pairs[:, 1]]-self.uv[pairs[:, 0]], axis=1) > 2.5*self.clearance]
            offset = p[pairs[:, 1]]-p[pairs[:, 0]]
            distances = np.linalg.norm(offset, axis=1)
            normal = offset/np.maximum(distances[:, None], 1e-12)
            separation = self.correction*(self.clearance-distances)
            approach = np.sum((requested[pairs[:, 1]]-requested[pairs[:, 0]])*normal, axis=1)
            active = approach < separation
            edges = np.vstack([edges, pairs[active]])
            unit = np.vstack([unit, 2*normal[active]])
            error = np.r_[error, -2*separation[active]]
        indices = (edges[:, :, None]*3+np.arange(3)).reshape(-1)
        data = np.concatenate([-unit, unit], axis=1).reshape(-1)
        a = csr_matrix((data, indices, np.arange(len(edges)+1)*6), shape=(len(edges), len(p)*3))
        at, strength = a.T.tocsr(), self.strength
        operator = LinearOperator((len(p)*3, len(p)*3), matvec=lambda v: v+strength*(at@(a@v)))
        diag = 1+strength*np.bincount(indices, weights=data*data, minlength=len(p)*3)
        rhs = requested.ravel()-strength*(at@error)
        iterations = 0
        def count(_):
            nonlocal iterations
            iterations += 1
        result, status = cg(operator, rhs, x0=requested.ravel(), callback=count,
            M=LinearOperator(operator.shape, matvec=lambda v: v/diag), rtol=1e-4, atol=1e-7,
            maxiter=self.maximum_iterations)
        residual = float(np.linalg.norm(operator@result-rhs))
        self.statistics["calls"] += 1
        self.statistics["maximum_iterations_used"] = max(self.statistics["maximum_iterations_used"], iterations)
        self.statistics["maximum_relative_residual"] = max(self.statistics["maximum_relative_residual"], residual/max(float(np.linalg.norm(rhs)), 1e-30))
        if status != 0 or not np.isfinite(result).all():
            raise RuntimeError(f"Material velocity projection did not converge: status={status}, residual={residual}")
        return result.reshape(-1, 3)


class ClothPreparation:
    """Management-only controller; on_tick receives every real post-step state."""

    def __init__(self, world, task, profile, *, table_bounds, config=None, on_tick=None):
        self.world, self.task, self.profile = world, task, profile
        self.cfg = config or PreparationConfig()
        self.cloth = task.entities["blanket"]
        self.on_tick = on_tick or (lambda *args: None)
        self.table_bounds = table_bounds
        self.edges = np.asarray(self.cloth.edges, dtype=int)
        self.rest = np.asarray(self.cloth._edges_len_rest).copy()
        self.projector = MaterialVelocityProjection(self.edges, self.rest, task.material_uv,
            strength=self.cfg.projection_strength, correction=self.cfg.projection_correction_rate_s,
            clearance=task.layout.particle_size_m, maximum_iterations=self.cfg.projection_maximum_iterations)
        # Visual edge geometry is inspected separately from physical material.
        self.visual_edges = np.unique(np.sort(task.birth_faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1), axis=0)
        self.visual_rest = np.linalg.norm(task.birth_uv[self.visual_edges[:, 1]]-task.birth_uv[self.visual_edges[:, 0]], axis=1)
        self.report = dict(kind="offline_bounded_velocity_preparation", robot_manipulation=False,
            profile=asdict(profile), parameters=asdict(self.cfg), position_writes=0, rest_writes=0,
            support_writes=0, pins_added=0, velocity_control_ticks=0, completed=False, stages=[])

    def state(self):
        p = to_numpy(self.cloth.get_particles_pos()).reshape(-1, 3)
        v = to_numpy(self.cloth.get_particles_vel()).reshape(-1, 3)
        if not np.isfinite(p).all() or not np.isfinite(v).all():
            raise FloatingPointError("Nonfinite preparation state")
        return p, v

    def metrics(self, p, v):
        b = self.task.binding
        visual = np.einsum("vk,vkj->vj", b.support_weights, p[b.support_indices])
        metrics = measure(p, v, self.task.particle_faces, self.edges, self.rest,
            table_z=self.task.table_height_m, table_bounds=self.table_bounds,
            material_area=self.task.layout.length_m*self.task.layout.width_m,
            visual_positions=visual, visual_edges=self.visual_edges, visual_rest_lengths=self.visual_rest)
        pairs = cKDTree(p).query_pairs(self.task.layout.particle_size_m, output_type="ndarray")
        if len(pairs):
            pairs = pairs[np.linalg.norm(self.task.material_uv[pairs[:, 1]]-self.task.material_uv[pairs[:, 0]], axis=1) > 2.5*self.task.layout.particle_size_m]
        gap = self.task.layout.particle_size_m if not len(pairs) else np.linalg.norm(p[pairs[:, 1]]-p[pairs[:, 0]], axis=1).min()
        metrics.update(minimum_nonlocal_particle_distance_m=float(gap),
                       self_contact_check="nonlocal particle separation; not surface CCD certification")
        return metrics

    def tick(self, stage, *, target=None, speed_limit=None):
        if target is not None:
            p, _ = self.state()
            requested = (target-p)*self.cfg.servo_gain_s
            speed = np.linalg.norm(requested, axis=1)
            requested *= np.minimum(1, self.cfg.maximum_speed_m_s/np.maximum(speed, 1e-12))[:, None]
            velocity = self.projector.project(p, requested)
            velocity *= min(1., self.cfg.maximum_speed_m_s/max(float(np.linalg.norm(velocity, axis=1).max()), 1e-12))
            self.cloth.set_particles_vel(velocity)
            self.report["velocity_control_ticks"] += 1
        elif speed_limit is not None:
            # Explicit offline dissipation during supported placement. This
            # ends before release_tick; the archived candidate has no limiter.
            _, velocity = self.state()
            speeds = np.linalg.norm(velocity, axis=1)
            velocity = velocity*np.minimum(1., speed_limit/np.maximum(speeds, 1e-12))[:, None]
            self.cloth.set_particles_vel(velocity)
            self.report["velocity_control_ticks"] += 1
        self.world.advance()
        p, v = self.state()
        # Preserve the actual completed tick even when its health guard fails.
        self.on_tick(stage, p, v)
        stretch = np.linalg.norm(p[self.edges[:, 1]]-p[self.edges[:, 0]], axis=1)/self.rest
        if stretch.max() > self.cfg.maximum_material_stretch or p[:, 2].min() < self.task.table_height_m-self.cfg.penetration_tolerance_m:
            raise RuntimeError(f"Preparation material/contact guard failed at {stage}: stretch={stretch.max():.5f}")
        return p, v

    def drive(self, name, target_at, seconds):
        start = self.world.physics_step
        steps = int(np.ceil(seconds/self.world.physics_dt_s))
        for i in range(1, steps+1):
            t = i/steps
            self.tick(name, target=target_at(t*t*(3-2*t)))
        final = target_at(1.)
        for _ in range(int(np.ceil(self.cfg.hold_seconds/self.world.physics_dt_s))):
            self.tick(name+"_hold", target=final)
        p, v = self.state()
        self.report["stages"].append(dict(name=name, start_tick=start, end_tick=self.world.physics_step,
            target_rms_error_m=float(np.sqrt(np.mean(np.sum((p-final)**2, axis=1)))), metrics=self.metrics(p, v)))

    def run(self, *, acceptance="released_stable"):
        if acceptance not in {"released_stable", "scene_layout"}:
            raise ValueError("Unknown preparation acceptance")
        self.report["acceptance"] = acceptance
        gravity = self.cloth.solver._gravity.to_numpy().copy()
        binding_hash = self.task.binding.sha256
        origin = np.r_[self.task.config["center_xy_m"], self.task.table_height_m+self.task.layout.drop_clearance_m]
        def target(gather, twist):
            points = preparation_target(self.task.material_uv, self.task.layout.length_m,
                self.task.layout.width_m, gather, twist, self.profile)
            # Keep the lowest target at the declared clearance while rotating
            # the pleated bundle. Lowering is a separate controlled stage.
            points[:, 2] -= points[:, 2].min()
            return points+origin
        try:
            self.cloth.solver._gravity.from_numpy(np.zeros_like(gravity))
            self.drive("gather", lambda t: target(t, 0.), self.cfg.gather_seconds)
            if self.profile.twist_angle_deg:
                self.drive("twist", lambda t: target(1., t), self.cfg.twist_seconds)
            p, _ = self.state()
            shift = np.array([0., 0., self.task.table_height_m+self.task.layout.particle_size_m/2-p[:, 2].min()])
            self.drive("lower_to_table", lambda t: p+t*shift, self.cfg.lower_seconds)
            self.cloth.solver._gravity.from_numpy(gravity)
            for _ in range(int(np.ceil(self.cfg.controlled_settle_seconds/self.world.physics_dt_s))):
                self.tick("controlled_settle", speed_limit=self.cfg.settling_speed_limit_m_s)
            # Free continuation begins with the actual remaining velocity;
            # neither velocity limiting nor a zero-velocity write follows.
            self.report["release_tick"] = self.world.physics_step
            limits = dict(penetration_tolerance_m=self.cfg.penetration_tolerance_m,
                maximum_edge_stretch=self.cfg.maximum_material_stretch, maximum_visual_edge_stretch=self.cfg.maximum_visual_stretch,
                mean_speed_m_s=self.cfg.settled_mean_speed_m_s, p99_speed_m_s=self.cfg.settled_p99_speed_m_s,
                maximum_speed_m_s=self.cfg.settled_maximum_speed_m_s, minimum_coverage_ratio=self.cfg.minimum_coverage_ratio,
                maximum_coverage_ratio=self.cfg.maximum_coverage_ratio, maximum_height_m=self.cfg.maximum_height_m)
            window = AcceptanceWindow(self.cfg.stable_window_seconds, self.cfg.maximum_drift_m)
            interval = max(1, round(.025/self.world.physics_dt_s))
            layout_start = layout_origin = None
            layout_drift = 0.
            for i in range(int(np.ceil(self.cfg.maximum_settle_seconds/self.world.physics_dt_s))):
                p, v = self.tick("released_settle")
                if i % interval:
                    continue
                metrics = self.metrics(p, v)
                gates = initial_gates(metrics, limits)
                gates["nonlocal_particle_clearance"] = metrics["minimum_nonlocal_particle_distance_m"] >= .9*self.task.layout.particle_size_m
                self.report.update(final_metrics=metrics, final_gates=gates)
                if window.update(self.world.sim_time_s, p, gates):
                    self.report.update(completed=True, stable_duration_s=window.duration,
                        stable_drift_m=window.drift_m, final_tick=self.world.physics_step)
                    break
                # Scene setup can be reviewed while the known particle-motion
                # issue is deferred. Keep the original stability result false,
                # and retain all geometry/material/binding gates unchanged.
                if acceptance == "scene_layout":
                    if not all(v for k, v in gates.items() if k != "settled"):
                        layout_start = layout_origin = None
                        layout_drift = 0.
                    else:
                        if layout_start is None:
                            layout_start, layout_origin = self.world.sim_time_s, p.copy()
                        layout_drift = max(layout_drift, float(np.linalg.norm(p-layout_origin, axis=1).max()))
                        if self.world.sim_time_s-layout_start+1e-9 >= self.cfg.stable_window_seconds:
                            self.report.update(scene_layout_completed=True,
                                motion_qualification="deferred", final_tick=self.world.physics_step,
                                layout_observation_seconds=self.world.sim_time_s-layout_start,
                                layout_drift_m=layout_drift)
                            break
            if not self.report["completed"] and not self.report.get("scene_layout_completed"):
                raise RuntimeError(f"Preparation did not settle within budget: {self.report['final_gates']}")
            return self.report
        finally:
            self.cloth.solver._gravity.from_numpy(gravity)
            self.report["gravity_restored"] = bool(np.array_equal(gravity, self.cloth.solver._gravity.to_numpy()))
            self.report["projection"] = self.projector.statistics
            self.report["rest_unchanged"] = bool(np.array_equal(self.rest, self.cloth._edges_len_rest))
            from topogym.world.physics.pbd_binding import read_birth_visual_binding
            self.report["binding_unchanged"] = read_birth_visual_binding(self.cloth).sha256 == binding_hash
            if not self.report["rest_unchanged"] or not self.report["binding_unchanged"]:
                raise RuntimeError("Preparation changed material or visual binding identity")
